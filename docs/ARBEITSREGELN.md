# Arbeitsregeln – Floorball Analyzer Projekt

## Projektstruktur (alle Dateien in `floorball-analyzer/`)

| Datei | Zweck |
|---|---|
| `main.py` | Einstiegspunkt: Video besorgen, Auflösung/Länge prüfen, Analyse steuern, JSON speichern |
| `analyzer.py` | Gemini-API-Aufruf: Video hochladen, Prompt senden, JSON zurückgeben |
| `downloader.py` | yt-dlp: YouTube-Video auf max. 480p herunterladen |
| `start.py` | HTTP-Server auf Port 8080, liefert `/analyses`-Route |
| `dashboard.html` | Web-UI, läuft unter `localhost:8080/dashboard.html` |
| `analyses/` | Gespeicherte Spiel-JSONs + `index.json` + `data.js` |
| `.env` | `GEMINI_API_KEY=...` (nicht im Repo) |
| `ARBEITSREGELN.md` | Diese Datei |

**Starten:** Zuerst `python start.py`, dann Browser auf `localhost:8080/dashboard.html`. Neue Analyse: `python main.py` in separatem Terminal.

## Gemini-Output-Format

Gemini gibt JSON zurück mit diesen Feldern:
```json
{
  "zusammenfassung": "...",
  "ereignisse": [
    { "timestamp": "MM:SS", "typ": "TOR", "team": "TeamA", "x": 38.0, "y": 10.0, "beschreibung": "..." }
  ],
  "statistik": {
    "tore_team_a": 3, "tore_team_b": 2,
    "torschuesse_team_a": 12, "torschuesse_team_b": 8,
    "konter_gesamt": 4, "chancen_gesamt": 6,
    "penalties_team_a": 1, "penalties_team_b": 2
  }
}
```

**Erlaubte Event-Typen:** `TOR`, `TORSCHUSS`, `BALLBESITZWECHSEL`, `KONTER`, `CHANCE`, `PENALTY`, `UEBERZAHL_TOR`, `UNTERZAHL_TOR`, `PENALTY_SHOT`, `FACE_OFF_GEWONNEN`

**Wichtig:** Statistik-Felder aus Gemini sind unzuverlässig. Im Dashboard werden Schusseffizienz, xGoals etc. immer selbst aus den Events berechnet. Nur `tore_team_a`/`tore_team_b` werden aus der Statistik übernommen (und mit Event-Zählung verglichen).



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
- Nie ohne ausdrückliche Aufforderung commiten oder pushen
- Commit + Push nur wenn explizit darum gebeten — beides zusammen ist okay wenn der Nutzer „push" sagt
- Branch ist `saisonmanager` (nicht `main`) — immer prüfen auf welchem Branch gearbeitet wird
- Änderungen in `saisonmanager.html` werden auf GitHub Pages erst nach dem Push sichtbar (Deployment ~1–2 Min)

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

## saisonmanager.html — Liga-Statistiken & PWA

### Projektstruktur (neu, ab April 2026)

| Datei | Zweck |
|---|---|
| `saisonmanager.html` | Haupt-App: Tabelle, Scorer, Spielplan, Turnierbaum, Alltime, Team-Detail |
| `manifest.json` | PWA-Manifest (start_url + scope: `/AnalyzerKI/`) |
| `service-worker.js` | Cache-first für App-Shell, Network-pass für saisonmanager.de API |
| `icons/App_Logo.png` | Quell-Logo (1254×1254 px, RGBA) — Basis für alle Icon-Größen |
| `icons/icon-192.png`, `icon-512.png` | PWA-Icons (per Python/Pillow via LANCZOS aus App_Logo.png skaliert) |
| `data/alltime.json` | Alltime-Spieler + Teams (via `tools/alltime.py` erzeugt) |
| `data/team_rosters.json` | Team-Kader für Alltime-DE-Tab |
| `tools/alltime.py` | Einmaliger Batch-Job: lädt alle Ligen von der API, aggregiert, speichert |

**API-Basis:** `https://saisonmanager.de/api/v2`
**GitHub Pages Pfad:** `/AnalyzerKI/` — dieser Prefix muss in manifest + SW überall stehen.
**Branch:** `saisonmanager` (nicht `main`) — GitHub Pages deployed von diesem Branch.

### Tab-Struktur (Stand April 2026)

