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

    @property
    def num_slots(self) -> int:
        small, large = self.data[self.base + 0x18], self.u16(0x22)
        return large if (large > small and large != 0x1FFF) else small

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
            raise PdbFormatError(f"page {self.index} : page d'index, pas de données")
        if n > MAX_SLOTS or self.heap_end % 4:
            raise PdbFormatError(f"page {self.index} : compteurs incohérents")
        if self.heap_end + index_size(n) > PAGE_SIZE:
            raise PdbFormatError(f"page {self.index} : le tas déborde sur l'index des lignes")
        for i in range(n):
            off = self.row_offset(i)
            if self.present(i) and (not (HEADER <= off < self.heap_end) or off % 4):
                raise PdbFormatError(f"page {self.index} : ligne {i} hors du tas (offset {off:#x})")

    def can_fit(self, row_len: int) -> bool:
        n = self.num_slots
        return n + 1 <= MAX_SLOTS and self.heap_end + row_len <= PAGE_SIZE - index_size(n + 1)

    def append(self, row: bytes, seq: int) -> int:
        """Ajoute une ligne (déjà alignée sur 4 octets) ; renvoie son numéro."""
        if len(row) % 4 or not self.can_fit(len(row)):
            raise PdbCapacityError(f"page {self.index} : pas de place pour {len(row)} octets")
        n, start = self.num_slots, self.heap_end
        self.data[self.base + start: self.base + start + len(row)] = row
        g, k = divmod(n, 16)
        if k == 0:                                   # nouveau groupe d'index
            self.set_u16(self._flags_pos(g), 0)
            self.set_u16(self._flags_pos(g) + 2, 0)
        self.set_u16(self._slot_pos(n), start - HEADER)
        self.set_u16(self._flags_pos(g), self.u16(self._flags_pos(g)) | (1 << k))
        self.data[self.base + 0x18] = n + 1
        if self.u16(0x22) not in (0, 0x1FFF):        # compteur « large » déjà utilisé : on le suit
            self.set_u16(0x22, n + 1)
        self.set_u16(0x1E, self.used + len(row))
        self.set_u16(0x1C, PAGE_SIZE - index_size(n + 1) - (HEADER + self.used))
        self.set_u32(0x10, seq)
        return n

    def delete(self, i: int, seq: int) -> None:
        """Marque la ligne supprimée (comme Rekordbox : bit de présence à 0, octets conservés)."""
        g, k = divmod(i, 16)
        self.set_u16(self._flags_pos(g), self.u16(self._flags_pos(g)) & ~(1 << k) & 0xFFFF)
        self.set_u32(0x10, seq)


