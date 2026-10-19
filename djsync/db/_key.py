"""Clé commune des bases OneLibrary (exportLibrary.db), reconstruite à l'exécution.

Cette clé est la même pour toutes les clés USB Rekordbox : elle n'est liée ni à
votre licence ni à votre machine. Les deux constantes ci-dessous (blob obfusqué +
clé XOR) et l'algorithme de décodage proviennent du projet open source
pyrekordbox (MIT, Dylan Jones) : https://github.com/dylanljones/pyrekordbox
Elles sont recopiées ici pour ne pas embarquer pyrekordbox (SQLAlchemy, numpy...)
dans l'exécutable : DJSync reste léger.
"""
import base64
import zlib

_BLOB = b'PN_1dH8$oLJY)16j_RvM6qphWw`476>;C1cWmI#se(PG`j}~xAjlufj?`#0i{;=glh(SkW)y0>n?YEiD`l%t('
_BLOB_KEY = b'657f48f84c437cc1'


def get_default_key() -> str:
    """Décode la clé SQLCipher par défaut (Base85 -> XOR -> zlib -> UTF-8)."""
    data = base64.b85decode(_BLOB)
    xored = bytes(b ^ _BLOB_KEY[i % len(_BLOB_KEY)] for i, b in enumerate(data))
    return zlib.decompress(xored).decode("utf-8")
