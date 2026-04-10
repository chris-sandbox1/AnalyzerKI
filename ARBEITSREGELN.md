# Arbeitsregeln – Floorball Analyzer Projekt

## Projektstruktur (alle Dateien in `floorball-analyzer/`)

| Datei | Zweck |
|---|---|
| `main.py` | Einstiegspunkt: Video besorgen, Auflösung/Länge prüfen, Analyse steuern, JSON speichern |
| `analyzer.py` | Gemini-API-Aufruf: Video hochladen, Prompt senden, JSON zurückgeben |
| `downloader.py` | yt-dlp: YouTube-Video auf max. 480p herunterladen (`restrictfilenames: True` → ASCII) |
| `start.py` | HTTP-Server auf Port 8080, liefert `/analyses`-Route |
| `dashboard.html` | Web-UI, läuft unter `localhost:8080/dashboard.html` |
| `analyses/` | Gespeicherte Spiel-JSONs + `index.json` + `data.js` |
| `.env` | `GEMINI_API_KEY=...` (nicht im Repo) |
| `ARBEITSREGELN.md` | Diese Datei |

**Starten:** Zuerst `python start.py`, dann Browser auf `localhost:8080/dashboard.html`. Neue Analyse: `python main.py` in separatem Terminal.

---

## Gemini-Output-Format (aktuell)

Gemini gibt JSON zurück. **Kein x/y mehr** — Events haben `zone` statt Koordinaten.

```json
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
      "details": "Eriksson gewinnt Ball gegen #9"
    }
  ],
  "statistik": {
    "tore_team_a": 2, "tore_team_b": 1,
    "torschuesse_team_a": 10, "torschuesse_team_b": 8,
    "konter_gesamt": 3, "chancen_gesamt": 5,
    "penalties_team_a": 0, "penalties_team_b": 1
  }
}
```

**Erlaubte Event-Typen:** `TOR`, `TORSCHUSS`, `BALLBESITZWECHSEL`, `KONTER`, `CHANCE`, `PENALTY`, `UEBERZAHL_TOR`, `UNTERZAHL_TOR`, `PENALTY_SHOT`, `FACE_OFF_GEWONNEN`, `ZWEIKAMPF`

**Zonen-System — 9 Bereiche** (immer aus Team-A-Perspektive, greift nach rechts):
```
EIGN_TOR | EIGN_TORRAUM | EIGN_SLOT | EIGN_HALB | RUECKRAUM | GEGN_HALB | GEGN_SLOT | GEGN_TORRAUM | GEGN_TOR
```
Für Schüsse/Tore/Chancen kommt ein Suffix `_MITTE`, `_OBEN` oder `_UNTEN` dazu.
Für Zweikampf/Konter nur der Basisbereich ohne Suffix.
Penalty-Schuss: `zone = "PENALTY"`.

**Wichtig:** Statistik-Felder von Gemini sind unzuverlässig. Im Dashboard werden Schusseffizienz, xGoals etc. immer selbst aus den Events berechnet. Nur `tore_team_a`/`tore_team_b` werden aus der Statistik übernommen (und mit Event-Zählung verglichen).

---

## Dashboard — Aktueller Stand

### Tabs
1. **Übersicht** — Score Hero, Zusammenfassung, Statistik-Bars, Strafzeiten
2. **Spielfeld** — SVG-Spielfeld mit allen Events als Dots, Heatmap/Zonen/Klar-Toggle, Perioden-Zeitstrahl
3. **Zeitstrahl** — Chronologische Liste aller Events mit Filter
4. **Spieler** — Spieler-Statistiken (Tore, Schüsse, Zweikämpfe)

### Score Hero (Übersicht-Tab)
- Zeigt Ergebnis: `[Team A] [Tore A] — [Tore B] [Team B]` groß und direkt auf dem Aurora-Hintergrund (kein Glaskasten)
- Mittelkarte (Spieltitel, Datum, Dauer) hat wieder einen Glaskasten (`glass match-card`)
- Gap zwischen Score-Zahlen und Mittelkarte: `40px`

