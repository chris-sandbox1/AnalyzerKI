"""
analyzer.py – Sendet ein Floorball-Video + Regelwerk-PDF an Gemini zur Analyse.
Das PDF wird per Context Caching zwischengespeichert (24h), damit es nicht
bei jeder Analyse neu hochgeladen und berechnet werden muss.
"""

import google.genai as genai
from google.genai import types
import time
import os
import json
import re
import glob as glob_module


# Datei zum Speichern des Cache-Zustands zwischen Programmläufen
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.pdf_cache.json')


def finde_pdf(ordner: str):
    """Gibt die erste gefundene PDF-Datei im Ordner zurück, oder None."""
    treffer = glob_module.glob(os.path.join(ordner, '*.pdf'))
    return treffer[0] if treffer else None


def _pdf_kontext_laden(client, pdf_pfad: str):
    """
    Lädt oder erstellt den Context-Cache für das PDF-Regelwerk.

    Rückgabe: eines von zwei Tupeln:
      ('cache',  cache_name,       None)        → cached_content=cache_name in Config nutzen
      ('direkt', None,   (uri, mime_type))      → PDF als Part direkt mitsenden
    """
    state = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding='utf-8') as f:
                state = json.load(f)
        except Exception:
            state = {}

    # 1. Bestehenden Cache prüfen
    cache_name = state.get('cache_name')
    if cache_name:
        try:
            client.caches.get(name=cache_name)
            print("  PDF-Cache wird wiederverwendet (noch aktiv).")
            return 'cache', cache_name, None
        except Exception:
            print("  Alter Cache abgelaufen, erstelle neuen...")
            state.pop('cache_name', None)

    # 2. Bereits hochgeladene Datei wiederverwenden (Files API: 48h gültig)
    pdf_uri, pdf_mime, file_name = None, 'application/pdf', None
    stored_file = state.get('file_name')
    if stored_file:
        try:
            existing = client.files.get(name=stored_file)
            if existing.state.name == 'ACTIVE':
                pdf_uri  = existing.uri
                pdf_mime = existing.mime_type or 'application/pdf'
                file_name = existing.name
                print("  PDF-Datei noch aktiv, kein Neu-Upload nötig.")
        except Exception:
            pass  # Datei abgelaufen, wird neu hochgeladen

    # 3. PDF hochladen falls nötig
    if not pdf_uri:
        print(f"  Lade PDF hoch: {os.path.basename(pdf_pfad)}...")
        uploaded = client.files.upload(file=pdf_pfad)
        while uploaded.state.name == 'PROCESSING':
            time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)
        pdf_uri   = uploaded.uri
        pdf_mime  = uploaded.mime_type or 'application/pdf'
        file_name = uploaded.name
        print("  PDF hochgeladen.")

    # 4. Context-Cache erstellen (24h TTL)
    try:
        print("  Erstelle Context-Cache (24h TTL)...")
        cache = client.caches.create(
            model='models/gemini-2.5-flash',
            config=types.CreateCachedContentConfig(
                contents=[types.Content(
                    role='user',
                    parts=[types.Part.from_uri(file_uri=pdf_uri, mime_type=pdf_mime)]
                )],
                ttl='86400s',
                display_name='floorball-regeln',
            )
        )
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'cache_name': cache.name, 'file_name': file_name}, f)
        print(f"  Cache erstellt: {cache.name}")
        return 'cache', cache.name, None

    except Exception as e:
        # Context Caching nicht verfügbar (z.B. Modell/Region nicht unterstützt)
        print(f"  Context-Caching nicht verfügbar ({e}).")
        print("  Sende PDF direkt mit dem Video (kein Caching).")
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'file_name': file_name}, f)
        return 'direkt', None, (pdf_uri, pdf_mime)


# ── Analyse-Prompt ────────────────────────────────────────────────────────────

