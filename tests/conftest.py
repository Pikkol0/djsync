"""Tests d'interface Qt sans écran : plateforme « offscreen » (aucun Xvfb nécessaire)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