### Spielfeld-Tab
- SVG `viewBox="0 0 820 400"`, Feld: `x=55..765`, `y=18..382` (710px breit, 364px hoch)
- Events als SVG-Kreise (`<circle class="feld-dot">`) mit `data-event-id` (= Index im `ereignisse`-Array)
- **Zone-Hintergrund-Toggle** (oben rechts über dem Feld):
  - **Heatmap** (Default): grüne/orange SVG-Rechtecke pro Zone, Intensität = Event-Häufigkeit / Maximum
  - **Zonen**: nur subtile Trennlinien (8 vertikale + 2 horizontale Drittellinien)
  - **Klar**: kein Hintergrund
- **Perioden-Zeitstrahl** unter dem Feld: Dots auf Zeitachse pro Periode, mit `data-event-id`
- **Cross-Highlight**: Spielfeld-Dot hovern → Perioden-Dot leuchtet auf (scale 1.8) und umgekehrt
- **Tooltips**: Hover auf Dot/Perioden-Dot/Zeitstrahl-Zeile → Tooltip mit Timestamp, Typ, Zone, Details

### Hover-Tooltip-System
- `#feld-tooltip`: `position: absolute` innerhalb `.field-card` → für Spielfeld-Dots
- `#hover-tooltip`: `position: fixed` am Ende von `<body>` → für Perioden-Zeitstrahl und Zeitstrahl-Tab
- `zeigeHoverTooltip(html, ankerEl)` und `versteckeHoverTooltip()` als globale Hilfsfunktionen
- `baueTooltipHTML(ev, col)` erzeugt einheitliches Tooltip-HTML für alle Stellen
- `initialisiereTooltips()` nutzt `fc._ttInit`-Flag um doppelte Listener zu verhindern
- `bindFeldDots(fc, tt, CA, CB)` wird bei Modus-Wechsel neu aufgerufen (Dots werden neu gerendert)

### CSS-Variablen & Design-System
```css
:root {
  --color-a: #4ade80;   /* Team A — grün */
  --color-b: #fb923c;   /* Team B — orange */
  --bg: #080810;
  --glass-bg: rgba(255,255,255,.04);
  --glass-border: rgba(255,255,255,.09);
  --topbar-h: 54px;
}
.glass { background: var(--glass-bg); backdrop-filter: blur(4px); border: 0.5px solid var(--glass-border); border-radius: 10px; }
```
- Score Hero: `background: none !important; border: none !important; backdrop-filter: none !important;`
- Tabs: `font-size: 13px; font-weight: 500; letter-spacing: .02em;`
- Logo: Text-only `Floorball<span>IQ</span>`, kein Icon
- Corner-Blobs: 4 subtile, blurry, pulsierende Kreise in den Ecken von `#bg-layer`
- Stat-Bars: wachsen bidirektional von der Mitte (`scaleX`, `transform-origin: right/left`)

### JS-Schlüssel-Globals
```js
let aktuelleTeams = [];   // [teamA-Name, teamB-Name]
let aktuelleData  = null; // aktuelles Spiel-JSON
let aktiverFilter = 'alle';
let aktiverZtFilter = 'alle';
let spielerSortierung = 'tore';
let aktiverFeldModus = 'heatmap'; // heatmap | zonen | klar
```

### Koordinaten-Umrechnung (Zone → SVG)
```
zBounds = [0, 2.5, 7, 12, 17.5, 22.5, 28, 33, 38, 40]  (Feldmeter)
x = 55 + (zBounds[z] / 40) * 710
y (vertikal): OBEN = fY + drittelH*0.5, MITTE = fY + drittelH*1.5, UNTEN = fY + drittelH*2.5
```
`feldZuSVG(fx, fy)` für Meter-Koordinaten: `x = 55 + (fx/40)*710`, `y = 382 - (fy/20)*364`

---

## Kommunikation & Planung
- Bevor du anfängst zu coden: Erkläre deinen Plan in verständlicher Sprache
- Warte auf meine explizite Bestätigung, bevor du Änderungen machst
- Erkläre auf Deutsch, was du tust und warum — ich bin kein Entwickler
- Wenn etwas unklar ist, frag nach, anstatt Annahmen zu treffen

## Coding-Stil
- Halte alles so einfach wie möglich
- Keine unnötigen Abhängigkeiten oder Libraries
- Kommentiere Code auf Deutsch wenn hilfreich
- Bestehenden Code immer gezielt bearbeiten — nicht komplett neu schreiben wenn nicht nötig
- Nur die minimal nötigen Änderungen machen
- Vor jeder Änderung die betroffene Datei lesen und verstehen

