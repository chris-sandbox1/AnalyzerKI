"""
start.py – Startet lokalen Webserver auf Port 8080 und öffnet das Dashboard.

Routen:
  GET  /dashboard.html    → Dashboard
  GET  /analyses          → JSON-Liste aller gespeicherten Spiele
  GET  /analyses/<datei>  → Einzelne Analyse-JSON-Datei
  GET  /api/videos        → Dateien im downloads/-Ordner als JSON-Liste
  POST /api/download      → {"url": "..."} → lädt YouTube-Video herunter
  POST /api/analyse       → {"video": "...", "titel": "...", "sequenzen": [...]}
  GET  /*                 → Sonstige statische Dateien
"""

import http.server
import webbrowser
import threading
import os
import json
import subprocess
import tempfile
import traceback
from datetime import datetime

PORT = 8080

# Ins Projektverzeichnis wechseln (funktioniert unabhängig vom Startort)
os.chdir(os.path.dirname(os.path.abspath(__file__)))


# ── Hilfsfunktionen für die Analyse-Pipeline ─────────────────────────────────

def _lade_api_key() -> str:
    """Liest den Gemini-API-Key aus der .env-Datei."""
    env_pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_pfad):
        with open(env_pfad, encoding="utf-8") as f:
            for zeile in f:
                zeile = zeile.strip()
                if zeile.startswith("GEMINI_API_KEY="):
                    key = zeile.split("=", 1)[1].strip()
                    if key and not key.startswith("dein-"):
                        return key
    return ""


def _ermittle_videohoehe(pfad: str) -> int:
    """Gibt die Bildhöhe des Videos in Pixeln zurück, oder -1 bei Fehler."""
    try:
        ergebnis = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height",
             "-of", "default=noprint_wrappers=1:nokey=1", pfad],
            capture_output=True, text=True, timeout=30,
        )
        return int(ergebnis.stdout.strip())
    except Exception:
        return -1


