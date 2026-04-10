# Arbeitsregeln – Floorball Analyzer Projekt

## Kommunikation & Planung
- Bevor du anfängst zu coden: Erkläre deinen Plan in verständlicher Sprache
- Warte auf meine explizite Bestätigung, bevor du Änderungen machst
- Erkläre auf Deutsch, was du tust und warum — ich bin kein Entwickler
- Wenn etwas unklar ist, frag nach, anstatt Annahmen zu treffen

## Coding-Stil (allgemein)
- Halte alles so einfach wie möglich
- Keine unnötigen Abhängigkeiten oder Libraries
- Kommentiere Code auf Deutsch wenn hilfreich
- Bestehenden Code immer gezielt bearbeiten und korrigieren — nicht komplett neu schreiben wenn nicht nötig
- Nur die minimal nötigen Änderungen machen um ein Problem zu lösen
- Vor jeder Änderung die betroffene Datei lesen und verstehen
- Bei Bugs: erst Ursache analysieren, dann gezielt fixen

## Git-Regeln
- Nie ohne ausdrückliche Aufforderung pushen — nur commiten wenn explizit darum gebeten
- Wenn gepusht werden soll, zuerst committen, dann fragen ob Push gewünscht ist

---

## Projekt-Technologie-Stack

### Gemini API
- Modell: `gemini-2.5-flash` (in `analyzer.py`)
- Temperature: `0.1`
- max_output_tokens: `65536`
- SDK: `google.genai` mit `types.Part.from_uri` und `types.GenerateContentConfig`
- Kein Kontext-Caching, kein Regelwerk-PDF — Gemini kennt Floorball aus eigenen Trainingsdaten
- Prompt-Platzhalter mit `.replace("{periode_kontext}", ...)` — NICHT `.format()`, da der Prompt JSON-Beispiele mit `{x}` und `{y}` enthält, die Python als Format-Platzhalter interpretiert (KeyError!)

### Video-Pipeline
- Download: `yt-dlp` via `downloader.py`, max. 480p (`bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[ext=mp4]`)
- Lokale Dateien: Auflösung per `ffprobe` prüfen, bei > 480p automatisch mit `ffmpeg` auf 480p skalieren (temporäre Datei, wird nach Analyse gelöscht)
- Videolänge: `ffprobe` — unter 35 Min direkt, 35–70 Min → Nutzer fragt nach 2 Hälften, über 70 Min → nach 3 Perioden
- Schneiden: `ffmpeg -c copy` (verlustfrei, schnell)
- ffmpeg muss im PATH sein (Installation: `winget install Gyan.FFmpeg --scope user` für User ohne Adminrechte)

### Server & Dashboard
- Server: `start.py`, Port `8080`, Route `/analyses` liefert JSON-Liste
- Dashboard: `dashboard.html`, läuft unter `localhost:8080/dashboard.html`
- Analysen gespeichert in `analyses/` als JSON, plus `analyses/index.json` und `analyses/data.js`
- `data.js` ermöglicht direktes Öffnen ohne Server (file://-Protokoll)

### Koordinatensystem im Prompt
- Spielfeld 40 m × 20 m: x=0 linkes Tor, x=40 rechtes Tor, y=0 untere Bande, y=20 obere Bande
- Team A greift nach rechts (x=40), Team B nach links (x=0)
- Bei Seitenwechsel (2. Hälfte / 2. + 3. Periode): Richtungen tauschen — aber nur als Wahrscheinlichkeit angeben, da Videoschnitt zeitbasiert ist und nicht exakt am Seitenwechsel liegt

---

## Dashboard-Logik (wichtige Regeln)

### Ergebnis / Tore
- `toreA` und `toreB` kommen IMMER aus `data.statistik.tore_team_a` / `tore_team_b`
- NICHT aus dem Zählen von TOR-Events — das sind zwei verschiedene Quellen
- Nach jeder Analyse in `main.py` wird ein Vergleich gemacht: Wenn Events und Statistik-Felder abweichen, wird `data.warnung` gesetzt und das Dashboard zeigt einen gelben Hinweis unter dem Score

### Teams
- Team-Namen kommen aus den Ereignissen (dynamisch), nicht hardcodiert
- Benutzer kann im Dashboard eigene Namen und Farben setzen (Team Settings Modal), gespeichert in `localStorage` unter `floorball_teams`

### DOM-Rendering
- `div#main` wird komplett als ein `innerHTML`-String neu gebaut (`baueDashboard(data)`)
- KEIN direktes DOM-Manipulation nach dem Render (kein `el.style`, kein `el.setAttribute` nachträglich) — das führte früher zu stillen Fehlern wo das Dashboard leer blieb

### SVG-Koordinaten
- Feldkoordinaten → SVG: `x = 55 + (fx/40)*710`, `y = 382 - (fy/20)*364`
- Jitter für Schuss-Positionen: `Math.sin(i * 7919.0 + 1.337)` (deterministisch, gleiche Daten = gleiche Darstellung)

---

## Bekannte Fallstricke & frühere Fehler

### Python
- `.format()` auf Prompt-Strings schlägt fehl wenn der Prompt JSON-Beispiele enthält → immer `.replace()` nutzen
- `_repariere_json()` ist nötig weil Gemini die Antwort manchmal abbricht — backwards-scan über `}` und `]` Positionen mit Stack-basierter Klammer-Analyse
- `os.chdir(os.path.dirname(os.path.abspath(__file__)))` am Anfang von `main.py` ist Pflicht — ohne das schlägt alles fehl wenn das Skript per Doppelklick gestartet wird (falsches Arbeitsverzeichnis)
- `beenden()` mit `input("Drücke Enter...")` nötig damit das Terminal-Fenster bei Fehler nicht sofort schließt
- Greedy Regex für JSON-Extraktion: `r"```(?:json)?\s*(\{[\s\S]*\})\s*```"` — das `*` muss greedy sein, nicht `*?` (sonst stoppt es beim ersten `}`)
- Variablen definieren bevor sie benutzt werden — `const stat = data.statistik || {}` muss vor `stat.tore_team_a` stehen (verursachte "stat is not defined" Fehler im Dashboard)

### JSON / Gemini-Output
- Gemini gibt manchmal abgeschnittenes JSON zurück — deshalb `_repariere_json()` und `max_output_tokens=65536`
- Falls JSON nicht reparierbar: Fallback `{"rohdaten": roh_text}` — Dashboard hat Fallback der `rohdaten` versucht zu parsen
- `rohdaten`-Fallback im Dashboard: `if (data.rohdaten && !data.ereignisse) { JSON.parse(data.rohdaten) }`

### Dashboard
- Wenn `div#main` leer bleibt: Ursache ist fast immer ein JS-Fehler im `baueDashboard()`-Aufruf — Browser-Konsole prüfen (F12)
- Statistik-Felder aus Gemini sind unzuverlässig → Schusseffizienz, xGoals usw. immer selbst aus Events berechnen, nur Tore aus `tore_team_a`/`b`