class PdbFile:
    def __init__(self, data: bytes, allow_growth: bool = False) -> None:
        if len(data) < 2 * PAGE_SIZE:
            raise PdbFormatError("fichier trop court pour un export.pdb")
        self.data = bytearray(data)
        self.allow_growth = allow_growth
        if u32(self.data, 0) != 0 or u32(self.data, 4) != PAGE_SIZE:
            raise PdbFormatError(f"taille de page {u32(self.data, 4)} (attendu : {PAGE_SIZE})")
        if len(data) % PAGE_SIZE:
            raise PdbFormatError("taille du fichier non multiple de la taille de page")
        self.n_pages = len(data) // PAGE_SIZE
        count = u32(self.data, 8)
        if not 1 <= count <= 64 or FILE_TABLES_AT + 16 * count > PAGE_SIZE:
            raise PdbFormatError(f"nombre de tables invraisemblable : {count}")
        self.next_unused = u32(self.data, 0x0C)
        if not 2 <= self.next_unused <= self.n_pages:
            raise PdbFormatError("prochaine page libre hors du fichier")
        self.seq = u32(self.data, 0x14)
        self.tables: Dict[int, TableRef] = {}
        for slot in range(count):
            t, empty, first, last = struct.unpack_from("<IIII", self.data, FILE_TABLES_AT + 16 * slot)
            if t in self.tables:
                raise PdbFormatError(f"table {t} déclarée deux fois")
            self.tables[t] = TableRef(slot, t, empty, first, last)
        self.touched: set = set()
        self._begun = False

    # ------------------------------------------------------------------ navigation
    def page(self, index: int) -> Page:
        if not 1 <= index < self.n_pages:
            raise PdbFormatError(f"page {index} hors du fichier ({self.n_pages} pages)")
        return Page(self.data, index)

    def table(self, ttype: int) -> TableRef:
        if ttype not in self.tables:
            raise PdbFormatError(f"table {ttype} absente du fichier")
        return self.tables[ttype]

    def chain(self, ttype: int) -> List[int]:
        """Pages de la table, de la première à la dernière, en suivant next_page."""
        tab = self.table(ttype)
        out: List[int] = []
        p = tab.first_page
        while True:
            if p in out:
                raise PdbFormatError(f"table {ttype} : boucle dans la liste de pages")
            page = self.page(p)
            if page.index != p or page.type != ttype or page.u32(0x04) != p:
                raise PdbFormatError(f"table {ttype} : la page {p} n'appartient pas à la table")
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
                        f"page {p} : la ligne {i} dépasse la zone « utilisée » ({end:#x} > {page.heap_end:#x})")
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
            raise PdbFormatError("ligne non alignée sur 4 octets")
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
                f"table {ttype} : dernière page pleine (l'agrandissement d'une table est désactivé par prudence)")
        page = self.page(self._grow(ttype, pages))
        if not page.can_fit(len(row)):
            raise PdbFormatError("ligne plus grande qu'une page")
        return page.index, page.append(row, self.seq)

    def delete_row(self, page: int, slot: int) -> None:
        self._begin()
        pg = self.page(page)
        pg.check_data_page()
        if not pg.present(slot):
            raise PdbFormatError(f"page {page} : ligne {slot} déjà supprimée")
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
        """Ajoute une page de données à la table. Toutes les hypothèses du modèle sont vérifiées
        AVANT la moindre écriture ; au moindre doute : PdbFormatError (fichier intact)."""
        tab = self.table(ttype)
        chain = self.chain(ttype)
        last = self.page(chain[-1])
        if last.next_page != tab.empty_candidate:
            raise PdbFormatError(f"table {ttype} : la dernière page ne pointe pas sur la page vide candidate")
        new = tab.empty_candidate
        if new < 1 or new in chain:
            raise PdbFormatError(f"table {ttype} : page vide candidate invalide ({new})")
        spare = max(self.next_unused, new + 1)       # future page vide candidate de la table
        for idx in (new, spare):
            if idx < self.n_pages:
                pg_i = self.page(idx)
                if not pg_i.is_blank() and not (idx == new and pg_i.type == ttype and pg_i.num_slots == 0):
                    raise PdbFormatError(f"page {idx} censée être libre mais non vide")
        indexes = [p for p in chain if self.page(p).is_index]
        if len(indexes) > 1 or (indexes and chain[0] != indexes[0]):
            raise PdbFormatError(f"table {ttype} : organisation des pages d'index non reconnue")
        if indexes:
            self._check_index_registration(indexes[0], data_pages)   # lève AVANT d'écrire

        # --- toutes les vérifications sont passées : on écrit
        template: Optional[Page] = self.page(data_pages[-1]) if data_pages else None
        while self.n_pages < spare + 1:
            self.data.extend(b"\x00" * PAGE_SIZE)
            self.n_pages += 1
        self.next_unused = spare + 1
        struct.pack_into("<I", self.data, 0x0C, self.next_unused)
        base = new * PAGE_SIZE
        self.data[base: base + PAGE_SIZE] = b"\x00" * PAGE_SIZE
        pg = Page(self.data, new)
        if template is not None:       # mêmes champs « inconnus » que les pages sœurs
            for a, b in ((0x14, 0x18), (0x19, 0x1B), (0x20, 0x22), (0x24, 0x28)):
                self.data[pg.base + a: pg.base + b] = self.data[template.base + a: template.base + b]
        if template is not None and template.u16(0x22) == 0x1FFF:   # « compteur large inutilisé »
            pg.set_u16(0x22, 0x1FFF)
        pg.set_u32(0x04, new)
        pg.set_u32(0x08, ttype)
        pg.set_u32(0x0C, spare)
        pg.set_u32(0x10, self.seq)
        self.data[pg.base + 0x1B] = template.flags if template is not None else 0x34
        pg.set_u16(0x1C, PAGE_SIZE - HEADER)
        pg.set_u16(0x1E, 0)
        last.set_u32(0x0C, new)
        last.set_u32(0x10, self.seq)
        tab.last_page, tab.empty_candidate = new, spare
        self._save_table(tab)
        self.touched.update((new, last.index))
        if indexes:
            self._register_in_index(indexes[0], data_pages, new)
        return new

    def _locate_index_run(self, index_page: int, data_pages: List[int]) -> Tuple[int, int]:
        """Cherche dans la page d'index la suite d'entrées (page << 3) des pages de données, suivie
        d'une entrée libre. Renvoie (offset de la 1re entrée, offset du couple de compteurs)."""
        if not data_pages:
            raise PdbFormatError("page d'index sans page de données : organisation non reconnue")
        pg = self.page(index_page)
        run = b"".join(struct.pack("<I", p << 3) for p in data_pages)
        raw = pg.raw()
        start = raw.find(run, HEADER)
        while start != -1 and start % 4:
            start = raw.find(run, start + 1)
        if start == -1:
            raise PdbFormatError(f"page d'index {index_page} : entrées des pages de données introuvables")
        after = start + len(run)
        if after + 4 > PAGE_SIZE or u32(raw, after) != EMPTY_ENTRY:
            raise PdbFormatError(f"page d'index {index_page} : pas d'entrée libre après la dernière page")
        pair = struct.pack("<HH", len(data_pages), len(data_pages))
        hits = [o for o in range(HEADER, start, 2) if raw[o:o + 4] == pair]
        if len(hits) != 1:
            raise PdbFormatError(f"page d'index {index_page} : compteurs d'entrées non reconnus")
        return start, hits[0]

    def _check_index_registration(self, index_page: int, data_pages: List[int]) -> None:
        self._locate_index_run(index_page, data_pages)

    def _register_in_index(self, index_page: int, data_pages: List[int], new_page: int) -> None:
        start, counters = self._locate_index_run(index_page, data_pages)
        pg = self.page(index_page)
        n = len(data_pages)
        pg.set_u32(start + 4 * n, new_page << 3)
        pg.set_u16(counters, n + 1)
        pg.set_u16(counters + 2, n + 1)
        pg.set_u32(0x10, self.seq)
        self.touched.add(index_page)

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
        raise PdbFormatError("prochaine page libre incohérente après modification")
    for i in range(1, len(old) // PAGE_SIZE):
        if i in touched:
            continue
        if old[i * PAGE_SIZE:(i + 1) * PAGE_SIZE] != new[i * PAGE_SIZE:(i + 1) * PAGE_SIZE]:
            raise PdbFormatError(f"page {i} modifiée alors qu'elle ne devait pas l'être")
