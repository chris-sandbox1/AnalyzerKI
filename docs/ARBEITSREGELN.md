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

6 Tabs: `overview`, `tabelle`, `spielplan`, `scorer`, `detail`, `alltime`
```js
const tabIds = ['overview','tabelle','spielplan','scorer','detail','alltime'];
```
- **Overview** ist erster Tab (Desktop) / Home-Icon Bottom-Nav (Mobile) — lädt alle Ligen der aktuellen Saison parallel
- **Alltime** enthält zwei Sub-Panels: „Verband" (Live-API) und „🇩🇪 Deutschland" (statisch aus `alltime.json`)
- Umschalten per `setAlltimeSubTab('verband' | 'deutschland')` → zeigt/versteckt `#alltime-verband-panel` / `#alltime-deutschland-panel`
- `tab-static` existiert nicht mehr als eigene Section — Inhalt lebt jetzt in `#alltime-deutschland-panel` innerhalb `#tab-alltime`
- Beide Datenquellen (live + static) werden geladen sobald der Alltime-Tab das erste Mal geöffnet wird

### Overview-Tab (Stand April 2026)

- **Block 1**: Live & Heute — horizontale Scroll-Reihe, `Mein Team` gepinnt oben
- **Block 2 + 3 nebeneinander** (Desktop: CSS Grid `ov-b2b3-grid 1fr 1fr`, Mobile: gestackt)
  - Block 2: Nächste Spiele — 5 Karten Preview, expandierbar zu allen zukünftigen Spielen (gruppiert nach Datum)
  - Block 3: Zuletzt gespielt — 5 Karten Preview, expandierbar zu allen vergangenen Spielen (neueste zuerst)
- **Block 4**: Pro Verband 2 Spalten (`ov-vb-cols`): links „Nächste Spiele" (max 5), rechts „Letzte Spiele" (max 5)
- **Mehr anzeigen-Logik**: `ovToggleMehr(previewId, fullId)` — reine show/hide, keine API-Calls. Preview und Full als separate Divs im HTML; Button wechselt zwischen beiden.
- **Settings**: Zahnrad-Button im Block-1-Header → `toggleOverviewSettings()` → `renderSettingsPanel()`
- **Sidebar** (nur Desktop): Top-5-Tabelle der aktuell gewählten Liga (`bautSidebarTabelle()`)
- **State**: `overviewGeladen`, `overviewDaten: [{liga, spiele}]`, `overviewSettings` (localStorage `fiq-overview-settings`)
- `ladeOverview()` wartet per Polling (200ms Intervall) auf `alleligen.length > 0` bevor sie startet
- Aktuelle Saison = höchste `season`-Nummer über alle Ligen

### CSS-Design-Variablen (Stand April 2026)

```css
:root {
  --color-a: #4ade80;          /* Grün (Team A / Akzent) */
  --color-b: #fb923c;          /* Orange (Team B) */
  --bg: #0d0d18;               /* Hintergrundfarbe */
  --glass-bg: rgba(255,255,255,.07);     /* Karten-Hintergrund (war .04, erhöht für Kontrast) */
  --glass-border: rgba(255,255,255,.13); /* Karten-Rahmen (war .09) */
  --topbar-h: 54px;
  --mob-header-content: 68px;  /* Höhe des Mobile-Headers unterhalb der Safe Area */
}
```
`--glass-bg` und `--glass-border` steuern den Kontrast aller `.glass`-Elemente. Wenn Karten zu wenig vom Hintergrund abheben → diese beiden Werte erhöhen.

### Mobile Header (Stand April 2026)

- Header ist einzeilig auf Mobile (`flex-wrap: nowrap`):
  - Links: Logo (`IQ`)
  - Rechts: `#mob-dropdowns` mit `#verband-select-mob` + `#liga-select-mob` **vertikal gestapelt** (`flex-direction: column`)
- `#liga-bar` (Desktop-Auswahlleiste) ist auf Mobile komplett ausgeblendet (`display: none !important`)
- Safe Area: `padding-top: calc(env(safe-area-inset-top) + 8px)` im Header → schiebt Inhalt unter iOS-Statusleiste
- `--mob-header-content: 68px` CSS-Variable; Header hat `min-height: calc(env(safe-area-inset-top) + 68px)` und `.tab-content` hat exakt dasselbe `padding-top` → kein Gap
- Mobile-Selects werden beim Laden in `ladeLigen()` und `befuelleLigaDropdown()` synchronisiert
- `onVerbandMob()` / `onLigaMob()` synchronisieren zurück auf die Desktop-Selects und rufen `onVerband()` / `onLiga()` auf

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
- `alltimeNurAktuell` — `true` = nur Ligen der aktuellen Saison geladen (Default), `false` = alle Archiv-Saisons; wird bei Verbandswechsel auf `true` zurückgesetzt
- `alltimeSubTab` — `'verband'` | `'deutschland'` — aktives Sub-Panel im Alltime-Tab
- `vorherTab` — merkt sich den Tab vor einer Spiel-Detail-Navigation, damit Zurück-Taste stimmt

