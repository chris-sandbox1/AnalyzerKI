"""
main.py – Einstiegspunkt des Floorball-Analyzers.

Ablauf:
1. Arbeitsverzeichnis auf Skript-Ordner setzen (wichtig bei Doppelklick)
2. API-Key aus .env-Datei laden
3. YouTube-URL oder lokalen Dateinamen abfragen
4. Video herunterladen (oder lokale Datei verwenden)
5. Videolänge mit ffprobe ermitteln
   - < 35 Min  → direkt analysieren
   - 35–70 Min → Nutzer fragen: in 2 Hälften aufteilen?
   - > 70 Min  → Nutzer fragen: in 3 Perioden aufteilen?
6. Ggf. Video mit ffmpeg schneiden und Teile einzeln analysieren
7. Analyse als JSON in analyses/ speichern
"""

import os
import re
import json
import subprocess
import tempfile
import traceback
from datetime import datetime

from dotenv import load_dotenv
from downloader import download_video
from analyzer import analyze_video

# Arbeitsverzeichnis immer auf den Ordner setzen, in dem main.py liegt.
os.chdir(os.path.dirname(os.path.abspath(__file__)))


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def print_schritt(text: str):
    """Gibt einen Fortschrittsschritt formatiert aus."""
    print(f"\n{'─' * 52}")
    print(f"  {text}")
    print(f"{'─' * 52}")


def beenden(meldung: str = "", fehler: bool = False):
    """Gibt eine Abschlussmeldung aus und wartet auf Enter, bevor das Fenster schließt."""
    if meldung:
        prefix = "\n❌ FEHLER: " if fehler else "\n"
        print(prefix + meldung)
    print("\n" + "─" * 50)
    input("  Drücke Enter zum Beenden...")
    raise SystemExit(1 if fehler else 0)


def sanitize_filename(titel: str) -> str:
    """Erstellt einen sicheren Dateinamen aus dem Videotitel."""
    titel = re.sub(r"[^\w\s-]", "", titel)
    titel = re.sub(r"\s+", "_", titel.strip())
    return titel[:60].lower()


