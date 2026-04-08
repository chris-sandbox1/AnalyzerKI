"""
analyzer.py – Sendet ein Floorball-Video an die Gemini API und gibt die Analyse zurück.
Genutzte Bibliothek: google-generativeai
"""

import google.genai as genai
from google.genai import types
import time
import os
import json
import re


def analyze_video(video_pfad: str, api_key: str) -> str:
    """
    Lädt ein Video zur Gemini API hoch und analysiert es.

    Parameter:
        video_pfad: Lokaler Pfad zur Videodatei
        api_key: Dein Gemini API-Key

    Rückgabe:
        Die Analyse als Text
    """

    # API-Client erstellen
    client = genai.Client(api_key=api_key)

    # Prüfen, ob die Datei existiert
    if not os.path.exists(video_pfad):
        raise FileNotFoundError(f"Videodatei nicht gefunden: {video_pfad}")

    # Video-Größe anzeigen (zur Info)
    groesse_mb = os.path.getsize(video_pfad) / (1024 * 1024)
    print(f"Lade Video hoch ({groesse_mb:.1f} MB)... Das kann etwas dauern.")

    # Video zur Gemini File API hochladen
    video_datei = client.files.upload(file=video_pfad)

    # Warten, bis Gemini das Video verarbeitet hat
    print("Warte auf Verarbeitung durch Gemini...", end="", flush=True)
    while video_datei.state.name == "PROCESSING":
        time.sleep(5)
        video_datei = client.files.get(name=video_datei.name)
        print(".", end="", flush=True)
    print(" fertig!")

    # Prüfen ob Verarbeitung erfolgreich war
    if video_datei.state.name == "FAILED":
        raise RuntimeError("Gemini konnte das Video nicht verarbeiten.")

    # Detaillierter Floorball-Analyse-Prompt mit JSON-Ausgabe
    prompt = """
Du analysierst ein Floorball-Video. Floorball ist eine Hallensportart mit folgenden Merkmalen:
- Kleiner weißer Plastikball (Wiffle-Ball)
- Zwei Spielfeldhälften, je ein Tor pro Seite
- Ein Torwart pro Team (liegt/kniet oft vor dem Tor)
- Spieler mit Kunststoffschlägern

Analysiere das Video und erkenne folgende Ereignisse mit Zeitstempeln (MM:SS Format):

1. **TORE**: Ball überquert vollständig die Torlinie ins Tor.
   - Welches Team hat getroffen (Team A = links angreifend, Team B = rechts angreifend)?
   - Wie war die Vorbereitung? (Direktschuss, Pass vor dem Tor, Einzelaktion, Nachschuss)

2. **TORSCHUESSE**: Gezielter Schuss in Richtung Tor (auch wenn gehalten oder daneben).
   - Position des Schützen: "Kreis" (nahe am Tor, innerhalb 3m), "Halbdistanz" (3–8m), "Aussen" (über 8m oder Seitenposition)
   - Welches Team schießt?

3. **BALLBESITZWECHSEL**: Klar erkennbarer Wechsel des Ballbesitzes (Abfangen, Zweikampfgewinn, nach Tor).

4. **KONTER**: Schneller Angriff direkt nach Ballgewinn in der eigenen Hälfte, bevor die Gegner sich sortieren können.
   - Wie viele Angreifer gegen wie viele Verteidiger? (z.B. "2 gegen 1")

5. **CHANCEN**: Klare Torchance ohne Torabschluss (z.B. Ball am leeren Tor vorbei, Torwart rettet in letzter Sekunde, Schuss geblockt kurz vor Abschluss).

Antworte **ausschließlich** mit einem gültigen JSON-Objekt, ohne Erklärungen davor oder danach.
Das JSON muss exakt folgende Struktur haben:

{
  "zusammenfassung": "Kurze Beschreibung des Videos in 2-3 Sätzen",
  "ereignisse": [
    {
      "timestamp": "MM:SS",
      "typ": "TOR" | "TORSCHUSS" | "BALLBESITZWECHSEL" | "KONTER" | "CHANCE",
      "team": "A" | "B" | "unbekannt",
      "details": "Beschreibung auf Deutsch"
    }
  ],
  "statistik": {
    "tore_team_a": 0,
    "tore_team_b": 0,
    "torschuesse_team_a": 0,
    "torschuesse_team_b": 0,
    "konter_gesamt": 0,
    "chancen_gesamt": 0
  }
}
"""

    print("Analysiere Video mit Gemini...")

    # Anfrage an Gemini senden (Modell: gemini-2.5-flash)
    antwort = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Part.from_uri(file_uri=video_datei.uri, mime_type=video_datei.mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(
            max_output_tokens=32768,  # hoch genug für lange Analysen mit vielen Ereignissen
            temperature=0.2,          # niedrige Kreativität → zuverlässigeres JSON-Format
        ),
    )

    # Hochgeladene Datei wieder löschen (spart Speicher im Gemini-Konto)
    client.files.delete(name=video_datei.name)

    # JSON aus der Antwort extrahieren und formatiert zurückgeben
    roh_text = antwort.text.strip()

    # Gemini verpackt die Antwort manchmal in ```json ... ``` – alle Varianten abfangen
    # Variante 1: ```json  ...  ```
    # Variante 2: ```      ...  ```
    # Variante 3: Nur geschweifte Klammer am Anfang (kein Wrapper)
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", roh_text)
    if json_match:
        roh_text = json_match.group(1).strip()
    else:
        # Fallback: ersten { bis letzten } ausschneiden
        start = roh_text.find("{")
        end   = roh_text.rfind("}") + 1
        if start != -1 and end > start:
            roh_text = roh_text[start:end]

    # JSON parsen und schön formatiert zurückgeben
    try:
        analyse_json = json.loads(roh_text)
        return json.dumps(analyse_json, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        # Falls kein gültiges JSON: Rohantwort zurückgeben (wird in main.py nochmals versucht)
        return roh_text