## Git-Regeln
- Commiten und Pushen nur wenn der Nutzer explizit darum bittet
- Commit und Push zusammen (nicht nachfragen ob Push gewünscht) wenn Nutzer "push" sagt

---

## Projekt-Technologie-Stack

### Gemini API
- Modell: `gemini-2.5-flash` (in `analyzer.py`)
- Temperature: `0.1`, max_output_tokens: `65536`
- SDK: `google.genai` mit `types.Part.from_uri` und `types.GenerateContentConfig`
- Kein Kontext-Caching, kein Regelwerk-PDF — Gemini kennt Floorball aus eigenen Trainingsdaten
- Prompt-Platzhalter mit `.replace("{periode_kontext}", ...)` — **NICHT** `.format()`, da der Prompt JSON-Beispiele mit `{}` enthält → KeyError!

### Video-Pipeline
- Download: `yt-dlp` via `downloader.py`, max. 480p, `restrictfilenames: True` (→ ASCII-Dateinamen, kein Sonderzeichen-Problem)
- Lokale Dateien: Auflösung per `ffprobe` prüfen, bei > 480p automatisch mit `ffmpeg` auf 480p skalieren (temporäre Datei, nach Analyse gelöscht)
- Videolänge: unter 35 Min direkt, 35–70 Min → Nutzer fragt nach 2 Hälften, über 70 Min → nach 3 Perioden
- Schneiden: `ffmpeg -c copy` (verlustfrei, schnell)
- ffmpeg muss im PATH sein (`winget install Gyan.FFmpeg --scope user`)

### Server & Dashboard
- Server: `start.py`, Port `8080`, Route `/analyses` liefert JSON-Liste
- Dashboard: `dashboard.html`, läuft unter `localhost:8080/dashboard.html`
- Analysen in `analyses/` als JSON + `analyses/index.json` + `analyses/data.js`
- `data.js` ermöglicht direktes Öffnen ohne Server (file://-Protokoll)

---

## Bekannte Fallstricke & frühere Fehler

### Python
- `.format()` auf Prompt-Strings → Fehler wenn Prompt JSON-Beispiele enthält → immer `.replace()` nutzen
- `_repariere_json()` nötig weil Gemini Antwort manchmal abbricht → Stack-basierter Rückwärts-Scan
- `os.chdir(os.path.dirname(os.path.abspath(__file__)))` in `main.py` Pflicht (falsches Arbeitsverzeichnis bei Doppelklick-Start)
- `beenden()` mit `input("Drücke Enter...")` damit Terminal bei Fehler nicht sofort schließt
- Greedy Regex für JSON-Extraktion: `r"```(?:json)?\s*(\{[\s\S]*\})\s*```"` — `*` muss greedy sein (nicht `*?`)

### JSON / Gemini-Output
- Gemini gibt manchmal abgeschnittenes JSON → `_repariere_json()` und `max_output_tokens=65536`
- Fallback `{"rohdaten": roh_text}` wenn JSON nicht reparierbar; Dashboard versucht `JSON.parse(data.rohdaten)`

### Dashboard
- Wenn `div#main` leer bleibt: Ursache ist fast immer ein JS-Fehler in `baueDashboard()` → Browser-Konsole (F12)
- `baueDashboard()` baut `div#main` komplett als `innerHTML`-String — kein direktes DOM-Manipulation danach
- Statistik von Gemini unzuverlässig → Schusseffizienz, xGoals etc. immer aus Events berechnen
- `const stat = data.statistik || {}` muss **vor** der Nutzung definiert sein (→ "stat is not defined" Fehler)
- Doppelte Event-Listener auf `.field-card` verhindern mit `fc._ttInit`-Flag
- `setzeZonenModus()` ruft nur `baueFeld()` + `bindFeldDots()` neu auf (nicht den ganzen Tab) — SVG-Wrapper: `<div id="feld-svg-wrap">`
- `data-event-id` = `ereignisse.indexOf(ev)` — funktioniert weil `sortiert` dieselben Objekt-Referenzen hat