5 Tabs: `tabelle`, `spielplan`, `scorer`, `detail`, `alltime`
```js
const tabIds = ['tabelle','spielplan','scorer','detail','alltime'];
```
- **Alltime** enthält zwei Sub-Panels: „Verband" (Live-API) und „🇩🇪 Deutschland" (statisch aus `alltime.json`)
- Umschalten per `setAlltimeSubTab('verband' | 'deutschland')` → zeigt/versteckt `#alltime-verband-panel` / `#alltime-deutschland-panel`
- `tab-static` existiert nicht mehr als eigene Section — Inhalt lebt jetzt in `#alltime-deutschland-panel` innerhalb `#tab-alltime`
- Beide Datenquellen (live + static) werden geladen sobald der Alltime-Tab das erste Mal geöffnet wird

### Mobile Header (Stand April 2026)

- Header ist 2-zeilig auf Mobile (`flex-wrap: wrap`):
  - Zeile 1: Logo (`IQ`) + hd-space
  - Zeile 2: `#mob-dropdowns` mit `#verband-select-mob` + `#liga-select-mob`
- `#liga-bar` (Desktop-Auswahlleiste) ist auf Mobile komplett ausgeblendet (`display: none !important`)
- Mobile-Selects werden beim Laden in `ladeLigen()` und `befuelleLigaDropdown()` synchronisiert
- `onVerbandMob()` / `onLigaMob()` synchronisieren zurück auf die Desktop-Selects und rufen `onVerband()` / `onLiga()` auf
- `--subbar-h: 0px` auf Mobile (statt 44px), `padding-top: 100px !important` auf `.tab-content` um den 2-zeiligen Header zu kompensieren

### Logo-Muster

```html
<div class="logo-text"><span class="logo-full">Floorball</span><span class="logo-iq">IQ</span></div>
```
```css
.logo-text .logo-iq { color: var(--color-a); border-bottom: 1.5px solid var(--color-a); }
@media (max-width: 768px) { .logo-full { display: none; } }
```
**Wichtig:** NICHT `.logo-text span { ... }` verwenden — das trifft alle Kind-Spans (inkl. `.logo-full`) und macht dann auch „Floorball" grün. Immer eine spezifische Klasse für den farbigen Teil.

### Pull-to-Refresh

- Auf Mobile ersetzt eine Wisch-Geste (80 px nach unten, wenn `scrollY === 0`) den Refresh-Button
- `#ptr-indicator` (grünes Pill, `position: fixed`) wird kurz eingeblendet, dann `datenGeladen = false; ladeDaten()`
- Refresh-Button (`.btn-refresh`) auf Mobile via `display: none !important` ausgeblendet
- Touch-Events mit `{ passive: true }` — kein `preventDefault()` nötig

### Datenfluss & wichtige State-Variablen

- `alleligen` — alle Ligen aus `leagues.json`, einmal beim Start geladen
- `alltimeRohdaten` — Array von `{ ligaId, ligaName, saison, scorer, table }` — die Rohdaten für den aktiven Verband; wird bei Verbandswechsel geleert
- `alltimeDaten` — aggregierte Spieler + Teams; wird aus `alltimeRohdaten` durch `aggregiereAlltime()` berechnet
- `alltimeLigaFilter` (Set) — ausgewählte Liga-IDs; leer = alle (außer `alltimeLigaNoneMode`)
- `alltimeGender` — `'alle'` / `'herren'` / `'damen'`
- `alltimeSubTab` — `'verband'` | `'deutschland'` — aktives Sub-Panel im Alltime-Tab
- `vorherTab` — merkt sich den Tab vor einer Spiel-Detail-Navigation, damit Zurück-Taste stimmt

### Wichtige Funktionen & Muster

**Liga-Dropdown:** `befuelleLigaDropdown()` soll immer die neueste Saison vorauswählen — per `.reduce()` die höchste `season`-Zahl finden, nicht alphabetisch sortieren und nicht hardcoded.

**Alltime-Filter:** `aggregiereUndRenderAlltime()` filtert `alltimeRohdaten` nach `alltimeLigaFilter` und ruft dann `renderAlltime()` auf. Jede Funktion die eigene Rosters baut (z. B. `bauldeAlltimeKaderRosters()`) muss dieselbe Filterlogik selbst anwenden:
```js
const quelldaten = (!alltimeLigaFilter.size && !alltimeLigaNoneMode)
  ? alltimeRohdaten
  : alltimeRohdaten.filter(e => alltimeLigaFilter.has(e.ligaId));
```
Und Gender-Filter: `istDamen(e.ligaName)` für jedes Entry prüfen.

