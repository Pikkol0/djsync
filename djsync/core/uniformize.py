"""Uniformiser une playlist (1.2.2, C14) : titres, artistes, album, année, genre et pochette rendus
homogènes SANS retélécharger (hot cues et grilles intacts). Rien n'est écrit sans validation.

Règles (fiches S02-S06 de la revue) :
  * titre : « feat. X » sorti du titre (X rejoint les artistes), nom de l'artiste en tête retiré
    (« Dr. Dre - Still D.R.E. »), bruit YouTube retiré ((Official Video), (Lyrics), [Visualizer]…) ;
    ce qui distingue une version pour un DJ est GARDÉ (Remix, Extended, Live, Part 3…) ; casse intacte ;
  * artistes : principal puis invités, séparés par une virgule. Source, dans l'ordre : Deezer quand la
    correspondance est sûre (liste « contributors » : principal + invités), sinon le titre
    (« Artiste - Titre (feat. Invité) »), sinon le nom de la chaîne nettoyé (« - Topic », « VEVO »,
    « Officiel ») ; une chaîne qui n'est visiblement pas l'artiste (agrégateur de paroles…) rend la
    proposition « douteuse » ;
  * album / année / genre / pochette : Deezer ; un album qui n'est que le nom de la vidéo est remplacé,
    un vrai album n'est jamais écrasé ; un champ vide est complété.
Le fichier audio n'est ni modifié ni renommé (S05 reporté).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from .duplicates import normalize

ARTIST_SEP = ", "
# ce qui distingue une version (gardé dans le titre)
_KEEP = re.compile(r"\b(remix|rmx|edit|mix|live|acoustic|acoustique|instrumental|clean|vip|version|extended|radio|"
                   r"part|pt|remaster(ed)?|bootleg|mashup|dub|rework|flip|session|unplugged|slowed|sped|reprise|"
                   r"intro|outro|interlude|cover)\b", re.IGNORECASE)
# bruit des vidéos (retiré quand il est entre parenthèses / crochets, ou en fin de titre après « | » ou « - »)
_NOISE_WORDS = (r"official|officiel(le)?|video|vid[e\u00e9]o|clip|lyrics?|lyric video|paroles|audio|visuali[sz]er|hd|hq|4k|"
                r"explicit|music video|mv|visual|full|audio officiel|s(?:on) officiel|en exclu|exclu")
_BRACKET = re.compile(r"\s*[\(\[]([^\)\]]*)[\)\]]")
_NOISE = re.compile(rf"^(?:\s|\W)*(?:{_NOISE_WORDS})(?:(?:\s|\W)+(?:{_NOISE_WORDS}))*(?:\s|\W)*$", re.IGNORECASE)
_TAIL_NOISE = re.compile(rf"\s*[|\-–—]\s*(?:{_NOISE_WORDS})(?:\s+(?:{_NOISE_WORDS}))*\s*$", re.IGNORECASE)
# bruit en fin de titre sans séparateur (« Many Men Lyrics ») : seulement des expressions sans ambiguïté
_TAIL_BARE = re.compile(r"\s+(?:official\s+(?:music\s+)?(?:video|audio|clip)|lyrics?(?:\s+video)?|clip\s+officiel|"
                        r"audio\s+officiel|visuali[sz]er|paroles)\s*$", re.IGNORECASE)
_FEAT = re.compile(r"[\(\[]?\s*\b(?:feat\.?|ft\.?|featuring)\s+([^\)\]]+?)\s*(?:[\)\]]|$)", re.IGNORECASE)
_SPLIT_ARTISTS = re.compile(r"\s*(?:,|&|\bx\b|\bX\b|\bet\b|\band\b|\b(?:feat|ft)\b\.?|\bfeaturing\b)\s*", re.IGNORECASE)
_CHANNEL_SUFFIX = re.compile(r"(\s*-\s*topic|\s*vevo|\s+(?:officiel(?:le)?|official)(?:\s+channel)?|\s*\(official\))$",
                             re.IGNORECASE)
_AGGREGATOR = re.compile(r"\b(lyrics?|paroles|music group|records|recordings|paradise|vibes|channel|tv|hits|"
                         r"nation|world|zone|planet|music lyrics|traductions?)\b", re.IGNORECASE)


def split_artists(text: str) -> List[str]:
    return [a.strip(" .") for a in _SPLIT_ARTISTS.split(text or "") if a.strip(" .")]


def clean_artist(name: str) -> str:
    """Nom de chaîne YouTube -> nom d'artiste : « Zed Bias - Topic » -> « Zed Bias »,
    « TheWeekndVEVO » -> « TheWeeknd », « Mhd Officiel » -> « Mhd »."""
    out = (name or "").strip()
    for _ in range(2):
        out = _CHANNEL_SUFFIX.sub("", out).strip()
    return out


def looks_like_channel(name: str) -> bool:
    """Chaîne qui n'est probablement pas l'artiste (agrégateur de paroles, label, compilation)."""
    return bool(_AGGREGATOR.search(name or ""))


# 1.3.0 (C25) : identifiant de vidéo YouTube resté dans le titre (« Charger [Om_gqUBQzll] »)
_YT_ID = re.compile(r"\s*[\[\(]([A-Za-z0-9_-]{11})[\]\)]")


def _is_video_id(text: str) -> bool:
    """11 caractères de l'alphabet des identifiants YouTube, avec un chiffre, « _ », « - » ou une majuscule
    au milieu : « Om_gqUBQzll » oui, « Instrumentl » ou « Remastered1 »… non s'il s'agit d'un mot."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return False
    if re.search(r"[0-9_-]", text):
        return not re.fullmatch(r"[A-Za-z]+[0-9]{1,4}", text)          # « Remastered1 » : un mot
    return bool(re.search(r"[A-Z]", text[1:])) and bool(re.search(r"[a-z]", text))


