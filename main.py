"""
main.py – Einstiegspunkt des Floorball-Analyzers.

Ablauf:
1. API-Key aus .env-Datei laden
2. YouTube-URL oder lokalen Dateinamen abfragen
3. Video herunterladen (oder lokale Datei verwenden)
4. Video mit Gemini analysieren
5. Analyse als JSON in analyses/ speichern
6. Ergebnis anzeigen
"""

import os
import re
import json
from datetime import datetime
from dotenv import load_dotenv
from downloader import download_video
from analyzer import analyze_video


def sanitize_filename(titel: str) -> str:
    """Erstellt einen sicheren Dateinamen aus dem Videotitel."""
    titel = re.sub(r"[^\w\s-]", "", titel)       # Sonderzeichen entfernen
    titel = re.sub(r"\s+", "_", titel.strip())    # Leerzeichen → Unterstriche
    return titel[:60].lower()                      # Max 60 Zeichen, Kleinbuchstaben


def speichere_analyse(analyse_text: str, video_titel: str) -> str:
    """
    Speichert die Analyse-JSON in den analyses/-Ordner und
    aktualisiert analyses/index.json.

    Rückgabe: Pfad zur gespeicherten Datei
    """
    os.makedirs("analyses", exist_ok=True)

    datum = datetime.now().strftime("%Y%m%d")
    sicherer_titel = sanitize_filename(video_titel)
    dateiname = f"{sicherer_titel}_{datum}.json"
    pfad = os.path.join("analyses", dateiname)

    # Falls Datei schon existiert (z.B. zweite Analyse am selben Tag), Zähler anhängen
    zaehler = 1
    while os.path.exists(pfad):
        dateiname = f"{sicherer_titel}_{datum}_{zaehler}.json"
        pfad = os.path.join("analyses", dateiname)
        zaehler += 1

    # Sicherheits-Bereinigung: falls analyzer.py den ```json-Block nicht entfernt hat
    bereinigt = analyse_text.strip()
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", bereinigt)
    if json_match:
        bereinigt = json_match.group(1).strip()
    else:
        start = bereinigt.find("{")
        end   = bereinigt.rfind("}") + 1
        if start != -1 and end > start:
            bereinigt = bereinigt[start:end]

    # JSON parsen und Metadaten ergänzen (Titel, Datum)
    try:
        daten = json.loads(bereinigt)
    except json.JSONDecodeError:
        daten = {"rohdaten": analyse_text}  # echter Fallback: Rohtext aufbewahren

    daten["_meta"] = {
        "videotitel": video_titel,
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "dateiname": dateiname,
    }

    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)

    # Index aktualisieren
    aktualisiere_index()

    return pfad


def aktualisiere_index():
    """
    Schreibt analyses/index.json (für Server-Modus) und
    analyses/data.js (für direktes Öffnen per Doppelklick ohne Server).

    data.js enthält alle Spieldaten als JavaScript-Variable, die der Browser
    auch über file://-Protokoll laden kann — fetch() würde dort geblockt werden.
    """
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
                "datei":  datei,
                "titel":  meta.get("videotitel", datei),
                "datum":  meta.get("datum", ""),
            })
            alle_spiele[datei] = daten
        except Exception:
            eintraege.append({"datei": datei, "titel": datei, "datum": ""})

    eintraege.reverse()  # Neueste zuerst

    # index.json (für start.py / Server-Modus)
    with open(os.path.join(ordner, "index.json"), "w", encoding="utf-8") as f:
        json.dump(eintraege, f, ensure_ascii=False, indent=2)

    # data.js (für direktes Öffnen ohne Server — <script src> funktioniert mit file://)
    inhalt = (
        "// Automatisch generiert von main.py – nicht manuell bearbeiten\n"
        "window.FLOORBALL_DATA = "
        + json.dumps({"index": eintraege, "spiele": alle_spiele}, ensure_ascii=False)
        + ";\n"
    )
    with open(os.path.join(ordner, "data.js"), "w", encoding="utf-8") as f:
        f.write(inhalt)


def main():
    # .env-Datei laden (enthält den API-Key)
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or api_key == "dein-api-key-hier":
        print("FEHLER: Kein gültiger Gemini API-Key gefunden.")
        print("Bitte trage deinen API-Key in die .env-Datei ein:")
        print("  GEMINI_API_KEY=dein-echter-key")
        return

    print("=== Floorball Video Analyzer ===\n")
    print("Eingabe: YouTube-URL  ODER  Dateiname aus dem downloads-Ordner (z.B. 'Sweden vs Finland.mp4')")

    eingabe = input("\nURL oder Dateiname: ").strip()
    if not eingabe:
        print("Keine Eingabe. Programm wird beendet.")
        return

    print()

    # ── Schritt 1: Video besorgen ──────────────────────────────────────────────
    if eingabe.startswith("http://") or eingabe.startswith("https://"):
        # YouTube-Download
        try:
            video_pfad, video_titel = download_video(eingabe)
        except Exception as fehler:
            print(f"\nFEHLER beim Herunterladen: {fehler}")
            return
    else:
        # Lokale Datei aus downloads/
        video_pfad = os.path.join("downloads", eingabe)
        if not os.path.exists(video_pfad):
            print(f"FEHLER: Datei nicht gefunden: {video_pfad}")
            if os.path.exists("downloads"):
                dateien = [f for f in os.listdir("downloads") if f.endswith((".mp4", ".webm", ".mkv"))]
                if dateien:
                    print("Verfügbare Dateien:")
                    for d in dateien:
                        print(f"  - {d}")
            return
        # Titel = Dateiname ohne Endung
        video_titel = os.path.splitext(eingabe)[0]

    print()

    # ── Schritt 2: Analyse ────────────────────────────────────────────────────
    try:
        analyse = analyze_video(video_pfad, api_key)
    except Exception as fehler:
        print(f"\nFEHLER bei der Analyse: {fehler}")
        return

    # ── Schritt 3: Ergebnis anzeigen ──────────────────────────────────────────
    print("\n" + "=" * 50)
    print("ANALYSE-ERGEBNIS:")
    print("=" * 50)
    print(analyse)
    print("=" * 50)

    # ── Schritt 4: Analyse speichern ──────────────────────────────────────────
    try:
        gespeichert_unter = speichere_analyse(analyse, video_titel)
        print(f"\n✓ Analyse gespeichert: {gespeichert_unter}")
        print("  → Im Dashboard unter 'Gespeicherte Spiele' verfügbar")
    except Exception as fehler:
        print(f"\nWarnung: Analyse konnte nicht gespeichert werden: {fehler}")


if __name__ == "__main__":
    main()
