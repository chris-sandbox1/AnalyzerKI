"""
start.py – Startet lokalen Webserver auf Port 8080 und öffnet den Saisonmanager.

Routen:
  GET /analyses             → JSON-Liste aller gespeicherten Spiele
  GET /data/alltime.json    → Alltime-Statistiken (generiert durch tools/alltime.py)
  GET /*                    → Sonstige statische Dateien
"""

import http.server
import socketserver
import webbrowser
import threading
import os
import json

PORT = 8080

# Ins Projektverzeichnis wechseln (funktioniert unabhängig vom Startort)
os.chdir(os.path.dirname(os.path.abspath(__file__)))


class DashboardHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path in ('/analyses', '/analyses/'):
            self._serve_analyses_list()
        else:
            super().do_GET()

    def _serve_analyses_list(self):
        """Liest alle Analyse-JSON-Dateien und gibt eine sortierte Liste zurück."""
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

        eintraege.reverse()  # Neueste zuerst

        body = json.dumps(eintraege, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Keine Konsolenausgabe pro Anfrage


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Jede Anfrage bekommt einen eigenen Thread — kein gegenseitiges Blockieren."""
    daemon_threads = True

def server_starten():
    with ThreadingServer(('', PORT), DashboardHandler) as server:
        server.serve_forever()


# Server im Hintergrund-Thread starten
threading.Thread(target=server_starten, daemon=True).start()

url_saisonmanager = f'http://localhost:{PORT}/saisonmanager.html'
url_dashboard     = f'http://localhost:{PORT}/dashboard.html'

print(f'  Saisonmanager:  {url_saisonmanager}')
print(f'  Spielanalyse:   {url_dashboard}')
webbrowser.open(url_saisonmanager)

print('Server läuft. Mit Strg+C beenden.')
try:
    while True:
        import time
        time.sleep(1)
except KeyboardInterrupt:
    print('\nServer beendet.')
