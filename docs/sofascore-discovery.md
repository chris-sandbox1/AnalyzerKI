# Sofascore Floorball API – Discovery Report
**Erstellt:** 2026-04-28  
**Branch:** internationaler-tab  
**Zweck:** API-Machbarkeitsprüfung vor Implementierung des International-Tabs

---

## 1. Basis-URL & CORS

| Parameter | Wert |
|---|---|
| API Base | `https://api.sofascore.com/api/v1` |
| Auth | Keine (öffentliche Endpunkte) |
| CORS | Blockiert im Browser → Fallback auf `https://corsproxy.io/?{encodedUrl}` |
| Rate-Limit | Nicht dokumentiert; bei normalem Polling kein Problem |

---

## 2. Getestete Endpunkte – Übersicht

### ✅ Verfügbar (HTTP 200)

| Endpunkt | Beschreibung | Beispiel |
|---|---|---|
| `/unique-tournament/{id}/season/{id}/events/last/{page}` | Vergangene Spiele, paginiert (0=neuste) | `/306/season/77638/events/last/0` |
| `/unique-tournament/{id}/season/{id}/events/next/{page}` | Zukünftige Spiele, paginiert | `/306/season/77638/events/next/0` |
| `/unique-tournament/{id}/season/{id}/events/round/{n}` | Alle Spiele einer Runde **✅ Neu!** | `/306/season/77638/events/round/1` |
| `/unique-tournament/{id}/season/{id}/standings/total` | Tabelle (Gesamtwertung) | `/306/season/77638/standings/total` |
| `/unique-tournament/{id}/season/{id}/rounds` | Rundenliste mit Namen | `/255/season/78217/rounds` |
| `/unique-tournament/{id}/season/{id}/cuptrees` | Playoff-Baum (Serien-Ergebnisse) | `/255/season/78217/cuptrees` |
| `/event/{id}/incidents` | Tore im Spielverlauf (⚠ limitiert) | `/15834256/incidents` |
| `/team/{id}/events/last/{page}` | Letzte Spiele eines Teams | `/7559/events/last/0` |
| `/sport/floorball/scheduled-events/{YYYY-MM-DD}` | Alle Spiele an einem Tag | |
| `/sport/floorball/live-events` | Aktuell laufende Spiele | |

### ❌ Nicht verfügbar (HTTP 404)

| Endpunkt | Erhoffter Inhalt |
|---|---|
| `/event/{id}/statistics` | Spielstatistiken (Schüsse, Fouls etc.) |
| `/event/{id}/lineups` | Aufstellungen / Kader |
| `/team/{id}/players` | Vereinskader |
| `/unique-tournament/{id}/season/{id}/top-players/overall` | Scorer-Liste |
| `/unique-tournament/{id}/season/{id}/top-scorers` | Topspieler |
| `/unique-tournament/{id}/season/{id}/info` | Saison-Metadaten |

---

## 3. Datenstrukturen

### Event-Objekt
```json
{
  "id": 15834256,
  "slug": "spv-seinajoki-westend-indians",
  "homeTeam": { "id": 6584, "name": "SPV Seinäjoki", "country": { "alpha2": "fi", "name": "Finland" } },
  "awayTeam": { "id": 65930, "name": "Westend Indians" },
  "homeScore": { "current": 4, "period1": 2, "period2": 1, "period3": 1 },
  "awayScore": { "current": 5 },
  "status": { "type": "finished", "code": 100 },
  "roundInfo": { "round": 27, "name": "Quarterfinals", "slug": "quarterfinals" },
  "startTimestamp": 1774792800,
  "tournament": { "name": "Champions Cup, Playoffs", "uniqueTournament": { "id": 961 } }
}
```

**Verfügbar:** Heim/Auswärts-Teams mit Land, Perioden-Scores, Status, Rundeninfo, Zeitstempel  
**Nicht verfügbar:** Torschützen, Spielminuten, Spielerstatistiken

### Incident-Objekt (Tore)
```json
{
  "incidentType": "goal",
  "incidentClass": "regular",
  "time": -1,           // ← immer -1! Keine Spielminute verfügbar
  "homeScore": 1,
  "awayScore": 0,
  "id": 342732179
  // kein "player"-Feld, kein "scorer"
}
```
**Einschränkung:** `time: -1` (keine Spielminute), **keine Torschützen**, nur Scoreline-Verlauf

### Tabellen-Zeile
```json
{
  "position": 1,
  "team": { "id": 4144, "name": "Salibandy Club Classic", "shortName": "SC Classic" },
  "matches": 32,
  "wins": 27,
  "losses": 5,
  "draws": 0,
  "scoresFor": 261,
  "scoresAgainst": 116,
  "scoreDiffFormatted": "+145",
  "points": 81,
  "promotion": "Playoffs"
}
```

### Rounds-Objekt
```json
{
  "currentRound": { "round": 29, "name": "Final" },
  "rounds": [
    { "round": 1 },
    { "round": 27, "name": "Quarterfinals", "slug": "quarterfinals" },
    { "round": 28, "name": "Semifinals", "slug": "semifinals" },
    { "round": 29, "name": "Final", "slug": "final" },
    { "round": 50, "name": "Match for 3rd place", "slug": "match-for-3rd-place" }
  ]
}
```