def strip_video_id(title: str) -> str:
    return _YT_ID.sub(lambda m: "" if _is_video_id(m.group(1)) else m.group(0), title or "").strip()


def clean_title(title: str, artist: str = "") -> Tuple[str, List[str], str]:
    """(titre propre, invités trouvés, artiste lu en tête du titre ou "")."""
    text = strip_video_id((title or "").strip())
    feats: List[str] = []

    def take_feat(m: "re.Match[str]") -> str:
        feats.extend(split_artists(m.group(1)))
        return " "

    text = _FEAT.sub(take_feat, text)

    def bracket(m: "re.Match[str]") -> str:
        inner = m.group(1).strip()
        if not inner:
            return ""
        if _KEEP.search(inner):
            return m.group(0)
        return "" if _NOISE.match(inner) else m.group(0)

    text = _BRACKET.sub(bracket, text)
    text = _TAIL_NOISE.sub("", text)
    text = _TAIL_BARE.sub("", text)
    head = ""
    m = re.match(r"^(.{1,60}?)\s+[-–—]\s+(.+)$", text)
    if m:
        left, right = m.group(1).strip(), m.group(2).strip()
        # « Titre - Radio Edit » : la droite est une version, pas un titre -> pas de coupure
        version_only = bool(_KEEP.search(right)) and len(right.split()) <= 3 and not _KEEP.search(left)
        # « Artiste - Titre » : à gauche, l'artiste (presque toujours, quelle que soit la chaîne)
        if not version_only and not _KEEP.search(left):
            head, text = left, right
            # « Artiste1 & Artiste2 - Titre » : le premier est le principal, les autres invités
            names = split_artists(head)
            if len(names) > 1:
                head = names[0]
                feats = names[1:] + feats
    text = re.sub(r"\s{2,}", " ", text).strip(" -–—|")
    return text or (title or "").strip(), list(dict.fromkeys(feats)), head


def join_artists(names: List[str]) -> str:
    out: List[str] = []
    for n in names:
        n = n.strip()
        if n and all(fuzz.ratio(normalize(n), normalize(o)) < 92 for o in out):
            out.append(n)
    return ARTIST_SEP.join(out)


def album_is_noise(album: str, title: str) -> bool:
    """Album qui n'est que le nom de la vidéo (ou du titre) : à remplacer s'il y a mieux."""
    a = (album or "").strip()
    if not a:
        return True
    if fuzz.token_set_ratio(normalize(a), normalize(title)) >= 85:
        return True
    return bool(re.search(_NOISE_WORDS, a, re.IGNORECASE) and (" - " in a or "(" in a))


# --------------------------------------------------------------------------- propositions
FIELDS = ("title", "artist", "album", "year", "genre", "artwork")


@dataclass
class Change:
    field: str
    old: Any
    new: Any
    checked: bool = True


