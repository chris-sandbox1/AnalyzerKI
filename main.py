"""
main.py – Einstiegspunkt des Floorball-Analyzers.

Ablauf:
1. Arbeitsverzeichnis auf Skript-Ordner setzen (wichtig bei Doppelklick)
2. API-Key aus .env-Datei laden
3. YouTube-URL oder lokalen Dateinamen abfragen
4. Video herunterladen (oder lokale Datei verwenden)
5. Video mit Gemini analysieren
6. Analyse als JSON in analyses/ speichern
"""

import os
import re
import json
import traceback
from datetime import datetime
from dotenv import load_dotenv
from downloader import download_video
from analyzer import analyze_video

# Arbeitsverzeichnis immer auf den Ordner setzen, in dem main.py liegt.
# Ohne das schlagen alle relativen Pfade (downloads/, analyses/, .env) fehl,
# wenn das Skript per Doppelklick oder aus einem anderen Ordner gestartet wird.
os.chdir(os.path.dirname(os.path.abspath(__file__)))


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


def speichere_analyse(analyse_text: str, video_titel: str) -> str:
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

    # Markdown-Wrapper entfernen (```json ... ```) – greedy Match für tief verschachteltes JSON
    bereinigt = analyse_text.strip()
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", bereinigt)
    if json_match:
        bereinigt = json_match.group(1).strip()
    else:
        start = bereinigt.find("{")
        end   = bereinigt.rfind("}") + 1
        if start != -1 and end > start:
            bereinigt = bereinigt[start:end]

    # JSON parsen und Metadaten ergänzen
    try:
        daten = json.loads(bereinigt)
    except json.JSONDecodeError:
        daten = {"rohdaten": analyse_text}

    daten["_meta"] = {
        "videotitel": video_titel,
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "dateiname": dateiname,
    }

    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)

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


def main():
    # .env aus dem Skript-Ordner laden (Pfad ist durch os.chdir oben bereits korrekt)
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
        print("↓  Lade Video herunter…")
        try:
            video_pfad, video_titel = download_video(eingabe)
        except Exception as fehler:
            print(traceback.format_exc())
            beenden(f"Download fehlgeschlagen: {fehler}", fehler=True)
    else:
        # Lokale Datei — auch direkte Vollpfade akzeptieren
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

    # ── Schritt 2: Analyse ────────────────────────────────────────────────────
    try:
        analyse = analyze_video(video_pfad, api_key)
    except Exception as fehler:
        print(traceback.format_exc())
        beenden(f"Analyse fehlgeschlagen: {fehler}", fehler=True)

    # ── Schritt 3: Ergebnis anzeigen ──────────────────────────────────────────
    print("\n" + "=" * 52)
    print("ANALYSE-ERGEBNIS (Vorschau):")
    print("=" * 52)
    # Nur die ersten 800 Zeichen anzeigen (JSON kann sehr lang sein)
    vorschau = analyse[:800] + ("…" if len(analyse) > 800 else "")
    print(vorschau)

    # ── Schritt 4: Analyse speichern ──────────────────────────────────────────
    try:
        gespeichert_unter = speichere_analyse(analyse, video_titel)
        print("\n" + "=" * 52)
        print(f"✓ Gespeichert: {gespeichert_unter}")
        print("  → Im Dashboard unter 'Gespeicherte Spiele' verfügbar")
    except Exception as fehler:
        print(traceback.format_exc())
        print(f"\n⚠ Warnung: Speichern fehlgeschlagen: {fehler}")

    beenden()  # Wartet auf Enter vor dem Schließen


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except Exception:
        # Unerwarteter Fehler – vollständigen Stacktrace zeigen
        print("\n" + "=" * 52)
        print("UNERWARTETER FEHLER:")
        print("=" * 52)
        traceback.print_exc()
        input("\nDrücke Enter zum Beenden...")