### CupTree-Objekt (vereinfacht)
```json
{
  "rounds": [
    {
      "round": 27,
      "name": "Quarterfinals",
      "series": [
        {
          "home": { "name": "Storvreta IBK" },
          "away": { "name": "Nykvarns IBF Ungdom" },
          "homeWins": 4,
          "awayWins": 0,
          "winner": "home"
        }
      ]
    }
  ]
}
```

---

## 4. Liga-Konfiguration (verifiziert)

| Liga | tournament-ID | season-ID | Gruppen | CupTree | Rounds |
|---|---|---|---|---|---|
| WM Männer | 617 | 64366 | Mehrere (A,B,C,D + K.O.) | ✅ | ✅ |
| WM Frauen | 762 | 85669 | Mehrere | ✅ | ✅ |
| Champions Cup | 961 | 80598 | 1 (nur Playoffs) | ✅ | ✅ (ab QF) |
| Svenska Superligan | 255 | 78217 | 1 | ✅ | ✅ |
| SSL Frauen | 1428 | 78233 | 1 | ✅ | ✅ |
| F-Liiga | 306 | 77638 | 1 | ✅ | ✅ (round/1 bestätigt) |
| F-Liiga Frauen | 20021 | 76917 | 1 | ? | ? |
| Unihockey Prime League | 313 | 78896 | 2 (Ost/West) | ✅ | ✅ |
| UPL Frauen | 19990 | 78897 | ? | ? | ? |
| Extraliga (CZ) | 829 | 76918 | 1 | ✅ | ✅ |
| Eliteserien (NO) | 318 | 78716 | ? | ? | ? |
| Floorball League (DK) | 1436 | 80599 | ? | ? | ? |

---

## 5. Nationale Teams (getestete IDs)

| Team | ID | `events/last/0` |
|---|---|---|
| Deutschland | 7559 | ✅ historische Spiele |
| Schweden | 25912 | ✅ |
| Finnland | 25906 | ✅ |
| Finnland Frauen | 7558 | ✅ |

Endpoint `/team/{id}/events/next/0` → 404 wenn keine Spiele geplant (z.B. DE nach WM)

---

## 6. Was ist realistisch umsetzbar?

| Feature | Machbar? | Begründung |
|---|---|---|
| **Spielplan (Runde für Runde)** | ✅ **JA** | `/events/round/{n}` funktioniert |
| **Tabelle** | ✅ **JA** | `/standings/total` mit Multi-Gruppen-Support |
| **Playoff-Baum (CupTree)** | ✅ **JA** | `/cuptrees` mit Serien-Scores |
| **Match-Detail (Tor-Verlauf)** | ⚠️ **EINGESCHRÄNKT** | Nur Scoreline 1:0, 2:0 etc., keine Spieler, keine Minuten |
| **Scorer-Liste** | ❌ **NEIN** | 404 – nicht verfügbar für Floorball |
| **Aufstellungen / Lineups** | ❌ **NEIN** | 404 |
| **Team-Kader** | ❌ **NEIN** | `/team/{id}/players` → 404 |
| **Spieler-Statistiken** | ❌ **NEIN** | 404 |
| **Länderspiele (Ergebnisse)** | ✅ **JA** | `events/last/0` für National-Teams |

---

## 7. Empfohlene Architektur

Basierend auf den Discovery-Ergebnissen empfehle ich diese Tab-Struktur:

```
International-Tab
├── [Verband-Dropdown]  →  International | Schweden | Finnland | Schweiz | Tschechien | ...
├── [Liga-Dropdown]     →  je nach Verband die verfügbaren Ligen
│
└── Sub-Navigation (analog Deutschland-Tab)
    ├── Übersicht   →  Nächste 5 + Letzte 5 Spiele der gewählten Liga
    ├── Spielplan   →  Runden-Selector (< Runde 1 ▸) + Spiele der Runde
    ├── Tabelle     →  Standings-Tabelle (Multi-Gruppe falls WM)
    └── Playoff     →  CupTree-Visualisierung (nur wenn cuptrees vorhanden)

Länderspiele (eigener Button / Verband = "International")
    →  Letzte 20 Spiele der Nationalmannschaften gefiltert nach Team
```

**Was ENTFÄLLT** gegenüber ursprünglichem Plan:
- Scorer-Tab (API nicht verfügbar)
- Team-Detail mit Kader (API nicht verfügbar)
- Spieler-Profile (API nicht verfügbar)
- Match-Detail mit Torschützen (Daten nicht vorhanden)

---

## 8. Nächste Schritte (nach User-Freigabe)

1. **Verband/Liga-Navigation** als Dropdowns (wie Deutschland-Tab)
2. **Übersicht-Sub-Tab**: letzte 5 + nächste 5 Spiele via `events/last/0` + `events/next/0`
3. **Spielplan-Sub-Tab**: Runden-Selector mit `rounds` + `events/round/{n}` pro Runde
4. **Tabelle-Sub-Tab**: Standings mit Multi-Gruppen (WM: A/B/C/D + Playoffs)
5. **Playoff-Sub-Tab**: CupTree-Visualisierung (bracket-style)
6. **Länderspiele**: separater Bereich bei Verband = "International"
