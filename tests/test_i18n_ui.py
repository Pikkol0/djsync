"""V0.2.0 / V0.2.1 : le logiciel est en anglais ; les autres langues passent par l'i18n.

  * aucune chaîne française « en dur » dans djsync/ (messages, exceptions, journaux, lignes de
    commande) : seules les docstrings, les commentaires et le catalogue i18n/fr.py sont exclus ;
  * chaque clé utilisée existe en anglais ET en français, avec les mêmes paramètres {…}.
"""
import ast
import re
import string
from pathlib import Path

import pytest

from djsync.i18n import en, fr

UI = Path(__file__).resolve().parent.parent / "djsync" / "ui"
PKG = UI.parent
FRENCH = re.compile(r"[éèêàùçôîûœ«»]|\b(le|la|les|des|une|aucun|aucune|cliquez|clé|sons?|enregistrer|"
                    r"supprimer|télécharg\w*|playlist intelligente)\b", re.I)
KEY_CALL = re.compile(r'''\b(?:t|plural)\(\s*"([a-z_]+\.[a-zA-Z0-9_]+)"(?:\s*,\s*"([a-z_]+\.[a-zA-Z0-9_]+)")?''')
ALLOWED = {"Segoe UI", "Contents", "DJSync", "FFmpeg", "YouTube Music", "Spotify · YouTube · SoundCloud", "BPM",
           "export.pdb", "Français", r"^(\d+(?:[.,]\d+)?)\s*([a-zà-ÿ]+)?"}
# mots français fréquents dans un message : repère les oublis hors interface (journaux, exceptions)
FRENCH_WORDS = re.compile(r"\b(introuvable|impossible|fichier|aucune?|clé|sons?|dans|avec|sans|erreur|lecture|"
                          r"illisible|déjà|ligne|réglages|platines?)\b", re.I)


def _docstrings(tree: ast.AST) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def _logging_args(tree: ast.AST) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                isinstance(node.func.value, ast.Name) and node.func.value.id in ("log", "logging"):
            for arg in node.args:
                for sub in ast.walk(arg):
                    out.add(id(sub))
    return out


def test_no_hard_coded_french_in_the_interface():
    offenders = []
    for path in sorted(UI.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
                text = node.value
                if text in ALLOWED or not text.strip():
                    continue
                if FRENCH.search(text):
                    offenders.append(f"{path.relative_to(UI)}:{node.lineno}: {text[:60]!r}")
    assert not offenders, "Textes à passer par t() :\n" + "\n".join(offenders)


def test_whole_package_is_english_exceptions_and_logs_included():
    offenders = []
    for path in sorted(PKG.rglob("*.py")):
        if path.name == "fr.py" and path.parent.name == "i18n":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
                text = node.value
                if text in ALLOWED or not text.strip():
                    continue
                if re.search(r"[éèêàùçôîûœ«»]", text) or FRENCH_WORDS.search(text):
                    offenders.append(f"{path.relative_to(PKG)}:{node.lineno}: {text[:60]!r}")
    assert not offenders, "Textes français hors i18n :\n" + "\n".join(offenders)


def _fields(text: str) -> set:
    return {name.split(":")[0] for _lit, name, _spec, _conv in string.Formatter().parse(text) if name}


def test_every_used_key_exists_in_both_languages_with_same_fields():
    used = set()
    for path in (UI.parent).rglob("*.py"):
        for m in KEY_CALL.finditer(path.read_text(encoding="utf-8")):
            used.update(k for k in m.groups() if k)
    used.discard("lib.tracks")                      # exemple dans une docstring
    assert not sorted(used - set(en.STRINGS)), sorted(used - set(en.STRINGS))
    assert set(en.STRINGS) == set(fr.STRINGS), set(en.STRINGS) ^ set(fr.STRINGS)
    bad = [k for k in en.STRINGS if _fields(en.STRINGS[k]) != _fields(fr.STRINGS[k])]
    assert not bad, bad
    # t(key, **params) : un paramètre nommé « key » entrerait en conflit avec l'argument
    assert not [k for k in en.STRINGS if "key" in _fields(en.STRINGS[k])]


def test_dynamic_keys_exist():
    for mode in ("auto", "on", "off"):
        assert f"settings.sidebar_{mode}" in en.STRINGS
    for notation in ("auto", "camelot", "musical"):
        assert f"settings.notation_{notation}" in en.STRINGS
    pytest.importorskip("PySide6")
    from djsync.ui.help_dialog import SHORTCUTS, TOPICS

    for key in [k for _keys, k in SHORTCUTS] + TOPICS + [k + "_title" for k in TOPICS]:
        assert key in en.STRINGS and key in fr.STRINGS, key