### Wichtige Funktionen & Muster

**Liga-Dropdown:** `befuelleLigaDropdown(verband)` soll immer die neueste Saison vorauswählen — per `Math.max(...)` die höchste `season`-Zahl finden, nicht alphabetisch sortieren und nicht hardcoded. Dropdown nutzt `<optgroup label="Aktuelle Saison">` und `<optgroup label="Archiv">`. Vorauswahl per Score-Logik: Nicht-Damen-Liga +2, Name beginnt mit „1." +1 — wählt so immer die Herren 1. Liga als Default.

**Dropdown-Sperr-Logik:** `aktualisiereDropdownStatus()` deaktiviert Verband- und Liga-Select je nach aktivem Tab. Overview: beide gesperrt. Alltime-Deutschland: beide gesperrt. Alltime-Verband: nur Liga gesperrt. Wird immer am Ende von `zeigeTab()` aufgerufen. Mobile-Selects (`-mob`-Sufffix) werden synchron gesperrt.

**Spielplan-Navigation aus Overview:** `zeigVerbandSpielplan(vb)` setzt den Verband-Select, ruft `befuelleLigaDropdown(vb)` auf (wählt beste Liga automatisch), dann `zeigeTab('spielplan')` und `ladeDaten()`. So landet der Nutzer direkt auf dem richtigen Verband+Liga im Spielplan-Tab.

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
- **iOS WebKit rendert `filter: blur()` NICHT in `position: fixed; overflow: hidden` Containern (PWA-Modus):** Aurora-Blobs und Corner-Blobs werden in der installierten PWA komplett unsichtbar. **Fix:** (1) `#bg-layer` von `overflow: hidden` → `overflow: clip` ändern — `clip` erstellt kein neues BFC und triggert den iOS-Bug nicht. (2) Alle `filter: blur(Xpx)` auf Blob-Elementen durch `radial-gradient(ellipse at center, rgba(...) 0%, transparent 70%)` ersetzen — optisch identisches weiches Leuchten, kein Filter. Blob-Größe ca. 1,4× größer als mit Blur wählen, da Gradient schon weich ausläuft. `overflow: clip` wird ab iOS 16 unterstützt.
- **`env(safe-area-inset-bottom)` funktioniert nicht ohne `viewport-fit=cover`:** Im Viewport-Meta-Tag muss `viewport-fit=cover` stehen, sonst ignoriert iOS die `env()`-Funktion. Gilt für alle Safe-Area-Insets (top/bottom/left/right).
- **Logo-CSS und generische `span`-Selektoren:** `.logo-text span { color: green }` trifft ALLE Kind-Spans. Wenn mehrere Spans im Logo-Element existieren (z. B. `.logo-full` + `.logo-iq`), immer spezifische Klassen für den farbigen Teil verwenden: `.logo-text .logo-iq { ... }`.
- **Mobile-Selects müssen manuell synchronisiert werden:** `#verband-select-mob` und `#liga-select-mob` sind Duplikate der Desktop-Selects. Bei jedem Befüllen der Desktop-Selects (in `ladeLigen()`, `befuelleLigaDropdown()`, `onVerband()`) die Mobile-Selects manuell nachziehen, sonst zeigen sie veraltete Werte.
- **`zeigeTab()` kennt 6 Tab-IDs:** `tabIds = ['overview','tabelle','spielplan','scorer','detail','alltime']`. Kein `static` mehr — `zeigeTab('static')` würde `getElementById('tab-static')` aufrufen und einen Fehler werfen.
- **`ovToggleMehr()` erwartet IDs im DOM:** Die Funktion greift auf `getElementById()` zu — die IDs (`ov-b2-preview`, `ov-b3-preview`, `vb0-np` etc.) existieren nur nach `renderOverview()`. Nie `ovToggleMehr()` vor dem ersten Render aufrufen.
- **`col-hide-mob` global vs. Tabelle:** `col-hide-mob` blendet Spalten auf Mobile aus. Wenn auch Tabellen-spezifische Spalten (OTS, OTN, T:G, Diff) ausgeblendet werden sollen, NICHT global mit `col-hide-mob` arbeiten — stattdessen separaten Override: `.tabelle-table .col-hide-mob { display: table-cell !important; }`. Oder eigene Klassen pro Kontext verwenden.
- **Service Worker Cache-Name muss bei jeder Deployment-Änderung hochgezählt werden:** `CACHE_NAME = 'floorballiq-vX'` — PWA lädt sonst die alte gecachte HTML-Datei. Jede inhaltliche Änderung → Cache-Version erhöhen → SW-Datei mitcommiten. Aktuell `v5`.
- **Bottom-Nav aktiver Startzustand muss im HTML UND per `zeigeTab()` gesetzt werden:** HTML-Klasse `class="bnav-item active"` auf dem korrekten Button, und im Init-Code `zeigeTab('overview')` statt manuell `aktualisiereDropdownStatus()` aufzurufen. `zeigeTab()` synchronisiert Desktop-Tabs, Bottom-Nav und Dropdown-Status in einem Aufruf. NIEMALS den aktiven Status nur im HTML hardcoden ohne auch `zeigeTab()` im Init zu rufen.
- **`#ov-settings-overlay` hat z-index:149 > Bottom-Nav:** Der Settings-Overlay liegt über der Bottom-Nav (z-index:100). Falls der Overlay versehentlich offen bleibt, blockiert er alle Klicks auf die Navigation. Fix: Bottom-Nav z-index auf 200 erhöhen. Alle zukünftigen Fix/Overlay-Elemente sollten unter 200 bleiben ODER `pointer-events: none` haben wenn sie nicht geklickt werden müssen.
- **`zeigSpielDetail()` und `zeigeTeamDetail()` müssen try/catch haben:** Ungefangene Fehler in diesen Funktionen können JS-Ausführung in der aktuellen Event-Handler-Chain abbrechen. Immer Fehler abfangen und einen Fallback (Zurück-Button + Error-Box) zeigen. Besonders wichtig: Im Error-Case von `zeigSpielDetail` den Zurück-Button trotzdem rendern, sonst steckt der Nutzer ohne Navigationsmöglichkeit fest.
- **`inset: 0` ist auf iOS 14 nicht vollständig unterstützt:** Für `#bg-layer` und andere Full-Screen-Fixed-Elemente immer `top:0; left:0; width:100%; height:100%` statt `inset:0` verwenden. `inset` wurde erst in iOS 15 vollständig unterstützt.
- **Aurora-Blob-Farben müssen die App-CSS-Variablen widerspiegeln:** `--color-a: #4ade80` = `rgba(74,222,128,...)`, `--color-b: #fb923c` = `rgba(251,146,60,...)`. Nicht `#10b981` (Tailwind green-500) oder `#f97316` (orange-500) verwenden — diese sehen anders aus. Corner-Blob-Positionen: grün oben-links + unten-rechts, orange oben-rechts + unten-links.
- **`@media (display-mode: standalone)` für PWA-spezifische Fixes:** Wenn ein Element in der installierten PWA nicht sichtbar ist aber im Browser schon, `@media (display-mode: standalone) { ... }` nutzen um PWA-spezifische Overrides zu setzen (z.B. `display: block !important` auf Blobs, `opacity: 1` auf bg-layer).
- **Alltime lädt nur aktuelle Saison (Default) — Archiv per Klick:** `getAktivVerbandSaisons(nurAktuell)` filtert bei `nurAktuell=true` auf die höchste `season`-Nummer. `ladeAlltimeDaten()` startet immer mit `alltimeNurAktuell=true`. Nach dem Laden erscheint ein Banner „X weitere Saisons im Archiv. [Alle Saisons laden]". Klick ruft `ladeAlleAlltimeSaisons()` auf, das `alltimeNurAktuell=false` setzt und neu lädt. Bei Verbandswechsel (`onVerband()`) immer `alltimeNurAktuell = true` zurücksetzen.
- **HTTP-500-Fehler von inaktiven Ligen lautlos ignorieren:** `fetchJSON(...).catch(() => [])` reicht — kein `console.warn` und kein `console.error` auf API-Fehler im Alltime-Batch. Die Ligen existieren in `leagues.json` aber die API liefert 500 wenn die Liga inaktiv ist. Erwartetes Verhalten, kein Bug. KEIN Logging.
- **Block-4-Verband-IDs sind Index-basiert:** `vb0`, `vb1` etc. (Index in der `verbände`-Array). Die Reihenfolge ist deterministisch (Floorball Deutschland zuerst, dann alphabetisch). Aber die IDs ändern sich wenn Verbände hinzukommen/wegfallen — kein Problem da sie bei jedem `renderOverview()` neu generiert werden.
- **`gruppiereNachDatum()` nutzt Objekt-Einfüge-Reihenfolge:** Modernes JS/V8 preserviert die Einfüge-Reihenfolge von String-Schlüsseln in Objekten. Wenn das Input-Array nach Datum aufsteigend sortiert ist, ist auch das Output-Objekt aufsteigend. Für Block 3 (neueste zuerst) Input bereits absteigend sortieren.

