import pytest

from djsync.core.camelot import are_compatible, neighbors, read_file_key, to_camelot


@pytest.mark.parametrize("raw, expected", [
    ("Am", "8A"), ("A minor", "8A"), ("Amin", "8A"), ("C", "8B"), ("Cmaj", "8B"), ("CM", "8B"), ("Cm", "5A"),
    ("F#", "2B"), ("F♯ minor", "11A"), ("Gb", "2B"), ("Bbm", "3A"), ("A#m", "3A"), ("Dbmaj", "3B"),
    ("G#m", "1A"), ("Abm", "1A"), ("E major", "12B"), ("bm", "10A"),
    ("8A", "8A"), ("08b", "8B"), ("12a", "12A"), ("1d", "8B"), ("1m", "8A"), ("2d", "9B"),
    (" am ", "8A"),
])
def test_to_camelot(raw, expected):
    assert to_camelot(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "  ", "xyz", "H", "13A", "0A", "Hm", "C dorian"])
def test_to_camelot_unknown(raw):
    assert to_camelot(raw) is None


def test_every_pitch_class_is_covered_exactly_once():
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    major = {to_camelot(n) for n in names}
    minor = {to_camelot(n + "m") for n in names}
    assert len(major) == 12 and len(minor) == 12
    assert major == {f"{i}B" for i in range(1, 13)} and minor == {f"{i}A" for i in range(1, 13)}


def test_neighbors_wrap_and_relative():
    assert neighbors("8A") == ["8A", "7A", "9A", "8B"]
    assert neighbors("1B") == ["1B", "12B", "2B", "1A"]
    assert neighbors("12A") == ["12A", "11A", "1A", "12B"]
    assert neighbors("nope") == []
    assert are_compatible("Am", "C") and are_compatible("8A", "9A") and not are_compatible("Am", "F#m")


def test_read_file_key_from_id3(tmp_path):
    from mutagen.id3 import ID3, TKEY
    from mutagen.mp3 import MP3  # noqa: F401

    f = tmp_path / "a.mp3"
    # trame MPEG minimale valide (silence)
    f.write_bytes((b"\xff\xfb\x90\x00" + b"\x00" * 413) * 8)
    tags = ID3()
    tags.add(TKEY(encoding=3, text="Am"))
    tags.save(str(f))
    assert read_file_key(str(f)) == "Am"
    assert read_file_key(str(tmp_path / "missing.mp3")) is None
