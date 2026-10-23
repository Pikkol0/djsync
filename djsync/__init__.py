"""DJSync - Gestionnaire de bibliothèque musicale pour clés USB Rekordbox."""

__version__ = "1.2.3"

try:                       # écrit par le workflow de build : version exacte publiée (ex. « 1.2.0-rc.4 »)
    from ._build_version import VERSION as BUILD_VERSION
except ImportError:        # depuis les sources
    BUILD_VERSION = ""


def full_version() -> str:
    """Version complète de CET exécutable : « 1.2.0-rc.4 » pour une version de test (la vérification
    des mises à jour en dépend : une 1.2.0-rc.3 doit se voir proposer la rc.4), sinon `__version__`.
    1.2.0-rc.4 : avant, une version de test se croyait en 1.2.0 et ne voyait jamais les suivantes."""
    return BUILD_VERSION or __version__