@dataclass
class Proposal:
    content_id: int
    confidence: str                         # "sure" (Deezer) | "rules" (règles seules) | "doubtful"
    changes: List[Change] = field(default_factory=list)
    cover_url: Optional[str] = None         # pochette Deezer proposée
    score: int = 0
    deezer: Dict[str, Any] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.changes

    def change(self, name: str) -> Optional[Change]:
        return next((c for c in self.changes if c.field == name), None)

    def values(self, only_checked: bool = True) -> Dict[str, Any]:
        return {c.field: c.new for c in self.changes if c.checked or not only_checked}


def propose(track: Any, details: Dict[str, Any], deezer: Optional[Dict[str, Any]] = None,
            owned: bool = True) -> Proposal:
    """Proposition pour un son. `deezer` = metadata.match(…) ({} ou None si rien), `owned` = son
    téléchargé par DJSync (propositions cochées par défaut ; sinon décochées, S06)."""
    deezer = deezer or {}
    title, feats, head = clean_title(track.title, track.artist or "")
    sure = bool(deezer.get("sure"))
    channel = track.artist or ""
    if sure and deezer.get("artists"):
        artists = list(deezer["artists"]) + feats
        confidence = "sure"
    else:
        main = head or clean_artist(channel)
        artists = split_artists(main)[:1] + split_artists(main)[1:] + feats if main else feats
        confidence = "doubtful" if (deezer and not sure) or (not head and looks_like_channel(channel)) else "rules"
    new_artist = join_artists(artists) or (channel or "")
    p = Proposal(int(track.content_id), confidence, score=int(deezer.get("score") or 0), deezer=deezer)
    checked = owned and confidence != "doubtful"
    if title and title != (track.title or ""):
        p.changes.append(Change("title", track.title, title, checked))
    if new_artist and new_artist != (track.artist or ""):
        p.changes.append(Change("artist", track.artist or "", new_artist, checked))
    if sure:
        album = details.get("album") or ""
        if deezer.get("album") and deezer["album"] != album and album_is_noise(album, track.title or ""):
            p.changes.append(Change("album", album, deezer["album"], checked))
        if deezer.get("year") and not details.get("year"):
            p.changes.append(Change("year", 0, int(deezer["year"]), checked))
        if deezer.get("genre") and not details.get("genre"):
            p.changes.append(Change("genre", "", deezer["genre"], checked))
        if deezer.get("cover") and not details.get("artwork_path"):
            p.cover_url = deezer["cover"]
            p.changes.append(Change("artwork", None, deezer["cover"], checked))
    return p


# --------------------------------------------------------------------------- suivi
def signature(track: Any) -> str:
    raw = f"{track.title}|{track.artist}|{track.album}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


class ReviewStore:
    """Avancement de la revue d'une bibliothèque, gardé entre deux sessions (S01 : une grosse
    bibliothèque se revoit en plusieurs fois). {son: {state, sig, values}} ; state = validated
    (validé, pas encore enregistré) | ignored | applied. Un son modifié depuis repart à zéro."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        try:
            self.data: Dict[str, Dict[str, Any]] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def state(self, track: Any) -> str:
        entry = self.data.get(str(track.content_id))
        if not entry:
            return ""
        if entry.get("state") == "applied":
            return "applied" if entry.get("sig") == signature(track) else ""
        return entry.get("state", "") if entry.get("sig") == signature(track) else ""

    def values(self, track: Any) -> Dict[str, Any]:
        return dict((self.data.get(str(track.content_id)) or {}).get("values") or {})

    def set(self, track: Any, state: str, values: Optional[Dict[str, Any]] = None) -> None:
        if state:
            self.data[str(track.content_id)] = {"state": state, "sig": signature(track), "values": values or {}}
        else:
            self.data.pop(str(track.content_id), None)
        self.save()

    def mark_applied(self, track_after: Any) -> None:
        self.data[str(track_after.content_id)] = {"state": "applied", "sig": signature(track_after), "values": {}}
        self.save()

    def validated(self) -> List[int]:
        return [int(k) for k, v in self.data.items() if v.get("state") == "validated"]

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass


def needs_review(track: Any) -> bool:
    """1.3.0 (C25) : son « à problèmes » (portée de l'outil depuis l'Accueil) : artiste vide ou nom de
    chaîne, titre avec du bruit (identifiant YouTube, « Official Video », « Artiste - Titre », feat.),
    ou pas de pochette."""
    title = track.title or ""
    artist = track.artist or ""
    if not artist.strip() or looks_like_channel(artist) or clean_artist(artist) != artist:
        return True
    cleaned, feats, head = clean_title(title, artist)
    if cleaned != title.strip() or feats or head:
        return True
    return not getattr(track, "artwork_path", None)
