# PyInstaller : pyinstaller packaging/DJSync.spec   (à lancer sous WINDOWS, depuis la racine du projet)
# Produit dist/DJSync.exe, un seul fichier. Copiez-le sur la clé (racine ou dossier DJSync/) avec :
#   tools/ffmpeg.exe, tools/ffprobe.exe, tools/deno.exe   (à côté de l'exe : ajoutés au PATH au démarrage)
# NON TESTÉ dans l'environnement de développement de cette livraison (pas de Windows) : à valider.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hidden = [], [], []
for pkg in ("customtkinter", "yt_dlp", "ytmusicapi", "sqlcipher3", "pygame", "mutagen"):   # numpy : hook PyInstaller natif
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h

a = Analysis(["../app.py"], pathex=[".."], binaries=binaries, datas=datas, hiddenimports=hidden)
pyz = PYZ(a.pure)
# Icône de l'exe : logo DJSync à la couleur par défaut (générée par tools/export_logos.py)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="DJSync", console=False, upx=False,
          icon="djsync.ico")
