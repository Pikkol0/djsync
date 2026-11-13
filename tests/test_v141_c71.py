"""1.4.1 (C71) : « Proposer des cues » sur les vraies parties du son."""
from __future__ import annotations

import numpy as np

from djsync.analysis import sections
from djsync.analysis.cues import Cue, suggest_cues


def _song(parts, bpm=120.0, sr=22050, seed=0):
    """Parties (nombre de mesures, niveau des basses, niveau des aigus) ; grille à `bpm`, 4 temps."""
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    out, beats, t0 = [], [], 0.0
    for bars, bass, high in parts:
        n = int(bars * 4 * beat * sr)
        tt = np.arange(n) / sr
        sig = bass * np.sin(2 * np.pi * 55 * tt) * (0.5 + 0.5 * np.cos(2 * np.pi * tt / beat))
        sig += high * rng.normal(0, 1, n) * 0.3
        out.append(sig.astype(np.float32))
    x = np.concatenate(out)
    k = 0
    while k * beat * 1000 < x.size / sr * 1000:
        beats.append(((k % 4) + 1, int(bpm * 100), int(round(k * beat * 1000))))
        k += 1
    return x, sr, beats


def test_changes_of_part_are_found_on_the_bar():
    x, sr, beats = _song([(16, 0.05, 0.2), (16, 0.8, 0.6), (8, 0.05, 0.6), (16, 0.9, 0.9)])
    ms, clear = sections.propose_ms(x, sr, beats)
    bar = 2000                                                        # 120 BPM : une mesure = 2 s
    found = sorted(round(m / bar) for m in ms)
    assert clear and found[0] == 0                                    # A sur le premier temps de la grille
    for want in (16, 32, 40):                                         # les trois changements, à une mesure près
        assert any(abs(f - want) <= 1 for f in found), found
    assert all(m % bar == 0 for m in ms)                              # toujours au début d'une mesure
    assert all(b - a >= sections.MIN_GAP_BARS for a, b in zip(found, found[1:]))


def test_no_clear_change_gives_a_only():
    x, sr, beats = _song([(48, 0.5, 0.5)], seed=3)
    ms, clear = sections.propose_ms(x, sr, beats)
    assert not clear and ms == [0]


def test_free_pads_only_and_no_duplicate_near_a_hot_cue():
    beats = [((i % 4) + 1, 12000, i * 500) for i in range(400)]       # 120 BPM
    existing = [Cue(1, 0), Cue(0, 32000), Cue(3, 64100)]              # A, une mémoire, C à 64,1 s
    got = suggest_cues(beats, existing, positions=[0, 32000, 64000, 96000])
    assert [c.slot for c in got] == [2, 4]                            # pads libres : B puis D
    assert [c.ms for c in got] == [32000, 96000]                      # 0 (A) et 64000 (C à 100 ms) écartés
    full = [Cue(s, s * 1000) for s in range(1, 9)]
    assert suggest_cues(beats, full, positions=[50000]) == []