**`renderAlltime()` steuert Controls:** Diese Funktion entscheidet welche Filter-Buttons in der Control-Leiste ein- oder ausgeblendet werden. Bei neuen Views immer prüfen welche Controls sinnvoll sind und ob `style.setProperty('display', ...)` alle relevanten Elemente erfasst.

**Tab-Navigation mit Rücksprung:** Pattern `vorherTab = aktiverTab` vor dem Wechsel, in `zeigSpielplan()` zurücknavigieren wenn `vorherTab !== 'spielplan'`.

**serienKey (Turnierbaum):** Immer über sortierte Team-**Namen** (nicht IDs), da `team_id` in `schedule.json` häufig fehlt:
```js
function serienKey(s) {
  return [s.home_team_name || '', s.guest_team_name || ''].sort().join('|||');
}
```

**Mobile CSS:** `@media (max-width: 768px)`, Klasse `col-hide-mob` auf `<th>` + `<td>` für unwichtige Spalten, `overflow-x: auto` auf `.glass`-Wrappern.

### Bekannte Fallstricke — saisonmanager.html

- **SyntaxError "Unexpected end of input":** Ursache war eine Funktion mit öffnendem `{` aber ohne Body und schließendes `}`. Alle folgenden Funktionen wurden als ihr Inhalt interpretiert → am Script-Ende fehlte eine Klammer. Backtick-Balancing war korrekt (kein offenes Template Literal) — das war eine Falle.
- **Backtick-Zähler als Debugging-Tool unzuverlässig:** Regex-Pattern wie `/'/g` innerhalb von Template Literals bringen einfache Python-Zähler durcheinander. Node.js `--check` ist die zuverlässige Methode; ohne Node.js besser auf Klammer-Ebene manuell debuggen.
- **Filter-Isolation:** Neue Berechnungsfunktionen, die `alltimeRohdaten` direkt konsumieren, erben nicht automatisch `alltimeLigaFilter` oder `alltimeGender` — diese müssen immer explizit angewendet werden.
- **PWA GitHub Pages:** scope und start_url müssen exakt `/AnalyzerKI/` enthalten — ein fehlender Trailing Slash oder falscher Pfad verhindert die Installation.
- **Liga-Multiselect startet mit `display:none`:** `alltime-liga-wrap` ist im HTML initial versteckt. `renderAlltime()` muss es explizit einblenden (nicht nur den `isKader`-Zustand toggeln).
- **`overflow-x: hidden` auf `body`/`html` bricht `position: fixed` auf iOS Safari:** Aurora-Blobs, Bottom-Nav und alle anderen `fixed`-Elemente verschwinden auf iPhone wenn `overflow-x: hidden` auf dem `body` sitzt. NIEMALS `overflow-x: hidden` auf `html` oder `body` setzen. Stattdessen `overflow: hidden` nur auf Wrapper-Divs verwenden.
- **`env(safe-area-inset-bottom)` funktioniert nicht ohne `viewport-fit=cover`:** Im Viewport-Meta-Tag muss `viewport-fit=cover` stehen, sonst ignoriert iOS die `env()`-Funktion. Gilt für alle Safe-Area-Insets (top/bottom/left/right).
- **Logo-CSS und generische `span`-Selektoren:** `.logo-text span { color: green }` trifft ALLE Kind-Spans. Wenn mehrere Spans im Logo-Element existieren (z. B. `.logo-full` + `.logo-iq`), immer spezifische Klassen für den farbigen Teil verwenden: `.logo-text .logo-iq { ... }`.
- **Mobile-Selects müssen manuell synchronisiert werden:** `#verband-select-mob` und `#liga-select-mob` sind Duplikate der Desktop-Selects. Bei jedem Befüllen der Desktop-Selects (in `ladeLigen()`, `befuelleLigaDropdown()`, `onVerband()`) die Mobile-Selects manuell nachziehen, sonst zeigen sie veraltete Werte.
- **`zeigeTab()` kennt nur 5 Tab-IDs:** Nach dem Alltime-Merge ist `tabIds = ['tabelle','spielplan','scorer','detail','alltime']`. Kein `static` mehr — `zeigeTab('static')` würde `getElementById('tab-static')` aufrufen und einen Fehler werfen.

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
