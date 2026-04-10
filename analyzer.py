"""
analyzer.py – Sendet ein Floorball-Video an die Gemini API und gibt die Analyse zurück.
Gemini nutzt sein eingebautes Floorball-Wissen (kein externes Regelwerk nötig).
"""

import google.genai as genai
from google.genai import types
import time
import os
import json
import re


# ── Analyse-Prompt ────────────────────────────────────────────────────────────

PROMPT_VORLAGE = """
Du analysierst ein Floorball-Spiel.{periode_kontext}

SPIELFELD-KOORDINATENSYSTEM (40 m × 20 m):
  x = 0  → linkes Tor      x = 40 → rechtes Tor
  y = 0  → untere Bande    y = 20 → obere Bande    Mitte: x=20, y=10
  Team A greift nach rechts (Ziel: Tor bei x=40)
  Team B greift nach links  (Ziel: Tor bei x=0)

ERKENNE DIESE EREIGNISSE (Zeitstempel: MM:SS):

  TOR               – Ball überquert vollständig die Torlinie. Position PFLICHT.
  TORSCHUSS         – Gezielter Schuss aufs Tor (auch gehalten/daneben). Position PFLICHT.
  BALLBESITZWECHSEL – Klar erkennbarer Wechsel des Ballbesitzes.
  KONTER            – Schneller Gegenangriff nach Ballgewinn ("X gegen Y" in Details).
  CHANCE            – Klare Torchance ohne Abschluss. Position falls erkennbar.
  PENALTY           – Zeitstrafe. Details: Spieler + Vergehen + Dauer (2 oder 5 Min).
  UEBERZAHL_TOR     – Tor erzielt während Gegner eine Zeitstrafe verbüßt. Position PFLICHT.
  UNTERZAHL_TOR     – Tor erzielt obwohl eigenes Team in Unterzahl spielt. Position PFLICHT.
  PENALTY_SHOT      – Direkter Penalty (1-gegen-1 mit Torwart). Position PFLICHT.
  FACE_OFF_GEWONNEN – Gewonnenes Bully. Details: Zone (eigene/Mitte/gegnerische Hälfte).

POSITIONS-PFLICHT für TOR, TORSCHUSS, CHANCE, UEBERZAHL_TOR, UNTERZAHL_TOR, PENALTY_SHOT:
  Schätze die Schussposition in Feldmetern. Referenzpunkte:
  – Nahschuss rechtes Tor (Team A):  {"x": 35, "y": 10}
  – Nahschuss linkes Tor  (Team B):  {"x":  5, "y": 10}
  – Halbdistanz rechts, oben:        {"x": 28, "y": 16}
  – Halbdistanz links, unten:        {"x": 12, "y":  4}
  – Außenschuss, Mitte:              {"x": 20, "y": 10}
  – Penalty aufs rechte Tor (7m):    {"x": 33, "y": 10}
  – Penalty aufs linke Tor (7m):     {"x":  7, "y": 10}

Antworte AUSSCHLIESSLICH mit folgendem JSON-Objekt (kein Text davor oder danach):

{
  "zusammenfassung": "2-3 Sätze zum Spielverlauf",
  "ereignisse": [
    {
      "timestamp": "MM:SS",
      "typ": "TOR",
      "team": "Teamname oder unbekannt",
      "details": "Beschreibung auf Deutsch",
      "position": {"x": 35.0, "y": 10.0}
    }
  ],
  "statistik": {
    "tore_team_a": 0,
    "tore_team_b": 0,
    "torschuesse_team_a": 0,
    "torschuesse_team_b": 0,
    "konter_gesamt": 0,
    "chancen_gesamt": 0,
    "penalties_team_a": 0,
    "penalties_team_b": 0
  }
}
"""


# ── JSON-Reparatur für abgeschnittene Antworten ───────────────────────────────

def _repariere_json(text: str):
    """
    Versucht ein abgeschnittenes JSON-Objekt zu reparieren.
    Scannt die letzten Positionen von } und ] rückwärts und schließt
    offene Arrays/Objekte durch Stack-Analyse.
    Gibt das geparste Objekt zurück, oder None bei Misserfolg.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    positionen = [i for i, c in enumerate(text) if c in ('}', ']')]
    if not positionen:
        return None

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


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def analyze_video(video_pfad: str, api_key: str, periode_info: str = "") -> str:
    """
    Lädt das Video zur Gemini API hoch und analysiert es.

    periode_info: Optionaler Kontext-String, z.B. "Dies ist die 1. Hälfte (1 von 2)."
    Gibt die Analyse als formatiertes JSON-String zurück.
    """
    client = genai.Client(api_key=api_key)

    if not os.path.exists(video_pfad):
        raise FileNotFoundError(f"Videodatei nicht gefunden: {video_pfad}")

    # Prompt mit optionalem Perioden-Kontext befüllen
    if periode_info:
        kontext_block = f"\n\nWICHTIGER KONTEXT: {periode_info}"
    else:
        kontext_block = ""
    prompt = PROMPT_VORLAGE.replace("{periode_kontext}", kontext_block)

    # Video hochladen
    groesse_mb = os.path.getsize(video_pfad) / (1024 * 1024)
    print(f"  Lade Video hoch ({groesse_mb:.1f} MB)...")
    video_datei = client.files.upload(file=video_pfad)

    print("  Warte auf Verarbeitung...", end='', flush=True)
    while video_datei.state.name == 'PROCESSING':
        time.sleep(5)
        video_datei = client.files.get(name=video_datei.name)
        print('.', end='', flush=True)
    print(' fertig!')

    if video_datei.state.name == 'FAILED':
        raise RuntimeError("Gemini konnte das Video nicht verarbeiten.")

    # Anfrage an Gemini
    print("  Gemini analysiert...")
    antwort = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            types.Part.from_uri(file_uri=video_datei.uri, mime_type=video_datei.mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(
            max_output_tokens=65536,
            temperature=0.1,
        ),
    )

    # Video aus Gemini-Storage löschen
    client.files.delete(name=video_datei.name)

    # JSON aus der Antwort extrahieren
    roh_text = antwort.text.strip()

    # Markdown-Wrapper entfernen (```json ... ```)
    json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', roh_text)
    if json_match:
        roh_text = json_match.group(1).strip()
    else:
        start = roh_text.find('{')
        end   = roh_text.rfind('}') + 1
        if start != -1 and end > start:
            roh_text = roh_text[start:end]

    # JSON parsen — bei Misserfolg Reparatur versuchen
    try:
        return json.dumps(json.loads(roh_text), ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        pass

    print("  Antwort unvollständig, versuche Reparatur...")
    repariert = _repariere_json(roh_text)
    if repariert:
        print("  Reparatur erfolgreich.")
        return json.dumps(repariert, ensure_ascii=False, indent=2)

    print("  WARNUNG: JSON konnte nicht repariert werden, speichere Rohtext.")
    return roh_text