---

## Git-Stand & offene Aufgaben (Stand April 2026)

### Aktueller Stand
- **Aktiver Branch:** `saisonmanager`
- **Letzter stabiler Commit:** `4d51da3` — fix: Mobile Header-Gap via `--mob-header-content`
  - Aktuell deployed als Revert-Commit `530731f`
- **Bekannter Broken-Commit:** `92c1e6a` — feat: Overview-Tab komplett überarbeitet
  - Dieser Commit hat einen visuellen Fehler in der App-Ansicht verursacht (genaue Ursache noch unbekannt)
  - Alle Commits ab `92c1e6a` wurden deshalb rückgängig gemacht
  - **Vor einer Neu-Implementierung des Overview-Tabs:** Diff zwischen `4d51da3` und `92c1e6a` gründlich prüfen (`git diff 4d51da3 92c1e6a -- saisonmanager.html`)

### Offene Bugs (wurden implementiert, dann revertiert — müssen neu angegangen werden)

**Bug 1 — Bottom-Nav zeigt Tabelle als aktiv beim Start:**
- `#bnav-tabelle` hatte `class="bnav-item active"` hardcodiert → auf `#bnav-overview` verschieben
- Init-Code muss `zeigeTab('overview')` aufrufen (synchronisiert alles in einem Schritt)

