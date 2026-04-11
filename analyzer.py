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
Analysiere das Video frame-genau und chronologisch von Anfang bis Ende. Erfinde keine Events und wiederhole keine Events. Jedes Event das du ausgibst muss auf einer real im Video sichtbaren Aktion basieren. Wenn du dir bei einem Event nicht sicher bist, lasse es weg — ein fehlendes Event ist besser als ein erfundenes oder wiederholtes.

Du analysierst ein Floorball-Spiel.{periode_kontext}

SPIELFELD-ZONEN-SYSTEM (immer aus Team-A-Perspektive):
  Team A = erstes Team das du in Ereignissen nennst. Team A greift immer nach rechts.
  Team B greift immer nach links.
  OBEN = obere Feldhälfte (Bande oben), UNTEN = untere Feldhälfte, MITTE = zentral.

  9 Bereiche von links (eigenes Tor Team A) nach rechts (gegnerisches Tor Team A):
  EIGN_TOR     – direkt vor eigenem Tor (Torwartbereich Team A)
  EIGN_TORRAUM – eigener Strafraum Team A
  EIGN_SLOT    – zwischen eigenem Strafraum und Mittellinie (nah)
  EIGN_HALB    – eigene Halbdistanz
  RUECKRAUM    – Mittelfeld / um die Mittellinie
  GEGN_HALB    – gegnerische Halbdistanz
  GEGN_SLOT    – gegnerischer Slot (nah vor Strafraum)
  GEGN_TORRAUM – gegnerischer Strafraum
  GEGN_TOR     – direkt hinter gegnerischem Tor

ERKENNE DIESE EREIGNISSE (Zeitstempel: MM:SS):

  TOR               – Ball überquert vollständig die Torlinie. Zone PFLICHT.
  TORSCHUSS         – Gezielter Schuss aufs Tor (auch gehalten/daneben). Zone PFLICHT.
  BALLBESITZWECHSEL – Klar erkennbarer Wechsel des Ballbesitzes. Keine Zone.
  KONTER            – Schneller Gegenangriff nach Ballgewinn. Zone = wo der Ball gewonnen wurde.
  CHANCE            – Klare Torchance ohne Abschluss. Zone PFLICHT.
  PENALTY           – Zeitstrafe. Keine Zone. Details: Spieler + Vergehen + Dauer (2 oder 5 Min).
  UEBERZAHL_TOR     – Tor in Überzahl. Zone PFLICHT.
  UNTERZAHL_TOR     – Tor in Unterzahl. Zone PFLICHT.
  PENALTY_SHOT      – Direkter Penalty (1-gegen-1). Zone immer PENALTY.
  FACE_OFF_GEWONNEN – Gewonnenes Bully. Keine Zone. Details: Feldbereich.
  ZWEIKAMPF         – Zwei Spieler kämpfen um den Ball, einer gewinnt ihn. Zone PFLICHT.

ZONEN-REGELN:

  Für TOR, TORSCHUSS, CHANCE, UEBERZAHL_TOR, UNTERZAHL_TOR:
    Zone = Bereich + Suffix _MITTE / _OBEN / _UNTEN
    Beispiele: GEGN_TORRAUM_MITTE, GEGN_SLOT_OBEN, RUECKRAUM_UNTEN
    Penalty-Schuss: zone = "PENALTY"

  Für ZWEIKAMPF, KONTER:
    Zone = nur Bereich ohne Suffix
    Beispiele: RUECKRAUM, GEGN_HALB, EIGN_SLOT

  Für ZWEIKAMPF zusätzliche Felder:
    gewonnen: true wenn das genannte team den Ball gewinnt, false wenn verliert
    spieler_gewinner: Trikotnummer + Name wenn erkennbar ('#19 Eriksson'), sonst weglassen
    spieler_verlierer: Trikotnummer + Name des Gegners wenn erkennbar, sonst weglassen

Antworte AUSSCHLIESSLICH mit folgendem JSON-Objekt (kein Text davor oder danach):

{
  "zusammenfassung": "2-3 Sätze zum Spielverlauf",
  "ereignisse": [
    {
      "timestamp": "02:01",
      "typ": "TOR",
      "team": "SWE",
      "zone": "GEGN_TORRAUM_MITTE",
      "details": "Pass vor das Tor, Direktschuss ins kurze Eck"
    },
    {
      "timestamp": "03:15",
      "typ": "ZWEIKAMPF",
      "team": "SWE",
      "zone": "RUECKRAUM",
      "gewonnen": true,
      "spieler_gewinner": "#19 Eriksson",
      "spieler_verlierer": "#9",
      "details": "Eriksson gewinnt Ball gegen #9 an der Mittellinie"
    },
    {
      "timestamp": "04:22",
      "typ": "KONTER",
      "team": "SWE",
      "zone": "EIGN_HALB",
      "details": "2-gegen-1 nach Ballgewinn in eigener Hälfte"
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
    # Dateinamen werden immer ASCII-sicher erzeugt (main.py/downloader.py nutzen ascii_dateiname())
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
