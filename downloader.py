"""
downloader.py – Lädt ein YouTube-Video herunter und speichert es lokal.
Genutzte Bibliothek: yt-dlp
"""

import yt_dlp
import os


def download_video(url: str, zielordner: str = "downloads") -> tuple:
    """
    Lädt ein YouTube-Video herunter.

    Parameter:
        url: Die YouTube-URL des Videos
        zielordner: Ordner, in dem das Video gespeichert wird (Standard: 'downloads')

    Rückgabe:
        Tupel: (Pfad zur Videodatei, Originaltitel des Videos)
    """

    # Sicherstellen, dass der Zielordner existiert
    os.makedirs(zielordner, exist_ok=True)

    # Pfad für die gespeicherte Datei
    ausgabepfad = os.path.join(zielordner, "%(title)s.%(ext)s")

    # Einstellungen für yt-dlp
    optionen = {
        "format": "mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",  # MP4 bevorzugen
        "outtmpl": ausgabepfad,       # Dateiname-Vorlage
        "quiet": False,               # Fortschritt anzeigen
        "noplaylist": True,           # Nur einzelnes Video, keine Playlist
    }

    print(f"Lade Video herunter: {url}")

    # Dateiname nach dem Download ermitteln
    with yt_dlp.YoutubeDL(optionen) as ydl:
        info = ydl.extract_info(url, download=True)
        dateiname = ydl.prepare_filename(info)

        # Falls yt-dlp die Endung geändert hat (z.B. .webm statt .mp4)
        if not os.path.exists(dateiname):
            # Alternativen suchen
            basis = os.path.splitext(dateiname)[0]
            for endung in [".mp4", ".webm", ".mkv"]:
                kandidat = basis + endung
                if os.path.exists(kandidat):
                    dateiname = kandidat
                    break

    print(f"Video gespeichert unter: {dateiname}")
    # Videotitel aus den Metadaten (Fallback: Dateiname ohne Endung)
    titel = info.get("title", os.path.splitext(os.path.basename(dateiname))[0])
    return dateiname, titel