def _repariere_json_main(text: str):
    """
    Versucht abgeschnittenes JSON zu reparieren.
    Gibt das geparste Objekt zurück, oder None bei Misserfolg.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    positionen = [i for i, c in enumerate(text) if c in ('}', ']')]
    for pos in reversed(positionen[-80:]):
        fragment = text[:pos + 1].rstrip().rstrip(',')
        stack = []
        in_str = False
        esc = False
        for ch in fragment:
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == '{':
                stack.append('}')
            elif ch == '[':
                stack.append(']')
            elif ch in '}]' and stack and stack[-1] == ch:
                stack.pop()
        closing = ''.join(reversed(stack))
        try:
            return json.loads(fragment + closing)
        except json.JSONDecodeError:
            continue
    return None


# ── ffprobe / ffmpeg ──────────────────────────────────────────────────────────

def ermittle_videohoehe(video_pfad: str) -> int:
    """
    Gibt die Bildhöhe des Videos in Pixeln zurück (z.B. 1080, 720, 480).
    Gibt -1 zurück, wenn ffprobe nicht verfügbar oder ein Fehler auftritt.
    """
    try:
        ergebnis = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=height",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_pfad,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return int(ergebnis.stdout.strip())
    except FileNotFoundError:
        return -1
    except Exception:
        return -1


def skaliere_auf_480p(quelle: str, ziel: str):
    """
    Skaliert das Video auf max. 480p (Breite bleibt proportional, gerade Zahl).
    Nutzt ffmpeg mit schnellem Software-Encoder (libx264, CRF 23).
    """
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", quelle,
            "-vf", "scale=-2:480",   # Breite automatisch, immer gerade Zahl
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "fast",
            "-c:a", "copy",
            ziel,
        ],
        capture_output=True,
        check=True,
    )


def ermittle_videolange(video_pfad: str) -> float:
    """
    Ermittelt die Videolänge in Sekunden mit ffprobe.
    Gibt -1.0 zurück, wenn ffprobe nicht verfügbar oder ein Fehler auftritt.
    """
    try:
        ergebnis = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_pfad,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(ergebnis.stdout.strip())
    except FileNotFoundError:
        print("  ⚠ ffprobe nicht gefunden – Videoaufteilung nicht möglich.")
        return -1.0
    except Exception as e:
        print(f"  ⚠ ffprobe-Fehler: {e}")
        return -1.0


def schneide_video(quelle: str, start_sek: float, dauer_sek: float, ziel: str):
    """
    Schneidet einen Abschnitt aus dem Video mit ffmpeg (verlustfrei, -c copy).
    """
    subprocess.run(
        [
            "ffmpeg",
            "-y",               # Zieldatei überschreiben
            "-ss", str(start_sek),
            "-i", quelle,
            "-t", str(dauer_sek),
            "-c", "copy",
            ziel,
        ],
        capture_output=True,
        check=True,
    )


def offset_zeitstempel(ts: str, offset_sek: int) -> str:
    """
    Addiert einen Offset (in Sekunden) zu einem MM:SS-Zeitstempel.
    Gibt den neuen Zeitstempel als MM:SS zurück.
    """
    try:
        teile = ts.split(":")
        if len(teile) == 2:
            gesamt = int(teile[0]) * 60 + int(teile[1]) + offset_sek
        elif len(teile) == 3:
            gesamt = int(teile[0]) * 3600 + int(teile[1]) * 60 + int(teile[2]) + offset_sek
        else:
            return ts
        minuten, sekunden = divmod(gesamt, 60)
        return f"{minuten:02d}:{sekunden:02d}"
    except Exception:
        return ts


def zusammenfuehren_analysen(teile: list) -> dict:
    """
    Führt mehrere Teil-Analysen (Dicts) zu einer Gesamt-JSON zusammen.

    teile: Liste von Dicts mit Feldern:
        - "daten": das geparste JSON-Objekt der Teil-Analyse
        - "offset_sek": Zeitversatz in Sekunden für Zeitstempel-Korrektur
        - "label": z.B. "1. Hälfte" für die Zusammenfassung
    """
    gesamt_ereignisse = []
    gesamt_zusammenfassung_teile = []

    stat_keys = [
        "tore_team_a", "tore_team_b",
        "torschuesse_team_a", "torschuesse_team_b",
        "konter_gesamt", "chancen_gesamt",
        "penalties_team_a", "penalties_team_b",
    ]
    gesamt_statistik = {k: 0 for k in stat_keys}

    for teil in teile:
        daten = teil["daten"]
        offset = teil["offset_sek"]
        label = teil.get("label", "")

        # Zusammenfassung sammeln
        zusammenfassung = daten.get("zusammenfassung", "")
        if zusammenfassung:
            prefix = f"[{label}] " if label else ""
            gesamt_zusammenfassung_teile.append(prefix + zusammenfassung)

        # Ereignisse mit Offset versehen
        for ereignis in daten.get("ereignisse", []):
            neu = dict(ereignis)
            if "timestamp" in neu:
                neu["timestamp"] = offset_zeitstempel(neu["timestamp"], offset)
            gesamt_ereignisse.append(neu)

        # Statistiken addieren
        stat = daten.get("statistik", {})
        for k in stat_keys:
            gesamt_statistik[k] += int(stat.get(k, 0))

    return {
        "zusammenfassung": " | ".join(gesamt_zusammenfassung_teile),
        "ereignisse": gesamt_ereignisse,
        "statistik": gesamt_statistik,
    }


# ── Analyse-Steuerung ─────────────────────────────────────────────────────────

def analysiere_direkt(video_pfad: str, api_key: str, periode_info: str = "") -> dict:
    """Analysiert das Video direkt und gibt das geparste JSON-Objekt zurück."""
    roh = analyze_video(video_pfad, api_key, periode_info)
    obj = _repariere_json_main(roh)
    if obj is None:
        return {"rohdaten": roh}
    return obj


def analysiere_mit_aufteilung(
    video_pfad: str,
    api_key: str,
    gesamtlaenge_sek: float,
    anzahl_teile: int,
) -> dict:
    """
    Schneidet das Video in `anzahl_teile` gleiche Abschnitte,
    analysiert jeden Teil separat und führt die Ergebnisse zusammen.
    """
    dauer_pro_teil = gesamtlaenge_sek / anzahl_teile
    labels = {
        2: ["1. Hälfte", "2. Hälfte"],
        3: ["1. Periode", "2. Periode", "3. Periode"],
    }
    teil_labels = labels.get(anzahl_teile, [f"Teil {i+1}" for i in range(anzahl_teile)])

    # Kontext-Texte: Teams wechseln nach der Hälfte die Seiten
    SEITENWECHSEL_HINWEIS = (
        "WICHTIG: Der Videoschnitt erfolgte zeitbasiert und trifft den echten Seitenwechsel "
        "möglicherweise nicht exakt. Achte daher aktiv auf visuelle Hinweise im Video, ob und "
        "wann die Teams die Seiten wechseln (z.B. Bully in der Mitte, Teams laufen in neue "
        "Richtung). Passe deine Angriffsrichtungs-Annahme entsprechend an, falls du einen "
        "Seitenwechsel erkennst."
    )

    def periode_kontext(i: int) -> str:
        label = teil_labels[i]
        if anzahl_teile == 2:
            if i == 0:
                basis = (
                    f"Dies ist die {label} (1 von 2). "
                    "Zu Beginn dieses Abschnitts greift Team A wahrscheinlich nach rechts "
                    "(Tor bei x=40), Team B nach links (Tor bei x=0)."
                )
            else:
                basis = (
                    f"Dies ist die {label} (2 von 2). "
                    "Zu Beginn dieses Abschnitts haben die Teams wahrscheinlich bereits die "
                    "Seiten gewechselt: Team A greift nach links (Tor bei x=0), "
                    "Team B nach rechts (Tor bei x=40)."
                )
        elif anzahl_teile == 3:
            seiten = [
                (f"Dies ist die {label} (1 von 3). "
                 "Zu Beginn greift Team A wahrscheinlich nach rechts (Tor bei x=40), "
                 "Team B nach links (Tor bei x=0)."),
                (f"Dies ist die {label} (2 von 3). "
                 "Zu Beginn haben die Teams wahrscheinlich die Seiten gewechselt: "
                 "Team A greift nach links (Tor bei x=0), Team B nach rechts (Tor bei x=40)."),
                (f"Dies ist die {label} (3 von 3). "
                 "Zu Beginn hat ein erneuter Seitenwechsel stattgefunden: "
                 "Team A greift wahrscheinlich wieder nach rechts (Tor bei x=40), "
                 "Team B nach links (Tor bei x=0)."),
            ]
            basis = seiten[i]
        else:
            basis = f"Dies ist {label}."
        return f"{basis} {SEITENWECHSEL_HINWEIS}"

    teile_ergebnisse = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        for i in range(anzahl_teile):
            label = teil_labels[i]
            start = i * dauer_pro_teil
            offset_sek = int(start)

            print_schritt(f"Schritt {i+1}/{anzahl_teile}: {label} analysieren")

            # Video-Abschnitt schneiden
            teil_pfad = os.path.join(tmp_dir, f"teil_{i+1}.mp4")
            print(f"  Schneide {label} ({int(start//60):02d}:{int(start%60):02d} – "
                  f"{int((start+dauer_pro_teil)//60):02d}:{int((start+dauer_pro_teil)%60):02d})...")
            try:
                schneide_video(video_pfad, start, dauer_pro_teil, teil_pfad)
            except subprocess.CalledProcessError as e:
                beenden(f"ffmpeg-Fehler beim Schneiden von {label}: {e}", fehler=True)

            # Teil analysieren
            kontext = periode_kontext(i)
            print(f"  Analyse startet (Kontext: {kontext[:60]}...)")
            try:
                daten = analysiere_direkt(teil_pfad, api_key, kontext)
            except Exception as fehler:
                print(traceback.format_exc())
                beenden(f"Analyse von {label} fehlgeschlagen: {fehler}", fehler=True)

            teile_ergebnisse.append({
                "daten": daten,
                "offset_sek": offset_sek,
                "label": label,
            })

    print_schritt("Zusammenführen der Teil-Analysen")
    return zusammenfuehren_analysen(teile_ergebnisse)


# ── Speichern ─────────────────────────────────────────────────────────────────

def speichere_analyse(analyse_obj: dict, video_titel: str) -> str:
    """Speichert die Analyse-JSON in den analyses/-Ordner und aktualisiert den Index."""
    os.makedirs("analyses", exist_ok=True)

    datum = datetime.now().strftime("%Y%m%d")
    sicherer_titel = sanitize_filename(video_titel)
    dateiname = f"{sicherer_titel}_{datum}.json"
    pfad = os.path.join("analyses", dateiname)

    # Falls Datei schon existiert (zweite Analyse am selben Tag), Zähler anhängen
    zaehler = 1
    while os.path.exists(pfad):
        dateiname = f"{sicherer_titel}_{datum}_{zaehler}.json"
        pfad = os.path.join("analyses", dateiname)
        zaehler += 1

    analyse_obj["_meta"] = {
        "videotitel": video_titel,
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "dateiname": dateiname,
    }

    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(analyse_obj, f, ensure_ascii=False, indent=2)

    aktualisiere_index()
    return pfad


def aktualisiere_index():
    """Schreibt analyses/index.json (Server-Modus) und analyses/data.js (file://-Modus)."""
    ordner = "analyses"
    eintraege = []
    alle_spiele = {}

    for datei in sorted(os.listdir(ordner)):
        if not datei.endswith(".json") or datei == "index.json":
            continue
        try:
            with open(os.path.join(ordner, datei), encoding="utf-8") as f:
                daten = json.load(f)
            meta = daten.get("_meta", {})
            eintraege.append({
                "datei": datei,
                "titel": meta.get("videotitel", datei),
                "datum": meta.get("datum", ""),
            })
            alle_spiele[datei] = daten
        except Exception:
            eintraege.append({"datei": datei, "titel": datei, "datum": ""})

    eintraege.reverse()  # Neueste zuerst

    with open(os.path.join(ordner, "index.json"), "w", encoding="utf-8") as f:
        json.dump(eintraege, f, ensure_ascii=False, indent=2)

    inhalt = (
        "// Automatisch generiert von main.py – nicht manuell bearbeiten\n"
        "window.FLOORBALL_DATA = "
        + json.dumps({"index": eintraege, "spiele": alle_spiele}, ensure_ascii=False)
        + ";\n"
    )
    with open(os.path.join(ordner, "data.js"), "w", encoding="utf-8") as f:
        f.write(inhalt)


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def main():
    # .env laden
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or api_key.startswith("dein-"):
        beenden(
            "Kein gültiger Gemini API-Key gefunden.\n"
            "  Bitte trage deinen Key in die .env-Datei ein:\n"
            "  GEMINI_API_KEY=dein-echter-key",
            fehler=True,
        )

    print("=" * 52)
    print("   🏒  Floorball Video Analyzer")
    print("=" * 52)
    print("\nEingabe: YouTube-URL  ODER  Dateiname aus dem")
    print("downloads-Ordner (z.B. 'Sweden vs Finland.mp4')\n")

    eingabe = input("URL oder Dateiname: ").strip()
    if not eingabe:
        beenden("Keine Eingabe erhalten.", fehler=True)

    print()

    # ── Schritt 1: Video besorgen ──────────────────────────────────────────────
    if eingabe.startswith("http://") or eingabe.startswith("https://"):
        print_schritt("Schritt 1: Video herunterladen")
        try:
            video_pfad, video_titel = download_video(eingabe)
        except Exception as fehler:
            print(traceback.format_exc())
            beenden(f"Download fehlgeschlagen: {fehler}", fehler=True)
    else:
        if os.path.isabs(eingabe) and os.path.exists(eingabe):
            video_pfad = eingabe
        else:
            video_pfad = os.path.join("downloads", eingabe)

        if not os.path.exists(video_pfad):
            hinweis = f"Datei nicht gefunden: {video_pfad}"
            if os.path.exists("downloads"):
                dateien = [
                    f for f in os.listdir("downloads")
                    if f.endswith((".mp4", ".webm", ".mkv"))
                ]
                if dateien:
                    hinweis += "\n\nVerfügbare Dateien im downloads-Ordner:"
                    for d in dateien:
                        hinweis += f"\n  • {d}"
            beenden(hinweis, fehler=True)

        video_titel = os.path.splitext(os.path.basename(eingabe))[0]

    print()

    # ── Schritt 2: Auflösung prüfen und ggf. auf 480p skalieren ──────────────
    print_schritt("Schritt 2: Auflösung prüfen")
    hoehe = ermittle_videohoehe(video_pfad)
    skaliert_tmp = None  # Pfad zur temporären skalierten Datei (falls erstellt)

    if hoehe > 480:
        print(f"  Auflösung: {hoehe}p → wird auf 480p skaliert (spart Upload-Zeit)")
        skaliert_tmp = os.path.join(
            tempfile.gettempdir(),
            f"fb_480p_{os.path.basename(video_pfad)}",
        )
        try:
            skaliere_auf_480p(video_pfad, skaliert_tmp)
            analyse_pfad = skaliert_tmp
            print("  Skalierung abgeschlossen.")
        except subprocess.CalledProcessError as e:
            print(f"  ⚠ Skalierung fehlgeschlagen, nutze Originaldatei. ({e})")
            analyse_pfad = video_pfad
            skaliert_tmp = None
    elif hoehe > 0:
        print(f"  Auflösung: {hoehe}p → bereits ≤ 480p, keine Skalierung nötig.")
        analyse_pfad = video_pfad
    else:
        print("  Auflösung konnte nicht ermittelt werden (ffprobe fehlt?), nutze Originaldatei.")
        analyse_pfad = video_pfad

    # ── Schritt 3: Videolänge ermitteln ───────────────────────────────────────
    print_schritt("Schritt 3: Videolänge ermitteln")
    laenge_sek = ermittle_videolange(analyse_pfad)

    if laenge_sek > 0:
        laenge_min = laenge_sek / 60
        print(f"  Videolänge: {int(laenge_min)} Min {int(laenge_sek % 60)} Sek")
    else:
        laenge_min = 0

    # ── Schritt 4: Analyse ────────────────────────────────────────────────────
    analyse_obj: dict

    try:
        if laenge_sek <= 0 or laenge_min < 35:
            # Kurzes Video oder ffprobe nicht verfügbar → direkt analysieren
            if laenge_sek > 0:
                print(f"  Kurzes Video (< 35 Min) → direkte Analyse")
            print_schritt("Schritt 4: Video analysieren")
            analyse_obj = analysiere_direkt(analyse_pfad, api_key)

        elif laenge_min < 70:
            # Mittleres Video: 35–70 Min → Nutzer fragen
            print(f"  Video ist {int(laenge_min)} Minuten lang.")
            antwort = input("  Aufteilen in 2 Hälften für bessere Analyse? (j/n): ").strip().lower()
            if antwort == "j":
                analyse_obj = analysiere_mit_aufteilung(analyse_pfad, api_key, laenge_sek, 2)
            else:
                print_schritt("Schritt 4: Video analysieren (ohne Aufteilung)")
                analyse_obj = analysiere_direkt(analyse_pfad, api_key)

        else:
            # Langes Video: > 70 Min → Nutzer fragen
            print(f"  Video ist {int(laenge_min)} Minuten lang.")
            antwort = input("  Aufteilen in 3 Perioden für bessere Analyse? (j/n): ").strip().lower()
            if antwort == "j":
                analyse_obj = analysiere_mit_aufteilung(analyse_pfad, api_key, laenge_sek, 3)
            else:
                print_schritt("Schritt 4: Video analysieren (ohne Aufteilung)")
                analyse_obj = analysiere_direkt(analyse_pfad, api_key)

    except Exception as fehler:
        print(traceback.format_exc())
        beenden(f"Analyse fehlgeschlagen: {fehler}", fehler=True)
    finally:
        # Temporäre skalierte Datei aufräumen
        if skaliert_tmp and os.path.exists(skaliert_tmp):
            try:
                os.remove(skaliert_tmp)
            except Exception:
                pass

    # ── Schritt 5: Ergebnis anzeigen ──────────────────────────────────────────
    print_schritt("Analyse abgeschlossen – Vorschau:")
    vorschau = json.dumps(analyse_obj, ensure_ascii=False, indent=2)
    print(vorschau[:800] + ("…" if len(vorschau) > 800 else ""))

    # ── Schritt 6: Analyse speichern ──────────────────────────────────────────
    try:
        gespeichert_unter = speichere_analyse(analyse_obj, video_titel)
        print("\n" + "=" * 52)
        print(f"✓ Gespeichert: {gespeichert_unter}")
        print("  → Im Dashboard unter 'Gespeicherte Spiele' verfügbar")
    except Exception as fehler:
        print(traceback.format_exc())
        print(f"\n⚠ Warnung: Speichern fehlgeschlagen: {fehler}")

    beenden()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except Exception:
        print("\n" + "=" * 52)
        print("UNERWARTETER FEHLER:")
        print("=" * 52)
        traceback.print_exc()
        input("\nDrücke Enter zum Beenden...")
