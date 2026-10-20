"""Niveau « pages » de export.pdb : lecture, ajout / retrait de lignes, agrandissement d'une table.

Modèle (Deep Symmetry) :
  page 0 : en-tête du fichier (taille de page, nb de tables, prochaine page libre, séquence)
           puis un tableau de 16 octets par table : type, page vide candidate, 1re page, dernière page ;
  page   : en-tête 0x28 octets, tas de lignes qui grandit vers le haut, index des lignes en fin de page
           qui grandit vers le bas, par groupes de 16 (0x24 octets : 16 offsets, masque « ligne
           présente », masque « transaction ») ; une ligne supprimée garde ses octets, seul son bit saute ;
  table  : liste chaînée de pages ; en pratique la 1re est une page d'index (drapeau 0x40) qui
           référence les pages de données.
Toute modification : on n'écrit que les pages touchées ; `PdbFile.touched` les liste pour que le
contrôle final prouve que le reste du fichier est resté identique octet pour octet.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

from . import rows as _rows
from .format import (
    EMPTY_ENTRY, FILE_TABLES_AT, GROUP, HEADER, MAX_SLOTS, PAGE_SIZE,
    PdbCapacityError, PdbFormatError, index_size, u16, u32,
)


@dataclass
class TableRef:
    slot: int            # position dans le tableau de la page 0
    type: int
    empty_candidate: int
    first_page: int
    last_page: int


class Page:
    """Vue modifiable d'une page à l'intérieur du buffer du fichier."""

    __slots__ = ("data", "base", "index")

    def __init__(self, data: bytearray, index: int) -> None:
        self.data, self.index, self.base = data, index, index * PAGE_SIZE

    # ---- accès bruts
    def u16(self, off: int) -> int:
        return u16(self.data, self.base + off)

    def u32(self, off: int) -> int:
        return u32(self.data, self.base + off)

    def set_u16(self, off: int, value: int) -> None:
        struct.pack_into("<H", self.data, self.base + off, value)

    def set_u32(self, off: int, value: int) -> None:
        struct.pack_into("<I", self.data, self.base + off, value)

    def raw(self) -> bytes:
        return bytes(self.data[self.base: self.base + PAGE_SIZE])

    # ---- en-tête
    @property
    def type(self) -> int:
        return self.u32(0x08)

    @property
    def next_page(self) -> int:
        return self.u32(0x0C)

    @property
    def flags(self) -> int:
        return self.data[self.base + 0x1B]

    @property
    def is_index(self) -> bool:
        return bool(self.flags & 0x40)

    @property
    def free(self) -> int:
        return self.u16(0x1C)

    @property
    def used(self) -> int:
        return self.u16(0x1E)

    def _packed(self) -> int:
        return int.from_bytes(self.data[self.base + 0x18: self.base + 0x1B], "little")

    @property
    def num_slots(self) -> int:
        """Nombre d'emplacements de ligne (bits 0-12 du champ 24 bits à 0x18)."""
        return self._packed() & 0x1FFF

    @property
    def num_valid(self) -> int:
        """Nombre de lignes valides (bits 13-23 du même champ)."""
        return self._packed() >> 13

    def _set_counts(self, slots: int, valid: int) -> None:
        self.data[self.base + 0x18: self.base + 0x1B] = (slots | (valid << 13)).to_bytes(3, "little")

    def _mark(self, slot: int) -> None:
        """Marqueur « dernière ligne touchée » (constaté sur export réel : u2 à 0x20 = 1, u2 à 0x22 =
        numéro de la ligne, bit correspondant dans le 2e mot du groupe d'index, les autres groupes à 0)."""
        self.set_u16(0x20, 1)
        self.set_u16(0x22, slot)
        for g in range((self.num_slots + 15) // 16):
            self.set_u16(self._flags_pos(g) + 2, (1 << (slot % 16)) if g == slot // 16 else 0)

    def is_blank(self) -> bool:
        return not any(self.data[self.base: self.base + PAGE_SIZE])

    # ---- index des lignes
    def _slot_pos(self, i: int) -> int:
        g, k = divmod(i, 16)
        return PAGE_SIZE - g * GROUP - 6 - 2 * k

    def _flags_pos(self, group: int) -> int:
        return PAGE_SIZE - group * GROUP - 4

    def row_offset(self, i: int) -> int:
        return HEADER + self.u16(self._slot_pos(i))

    def present(self, i: int) -> bool:
        g, k = divmod(i, 16)
        return bool((self.u16(self._flags_pos(g)) >> k) & 1)

    def present_rows(self) -> Iterator[Tuple[int, int]]:
        """(numéro de ligne, offset dans la page) des lignes valides."""
        for i in range(self.num_slots):
            if self.present(i):
                yield i, self.row_offset(i)

    @property
    def heap_end(self) -> int:
        return HEADER + self.used

    def check_data_page(self) -> None:
        """Vérifie que la page respecte le modèle (sinon PdbFormatError : on n'y écrit pas)."""
        n = self.num_slots
        if self.is_index:
            raise PdbFormatError(f"page {self.index}: index page, no data")
        if self.flags not in (0x24, 0x34):
            raise PdbFormatError(f"page {self.index} : drapeaux de page inconnus ({self.flags:#x})")
        if n > MAX_SLOTS or self.heap_end % 4:
            raise PdbFormatError(f"page {self.index}: inconsistent counters")
        if self.heap_end + self.free + index_size(n) != PAGE_SIZE:      # vrai sur les 40 pages d'un export réel
            raise PdbFormatError(f"page {self.index}: inconsistent free/used sizes")
        valid = sum(1 for i in range(n) if self.present(i))
        if valid != self.num_valid:
            raise PdbFormatError(f"page {self.index}: inconsistent valid row count")

        for i in range(n):
            off = self.row_offset(i)
            if self.present(i) and (not (HEADER <= off < self.heap_end) or off % 4):
                raise PdbFormatError(f"page {self.index}: row {i} outside the heap (offset {off:#x})")

    def can_fit(self, row_len: int) -> bool:
        n = self.num_slots
        return n + 1 <= MAX_SLOTS and self.heap_end + row_len <= PAGE_SIZE - index_size(n + 1)

    def append(self, row: bytes, seq: int) -> int:
        """Ajoute une ligne (déjà alignée sur 4 octets) ; renvoie son numéro."""
        if len(row) % 4 or not self.can_fit(len(row)):
            raise PdbCapacityError(f"page {self.index}: no room for {len(row)} bytes")
        n, start = self.num_slots, self.heap_end
        self.data[self.base + start: self.base + start + len(row)] = row
        g, k = divmod(n, 16)
        if k == 0:                                   # nouveau groupe d'index
            self.set_u16(self._flags_pos(g), 0)
            self.set_u16(self._flags_pos(g) + 2, 0)
        self.set_u16(self._slot_pos(n), start - HEADER)
        self.set_u16(self._flags_pos(g), self.u16(self._flags_pos(g)) | (1 << k))
        self._set_counts(n + 1, self.num_valid + 1)
        self.set_u16(0x1E, self.used + len(row))
        self.set_u16(0x1C, PAGE_SIZE - index_size(n + 1) - (HEADER + self.used))
        self._mark(n)
        self.set_u32(0x10, seq)
        return n

    def delete(self, i: int, seq: int) -> None:
        """Marque la ligne supprimée (comme Rekordbox : bit de présence à 0, octets conservés)."""
        g, k = divmod(i, 16)
        self.set_u16(self._flags_pos(g), self.u16(self._flags_pos(g)) & ~(1 << k) & 0xFFFF)
        self._set_counts(self.num_slots, self.num_valid - 1)
        self.data[self.base + 0x1B] = self.flags | 0x10      # 0x24 -> 0x34 : « contient des lignes supprimées »
        self._mark(i)
        self.set_u32(0x10, seq)


class PdbFile:
    def __init__(self, data: bytes, allow_growth: bool = False) -> None:
        if len(data) < 2 * PAGE_SIZE:
            raise PdbFormatError("file too short for an export.pdb")
        self.data = bytearray(data)
        self.allow_growth = allow_growth
        if u32(self.data, 0) != 0 or u32(self.data, 4) != PAGE_SIZE:
            raise PdbFormatError(f"page size {u32(self.data, 4)} (expected: {PAGE_SIZE})")
        if len(data) % PAGE_SIZE:
            raise PdbFormatError("file size is not a multiple of the page size")
        self.n_pages = len(data) // PAGE_SIZE
        count = u32(self.data, 8)
        if not 1 <= count <= 64 or FILE_TABLES_AT + 16 * count > PAGE_SIZE:
            raise PdbFormatError(f"implausible table count: {count}")
        self.next_unused = u32(self.data, 0x0C)
        # Constaté sur un vrai export : next_unused = nombre de pages + 1 (la page « vide candidate » de
        # la dernière table n'existe pas encore physiquement : le fichier s'arrête à la dernière page écrite).
        if not 2 <= self.next_unused <= self.n_pages + 8:
            raise PdbFormatError("next free page outside the file")
        self.seq = u32(self.data, 0x14)
        self.tables: Dict[int, TableRef] = {}
        for slot in range(count):
            t, empty, first, last = struct.unpack_from("<IIII", self.data, FILE_TABLES_AT + 16 * slot)
            if t in self.tables:
                raise PdbFormatError(f"table {t} declared twice")
            self.tables[t] = TableRef(slot, t, empty, first, last)
        self.touched: set = set()
        self._begun = False

    # ------------------------------------------------------------------ navigation
    def page(self, index: int) -> Page:
        if not 1 <= index < self.n_pages:
            raise PdbFormatError(f"page {index} outside the file ({self.n_pages} pages)")
        return Page(self.data, index)

    def table(self, ttype: int) -> TableRef:
        if ttype not in self.tables:
            raise PdbFormatError(f"table {ttype} missing from the file")
        return self.tables[ttype]

    def chain(self, ttype: int) -> List[int]:
        """Pages de la table, de la première à la dernière, en suivant next_page."""
        tab = self.table(ttype)
        out: List[int] = []
        p = tab.first_page
        while True:
            if p in out:
                raise PdbFormatError(f"table {ttype}: loop in the page list")
            page = self.page(p)
            if page.index != p or page.type != ttype or page.u32(0x04) != p:
                raise PdbFormatError(f"table {ttype}: page {p} does not belong to the table")
            out.append(p)
            if p == tab.last_page:
                return out
            p = page.next_page

    def data_pages(self, ttype: int) -> List[int]:
        return [p for p in self.chain(ttype) if not self.page(p).is_index]

    def index_pages(self, ttype: int) -> List[int]:
        return [p for p in self.chain(ttype) if self.page(p).is_index]

    def iter_rows(self, ttype: int) -> Iterator[Tuple[int, int, int]]:
        """(page, numéro de ligne, offset dans la page) de toutes les lignes valides de la table."""
        for p in self.data_pages(ttype):
            page = self.page(p)
            page.check_data_page()
            for i, off in page.present_rows():
                end = _rows.row_end(ttype, self.data, page.base + off) - page.base
                if end > page.heap_end:
                    raise PdbFormatError(
                        f"page {p}: row {i} goes beyond the used area ({end:#x} > {page.heap_end:#x})")
                yield p, i, off

    # ------------------------------------------------------------------ écriture
    def _begin(self) -> None:
        if not self._begun:
            self._begun = True
            self.seq += 1
            struct.pack_into("<I", self.data, 0x14, self.seq)

    def _save_table(self, tab: TableRef) -> None:
        struct.pack_into("<IIII", self.data, FILE_TABLES_AT + 16 * tab.slot,
                         tab.type, tab.empty_candidate, tab.first_page, tab.last_page)

    def insert_row(self, ttype: int, row: bytes) -> Tuple[int, int]:
        """Ajoute une ligne à la table ; renvoie (page, numéro de ligne)."""
        if len(row) % 4:
            raise PdbFormatError("row not aligned on 4 bytes")
        self._begin()
        pages = self.data_pages(ttype)
        if pages:
            last = self.page(pages[-1])
            last.check_data_page()
            if last.can_fit(len(row)):
                self.touched.add(last.index)
                return last.index, last.append(row, self.seq)
        if not self.allow_growth:
            raise PdbCapacityError(
                f"table {ttype}: last page full (growing a table is disabled for safety)")
        page = self.page(self._grow(ttype, pages))
        if not page.can_fit(len(row)):
            raise PdbFormatError("row larger than a page")
        return page.index, page.append(row, self.seq)

    def delete_row(self, page: int, slot: int) -> None:
        self._begin()
        pg = self.page(page)
        pg.check_data_page()
        if not pg.present(slot):
            raise PdbFormatError(f"page {page}: row {slot} already deleted")
        pg.delete(slot, self.seq)
        self.touched.add(page)

    def patch_u32(self, page: int, row_offset: int, field_offset: int, value: int) -> None:
        self._begin()
        pg = self.page(page)
        pg.set_u32(row_offset + field_offset, value)
        pg.set_u32(0x10, self.seq)
        self.touched.add(page)

    # ------------------------------------------------------------ agrandir une table
    def _grow(self, ttype: int, data_pages: List[int]) -> int:
        """Ajoute une page de données à la table (comme Rekordbox : la « page vide candidate » devient la
        dernière page, une nouvelle candidate est réservée à `next_unused`). Constaté sur un export réel :
        la page d'index d'une table NE liste PAS les pages de données (seulement certaines pages avec
        lignes supprimées) : elle n'est donc pas modifiée. Toutes les hypothèses sont vérifiées AVANT la
        moindre écriture ; au moindre doute : PdbFormatError (fichier intact)."""
        tab = self.table(ttype)
        chain = self.chain(ttype)
        last = self.page(chain[-1])
        if last.next_page != tab.empty_candidate:
            raise PdbFormatError(f"table {ttype}: the last page does not point to the empty candidate page")
        new = tab.empty_candidate
        spare = max(self.next_unused, new + 1)       # future page vide candidate de la table
        if new < 1 or new in chain or new > self.n_pages + 64:
            raise PdbFormatError(f"table {ttype}: invalid empty candidate page ({new})")
        if new < self.n_pages and not self.page(new).is_blank():
            raise PdbFormatError(f"page {new} should be empty but is not")
        if spare < self.n_pages and not self.page(spare).is_blank():
            raise PdbFormatError(f"page {spare} should be free but is not empty")
        indexes = [p for p in chain if self.page(p).is_index]
        if len(indexes) > 1 or (indexes and chain[0] != indexes[0]):
            raise PdbFormatError(f"table {ttype}: unknown index page layout")

        # --- vérifications passées : on écrit
        while self.n_pages <= new:                   # la candidate n'existe pas encore dans le fichier :
            self.data.extend(b"\x00" * PAGE_SIZE)   # pages intermédiaires à zéro, comme dans un export réel
            self.n_pages += 1
        self.next_unused = spare + 1
        struct.pack_into("<I", self.data, 0x0C, self.next_unused)
        base = new * PAGE_SIZE
        self.data[base: base + PAGE_SIZE] = b"\x00" * PAGE_SIZE
        pg = Page(self.data, new)
        pg.set_u32(0x04, new)
        pg.set_u32(0x08, ttype)
        pg.set_u32(0x0C, spare)
        pg.set_u32(0x10, self.seq)
        self.data[pg.base + 0x1B] = 0x24
        pg.set_u16(0x1C, PAGE_SIZE - HEADER)
        pg.set_u16(0x1E, 0)
        pg.set_u16(0x20, 0x1FFF)
        pg.set_u16(0x22, 0x1FFF)
        last.set_u32(0x0C, new)
        last.set_u32(0x10, self.seq)
        tab.last_page, tab.empty_candidate = new, spare
        self._save_table(tab)
        self.touched.update((new, last.index))
        return new

    # ------------------------------------------------------------------ contrôle
    def to_bytes(self) -> bytes:
        return bytes(self.data)


def validate_against(old: bytes, new: bytes, touched: set) -> None:
    """Preuve avant écriture : `new` est un fichier valide et seules les pages `touched` (plus la
    page 0) diffèrent de `old`. Lève PdbFormatError sinon."""
    fresh = PdbFile(new)
    for ttype in fresh.tables:
        for p in fresh.data_pages(ttype):
            fresh.page(p).check_data_page()
        fresh.chain(ttype)
    if fresh.next_unused < max([t.last_page for t in fresh.tables.values()] + [1]) + 1:
        raise PdbFormatError("inconsistent next free page after the change")
    for i in range(1, len(old) // PAGE_SIZE):
        if i in touched:
            continue
        if old[i * PAGE_SIZE:(i + 1) * PAGE_SIZE] != new[i * PAGE_SIZE:(i + 1) * PAGE_SIZE]:
            raise PdbFormatError(f"page {i} changed although it should not have been")