PROMPT = """
Du analysierst ein Floorball-Spiel. Das Regelwerk-Dokument hast du bereits erhalten –
nutze es für präzise Ereigniserkennung (Strafen, Vergehen, Spielregeln).

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
  UEBERZAHL_TOR     – Tor erzielt während Gegner eine Zeitstrafe verbüßt.
  UNTERZAHL_TOR     – Tor erzielt obwohl das eigene Team in Unterzahl spielt.
  PENALTY_SHOT      – Direkter Penalty (1-gegen-1 mit Torwart). Position PFLICHT.
  FACE_OFF_GEWONNEN – Gewonnenes Bully. Details: Zone (eigene/Mitte/gegnerische Hälfte).

POSITIONS-PFLICHT für TOR, TORSCHUSS, CHANCE, PENALTY_SHOT:
  Schätze die Schussposition in Feldmetern. Referenzpunkte:
  – Nahschuss rechtes Tor (Team A):  {"x": 35, "y": 10}
  – Nahschuss linkes Tor  (Team B):  {"x":  5, "y": 10}
  – Halbdistanz rechts, oben:        {"x": 28, "y": 16}
  – Halbdistanz links, unten:        {"x": 12, "y":  4}
  – Außenschuss, Mitte rechts:       {"x": 22, "y": 10}
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


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def analyze_video(video_pfad: str, api_key: str) -> str:
    """
    Lädt das Video (und das PDF-Regelwerk) zur Gemini API hoch und analysiert es.
    Gibt die Analyse als formatiertes JSON-String zurück.
    """
    client = genai.Client(api_key=api_key)

    if not os.path.exists(video_pfad):
        raise FileNotFoundError(f"Videodatei nicht gefunden: {video_pfad}")

    # Video hochladen
    groesse_mb = os.path.getsize(video_pfad) / (1024 * 1024)
    print(f"Lade Video hoch ({groesse_mb:.1f} MB)...")
    video_datei = client.files.upload(file=video_pfad)

    print("Warte auf Video-Verarbeitung...", end='', flush=True)
    while video_datei.state.name == 'PROCESSING':
        time.sleep(5)
        video_datei = client.files.get(name=video_datei.name)
        print('.', end='', flush=True)
    print(' fertig!')

    if video_datei.state.name == 'FAILED':
        raise RuntimeError("Gemini konnte das Video nicht verarbeiten.")

    # PDF-Regelwerk vorbereiten (Cache oder Direkt-Upload)
    modus, cache_name, pdf_direkt = 'ohne', None, None
    pdf_pfad = finde_pdf(os.path.dirname(os.path.abspath(__file__)))
    if pdf_pfad:
        print("Bereite PDF-Regelwerk vor...")
        try:
            modus, cache_name, pdf_direkt = _pdf_kontext_laden(client, pdf_pfad)
        except Exception as e:
            print(f"  Warnung: PDF-Vorbereitung fehlgeschlagen: {e}")
            print("  Analysiere ohne Regelwerk.")
    else:
        print("Kein PDF-Regelwerk gefunden, analysiere ohne Regelwerk.")

    # Gemini-Anfrage zusammenstellen
    video_part = types.Part.from_uri(
        file_uri=video_datei.uri,
        mime_type=video_datei.mime_type
    )

    if modus == 'cache':
        # PDF ist gecacht → nur Video + Prompt senden, Cache wird automatisch vorangestellt
        contents = [video_part, PROMPT]
        cfg = types.GenerateContentConfig(
            cached_content=cache_name,
            max_output_tokens=32768,
            temperature=0.2,
        )
    elif modus == 'direkt':
        # PDF als Part direkt mitsenden (kein Cache)
        pdf_part = types.Part.from_uri(file_uri=pdf_direkt[0], mime_type=pdf_direkt[1])
        contents = [pdf_part, video_part, PROMPT]
        cfg = types.GenerateContentConfig(
            max_output_tokens=32768,
            temperature=0.2,
        )
    else:
        # Kein Regelwerk
        contents = [video_part, PROMPT]
        cfg = types.GenerateContentConfig(
            max_output_tokens=32768,
            temperature=0.2,
        )

    print("Analysiere Video mit Gemini...")
    antwort = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=contents,
        config=cfg,
    )

    # Video-Datei aus Gemini-Storage löschen (spart Speicherplatz)
    client.files.delete(name=video_datei.name)

    # JSON aus der Antwort extrahieren
    roh_text = antwort.text.strip()

    # Gemini verpackt manchmal in ```json ... ``` → entfernen
    json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', roh_text)
    if json_match:
        roh_text = json_match.group(1).strip()
    else:
        start = roh_text.find('{')
        end   = roh_text.rfind('}') + 1
        if start != -1 and end > start:
            roh_text = roh_text[start:end]

    try:
        analyse_json = json.loads(roh_text)
        return json.dumps(analyse_json, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return roh_text