def _skaliere_auf_480p(quelle: str, ziel: str):
    """Skaliert das Video auf max. 480p mit ffmpeg."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", quelle, "-vf", "scale=-2:480",
         "-c:v", "libx264", "-crf", "23", "-preset", "fast", "-c:a", "copy", ziel],
        capture_output=True, check=True,
    )


def _schneide_video(quelle: str, start_sek: float, dauer_sek: float, ziel: str):
    """Schneidet einen Abschnitt aus dem Video (verlustfrei, -c copy)."""
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start_sek), "-i", quelle,
         "-t", str(dauer_sek), "-c", "copy", ziel],
        capture_output=True, check=True,
    )


def _speichere_analyse(analyse_obj: dict, video_titel: str) -> str:
    """Speichert die Analyse-JSON in analyses/ und aktualisiert den Index."""
    import re
    os.makedirs("analyses", exist_ok=True)

    def _ascii(name):
        ersets = {'ä':'ae','ö':'oe','ü':'ue','Ä':'Ae','Ö':'Oe','Ü':'Ue','ß':'ss'}
        for a, b in ersets.items():
            name = name.replace(a, b)
        name = name.encode('ascii', 'ignore').decode('ascii')
        name = re.sub(r'[^\w\-.]', '_', name)
        name = re.sub(r'_+', '_', name)
        return name[:60].strip('_').lower()

    datum = datetime.now().strftime("%Y%m%d")
    dateiname = f"{_ascii(video_titel)}_{datum}.json"
    pfad = os.path.join("analyses", dateiname)

    zaehler = 1
    while os.path.exists(pfad):
        dateiname = f"{_ascii(video_titel)}_{datum}_{zaehler}.json"
        pfad = os.path.join("analyses", dateiname)
        zaehler += 1

    analyse_obj["_meta"] = {
        "videotitel": video_titel,
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "dateiname": dateiname,
    }

    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(analyse_obj, f, ensure_ascii=False, indent=2)

    _aktualisiere_index()
    return pfad


def _aktualisiere_index():
    """Schreibt analyses/index.json und analyses/data.js neu."""
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

    eintraege.reverse()

    with open(os.path.join(ordner, "index.json"), "w", encoding="utf-8") as f:
        json.dump(eintraege, f, ensure_ascii=False, indent=2)

    inhalt = (
        "// Automatisch generiert – nicht manuell bearbeiten\n"
        "window.FLOORBALL_DATA = "
        + json.dumps({"index": eintraege, "spiele": alle_spiele}, ensure_ascii=False)
        + ";\n"
    )
    with open(os.path.join(ordner, "data.js"), "w", encoding="utf-8") as f:
        f.write(inhalt)


def _analyse_pipeline(video_datei: str, sequenzen: list, video_titel: str) -> str:
    """
    Führt die komplette Analyse-Pipeline aus.
    Gibt den Dateinamen der gespeicherten Analyse zurück.

    video_datei : Dateiname relativ zu downloads/ (z.B. 'spiel.mp4')
    sequenzen   : Liste mit {"start": "MM:SS", "end": "MM:SS", "label": "..."} oder []
    video_titel : Spieltitel für die Anzeige
    """
    from analyzer import analyze_video
    from merger import merge_ergebnisse, parse_zeit
    from stats_engine import berechne_stats

    api_key = _lade_api_key()
    if not api_key:
        raise RuntimeError("Kein Gemini-API-Key in .env gefunden.")

    video_pfad = os.path.join("downloads", video_datei)
    if not os.path.exists(video_pfad):
        raise FileNotFoundError(f"Video nicht gefunden: {video_pfad}")

    def _repariere(text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        positionen = [i for i, c in enumerate(text) if c in ('}', ']')]
        for pos in reversed(positionen[-80:]):
            fragment = text[:pos + 1].rstrip().rstrip(',')
            stack, in_str, esc = [], False, False
            for ch in fragment:
                if esc: esc = False; continue
                if ch == '\\': esc = True; continue
                if ch == '"': in_str = not in_str; continue
                if in_str: continue
                if ch == '{': stack.append('}')
                elif ch == '[': stack.append(']')
                elif ch in '}]' and stack and stack[-1] == ch: stack.pop()
            try:
                return json.loads(fragment + ''.join(reversed(stack)))
            except json.JSONDecodeError:
                continue
        return None

    def _analysiere_clip(clip_pfad, periode_info):
        """Analysiert einen Clip (skaliert ggf. auf 480p) und gibt das geparste JSON zurück."""
        hoehe = _ermittle_videohoehe(clip_pfad)
        analyse_pfad = clip_pfad
        skaliert = None
        if hoehe > 480:
            skaliert = clip_pfad + "_480p.mp4"
            try:
                _skaliere_auf_480p(clip_pfad, skaliert)
                analyse_pfad = skaliert
            except subprocess.CalledProcessError:
                pass  # Skalierung fehlgeschlagen → Originaldatei nutzen

        roh = analyze_video(analyse_pfad, api_key, periode_info)

        if skaliert and os.path.exists(skaliert):
            try:
                os.remove(skaliert)
            except Exception:
                pass

        obj = _repariere(roh)
        if obj is None:
            raise RuntimeError("Gemini-Antwort konnte nicht als JSON gelesen werden.")
        return obj

    with tempfile.TemporaryDirectory() as tmp:

        if not sequenzen:
            # Kein Schnitt → gesamtes Video direkt analysieren
            print("Analysiere gesamtes Video ohne Schnitt...")
            ergebnis = _analysiere_clip(video_pfad, "")
            ergebnis = berechne_stats(ergebnis)

        elif len(sequenzen) == 1:
            # Eine Sequenz → schneiden und analysieren, kein Merging
            # Erste Sequenz ist immer Referenz: Team A greift nach rechts
            seq = sequenzen[0]
            start_sek = parse_zeit(seq.get("start", "00:00"))
            end_sek   = parse_zeit(seq.get("end",   "00:00"))
            label = seq.get("label") or "Sequenz 1"
            print(f"Schneide und analysiere: {label}...")
            if end_sek > start_sek:
                clip = os.path.join(tmp, "seq_1.mp4")
                _schneide_video(video_pfad, start_sek, end_sek - start_sek, clip)
            else:
                clip = video_pfad
            richtung = "Team A greift in diesem Clip nach rechts (Tor bei x=40), Team B nach links (Tor bei x=0)."
            ergebnis = _analysiere_clip(clip, f"{richtung} Dies ist {label}.")
            ergebnis = berechne_stats(ergebnis)

        else:
            # Mehrere Sequenzen → schneiden, analysieren, zusammenführen
            teilergebnisse = []
            greift_rechts = True  # Seq 1 ist immer Referenz; jedes "seitengetauscht" dreht um
            gesamt = len(sequenzen)
            for i, seq in enumerate(sequenzen):
                start_sek = parse_zeit(seq.get("start", "00:00"))
                end_sek   = parse_zeit(seq.get("end",   "00:00"))
                label = seq.get("label") or f"Teil {i + 1}"
                print(f"Sequenz {i + 1}/{gesamt}: {label}...")

                # Richtung akkumulieren: erste Seq immer rechts, jedes "↔" dreht um
                if i > 0 and seq.get("seitengetauscht", False):
                    greift_rechts = not greift_rechts

                if greift_rechts:
                    richtung = "Team A greift in diesem Clip nach rechts (Tor bei x=40), Team B nach links (Tor bei x=0)."
                else:
                    richtung = "Team A greift in diesem Clip nach links (Tor bei x=0), Team B nach rechts (Tor bei x=40)."

                if end_sek > start_sek:
                    clip = os.path.join(tmp, f"seq_{i + 1}.mp4")
                    _schneide_video(video_pfad, start_sek, end_sek - start_sek, clip)
                else:
                    clip = video_pfad

                periode_info = f"{richtung} Dies ist {label} ({i + 1} von {gesamt})."
                obj = _analysiere_clip(clip, periode_info)
                teilergebnisse.append(obj)

            ergebnis = merge_ergebnisse(teilergebnisse, sequenzen)

    pfad = _speichere_analyse(ergebnis, video_titel)
    return os.path.basename(pfad)


# ── HTTP-Handler ──────────────────────────────────────────────────────────────

class DashboardHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path in ('/analyses', '/analyses/'):
            self._serve_analyses_list()
        elif self.path == '/api/videos':
            self._api_videos()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/api/download':
            self._api_download()
        elif self.path == '/api/analyse':
            self._api_analyse()
        else:
            self._antworte_json({"fehler": "Unbekannte Route"}, status=404)

    # ── GET /analyses ──────────────────────────────────────────────────────────

    def _serve_analyses_list(self):
        ordner = 'analyses'
        eintraege = []
        if os.path.exists(ordner):
            for datei in sorted(os.listdir(ordner)):
                if not datei.endswith('.json') or datei in ('index.json', 'data.js'):
                    continue
                try:
                    with open(os.path.join(ordner, datei), encoding='utf-8') as f:
                        daten = json.load(f)
                    meta = daten.get('_meta', {})
                    eintraege.append({
                        'datei': datei,
                        'titel': meta.get('videotitel', datei),
                        'datum': meta.get('datum', ''),
                    })
                except Exception:
                    eintraege.append({'datei': datei, 'titel': datei, 'datum': ''})
        eintraege.reverse()
        self._antworte_json(eintraege)

    # ── GET /api/videos ────────────────────────────────────────────────────────

    def _api_videos(self):
        ordner = 'downloads'
        dateien = []
        if os.path.exists(ordner):
            for name in sorted(os.listdir(ordner)):
                if not name.lower().endswith(('.mp4', '.webm', '.mkv', '.avi', '.mov')):
                    continue
                pfad = os.path.join(ordner, name)
                try:
                    stat = os.stat(pfad)
                    dateien.append({
                        'name': name,
                        'groesse_mb': round(stat.st_size / (1024 * 1024), 1),
                        'datum': datetime.fromtimestamp(stat.st_mtime).strftime('%d.%m.%Y %H:%M'),
                    })
                except Exception:
                    dateien.append({'name': name, 'groesse_mb': 0, 'datum': ''})
        dateien.sort(key=lambda x: x['datum'], reverse=True)
        self._antworte_json(dateien)

    # ── POST /api/download ─────────────────────────────────────────────────────

    def _api_download(self):
        body = self._lese_body()
        if body is None:
            return
        url = body.get('url', '').strip()
        if not url:
            self._antworte_json({"ok": False, "fehler": "Keine URL angegeben."})
            return
        try:
            from downloader import download_video
            pfad, titel = download_video(url)
            self._antworte_json({"ok": True, "datei": os.path.basename(pfad), "titel": titel})
        except Exception as e:
            self._antworte_json({"ok": False, "fehler": str(e)})

    # ── POST /api/analyse ──────────────────────────────────────────────────────

    def _api_analyse(self):
        body = self._lese_body()
        if body is None:
            return
        video  = body.get('video', '').strip()
        titel  = body.get('titel', '').strip() or os.path.splitext(video)[0]
        sequenzen = body.get('sequenzen', [])

        if not video:
            self._antworte_json({"ok": False, "fehler": "Kein Video angegeben."})
            return
        try:
            dateiname = _analyse_pipeline(video, sequenzen, titel)
            self._antworte_json({"ok": True, "datei": dateiname})
        except Exception as e:
            traceback.print_exc()
            self._antworte_json({"ok": False, "fehler": str(e)})

    # ── Hilfsmethoden ──────────────────────────────────────────────────────────

    def _lese_body(self):
        """Liest und parst den JSON-Request-Body. Gibt None zurück und antwortet bei Fehler."""
        try:
            laenge = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(laenge)
            return json.loads(raw.decode('utf-8'))
        except Exception as e:
            self._antworte_json({"fehler": f"Ungültiger Request-Body: {e}"}, status=400)
            return None

    def _antworte_json(self, daten, status=200):
        body = json.dumps(daten, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Keine Konsolenausgabe pro Anfrage


def server_starten():
    with http.server.ThreadingHTTPServer(('', PORT), DashboardHandler) as server:
        server.serve_forever()


# Server im Hintergrund-Thread starten
threading.Thread(target=server_starten, daemon=True).start()

url = f'http://localhost:{PORT}/dashboard.html'
print(f'Floorball Dashboard: {url}')
webbrowser.open(url)

print('Server läuft. Mit Strg+C beenden.')
try:
    while True:
        import time
        time.sleep(1)
except KeyboardInterrupt:
    print('\nServer beendet.')