**Bug 2 — App hängt nach Klick auf Spiel oder Team:**
- `#ov-settings-overlay` (z-index:149) blockiert Bottom-Nav (z-index:100) wenn versehentlich offen
- Fix: Bottom-Nav z-index auf 200 erhöhen
- Zusätzlich: `try/catch` in `zeigSpielDetail()` und `zeigeTeamDetail()` — ungefangene Fehler brechen die Event-Handler-Chain ab

**Bug 3 — Aurora-Blobs in PWA unsichtbar:**
- iOS WebKit: `filter: blur()` in `position: fixed; overflow: hidden` Containern → Blobs werden weiß/unsichtbar
- Fix 1: `#bg-layer` auf `overflow: clip` statt `overflow: hidden` (kein neues BFC, triggert iOS-Bug nicht)
- Fix 2: `filter: blur(Xpx)` ersetzen durch `radial-gradient(ellipse at center, rgba(...) 0%, transparent 70%)`
- Fix 3: `#bg-layer` von `inset: 0` → `top:0; left:0; width:100%; height:100%` (iOS 14 Kompatibilität)
- Fix 4: `@media (display-mode: standalone)` Override für Aurora/Corner-Blobs
- Farben: grün (`rgba(74,222,128,...)`) oben-links + unten-rechts; orange (`rgba(251,146,60,...)`) oben-rechts + unten-links
- Corner-Blob-Größe: 400–460px, opacity ~0.13–0.15

**Problem 1 — Service Worker Pfad 404:**
- SW-Registrierung von absolutem `/AnalyzerKI/service-worker.js` → relativ `service-worker.js` mit `scope: './'`

**Problem 2 — Logo-URLs in renderSpielDetail falsch:**
- `g.home_team_logo` und `g.guest_team_logo` direkt in `<img src="">` — fehlende `logoUrl()`-Wrapper
- Fix: `src="${logoUrl(g.home_team_logo) || ''}"` und `src="${logoUrl(g.guest_team_logo) || ''}"`

**Problem 3 — Alltime lädt bis zu 500 Requests gleichzeitig:**
- `getAktivVerbandSaisons()` gibt alle historischen Ligen zurück (200-300+)
- Fix: Parameter `nurAktuell=false` hinzufügen; bei `true` nur Ligen mit der höchsten `season`-Nummer zurückgeben
- `ladeAlltimeDaten()` startet mit `alltimeNurAktuell=true` (State-Variable)
- Nach Laden: Banner anzeigen „X weitere Saisons im Archiv. [Alle Saisons laden]"
- `ladeAlleAlltimeSaisons()`: setzt `alltimeNurAktuell=false`, resettet `alltimeGeladen`, ruft `ladeAlltimeDaten()` neu auf
- `onVerband()`: `alltimeNurAktuell = true` zurücksetzen bei Verbandswechsel

**Problem 4 — HTTP-500 Konsolen-Rauschen:**
- `console.warn(...)` für fehlgeschlagene Alltime-Requests entfernen
- `.catch(() => [])` reicht — 500er von inaktiven Ligen sind erwartet, kein Logging nötig

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
