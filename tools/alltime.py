"""
alltime.py — Einmalig alle Alltime-Statistiken über alle Verbände und Saisons berechnen.
Speichert das Ergebnis als alltime.json im Projektverzeichnis (eine Ebene über tools/).

Aufruf: python tools/alltime.py
"""

import json
import os
import re
import sys
import time
from datetime import date
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

# Projektverzeichnis (eine Ebene über tools/)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

API_BASE = 'https://saisonmanager.de/api/v2'
DELAY    = 0.15   # Sekunden zwischen Requests (0.15s × 2 pro Liga = 0.3s gesamt)
TIMEOUT  = 15     # Sekunden bis Request aufgibt


def fetch_json(url):
    """Lädt eine URL und gibt geparste JSON-Daten zurück, oder None bei Fehler."""
    try:
        with urlopen(url, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        return None   # 404 etc. → Liga hat keine Daten, kein Problem
    except (URLError, Exception):
        return None


def pim(s):
    """Strafminuten berechnen: 2er, 2+2er, 5er, 10er Strafen."""
    return (
        (s.get('penalty_2')     or 0) * 2 +
        (s.get('penalty_2and2') or 0) * 4 +
        (s.get('penalty_5')     or 0) * 5 +
        (s.get('penalty_10')    or 0) * 10
    )


def ist_damen(name):
    """Erkennt Damen-Ligen anhand des Namens."""
    return bool(re.search(r'damen|frauen', name, re.IGNORECASE))


def main():
    # ── 1. Ligen laden ────────────────────────────────────────────────────────
    print("Lade leagues.json…", flush=True)
    alle_ligen = fetch_json(f'{API_BASE}/leagues.json')
    if not alle_ligen:
        print("FEHLER: leagues.json konnte nicht geladen werden.")
        sys.exit(1)

    # Deduplizieren: dieselbe Liga-ID kann mehrfach im JSON auftauchen
    gesehen = set()
    ligen = []
    for liga in alle_ligen:
        lid = liga.get('id')
        if lid and lid not in gesehen:
            gesehen.add(lid)
            ligen.append(liga)

    duplikate = len(alle_ligen) - len(ligen)
    print(f"  {len(alle_ligen)} Einträge geladen → {len(ligen)} eindeutige Ligen"
          + (f" ({duplikate} Duplikate entfernt)" if duplikate else ""))
    print()

    # ── 2. Pro Liga: scorer.json + table.json laden und aggregieren ───────────
    spieler_map = {}   # player_id → dict
    team_map    = {}   # team_id   → dict
    fehler_ligen = []

    for i, liga in enumerate(ligen, 1):
        liga_id    = liga['id']
        liga_name  = liga.get('name', f'Liga {liga_id}')
        game_op    = liga.get('game_operation', '—')
        geschlecht = 'damen' if ist_damen(liga_name) else 'herren'

        print(f"  Liga {i:>4}/{len(ligen)}: {liga_name:<40} [{game_op}]", end='', flush=True)

        # Scorer laden
        scorer  = fetch_json(f'{API_BASE}/leagues/{liga_id}/scorer.json')
        time.sleep(DELAY)

        # Tabelle laden
        tabelle = fetch_json(f'{API_BASE}/leagues/{liga_id}/table.json')
        time.sleep(DELAY)

        if scorer is None and tabelle is None:
            print(f'  → FEHLER')
            fehler_ligen.append(f'{liga_name} (ID {liga_id})')
            continue

        n_scorer  = len(scorer  or [])
        n_tabelle = len(tabelle or [])
        print(f'  → {n_scorer} Scorer, {n_tabelle} Teams')

        # ── Spieler aggregieren ───────────────────────────────────────────────
        for s in (scorer or []):
            pid = s.get('player_id')
            if not pid:
                continue   # Eintrag ohne player_id überspringen

            if pid not in spieler_map:
                spieler_map[pid] = {
                    'player_id':    pid,
                    'first_name':   s.get('first_name', ''),
                    'last_name':    s.get('last_name',  ''),
                    'teams':        set(),
                    'spiele':       0,
                    'tore':         0,
                    'assists':      0,
                    'strafminuten': 0,
                    'geschlecht':   geschlecht,
                }

            sp = spieler_map[pid]
            # Neuesten Namen übernehmen
            sp['first_name'] = s.get('first_name') or sp['first_name']
            sp['last_name']  = s.get('last_name')  or sp['last_name']
            sp['spiele']       += s.get('games')   or 0
            sp['tore']         += s.get('goals')   or 0
            sp['assists']      += s.get('assists')  or 0
            sp['strafminuten'] += pim(s)
            if s.get('team_name'):
                sp['teams'].add(s['team_name'])
            # Wenn Spieler in Damen- UND Herren-Liga → gemischt
            if sp['geschlecht'] != geschlecht:
                sp['geschlecht'] = 'gemischt'

        # ── Teams aggregieren ─────────────────────────────────────────────────
        for t in (tabelle or []):
            tid = t.get('team_id')
            if not tid:
                continue   # Eintrag ohne team_id überspringen

            if tid not in team_map:
                team_map[tid] = {
                    'team_id':    tid,
                    'team_name':  t.get('team_name', ''),
                    'saisons':    0,
                    'spiele':     0,
                    'siege':      0,
                    'tore':       0,
                    'gegentore':  0,
                    'punkte':     0,
                    'geschlecht': geschlecht,
                }

            tm = team_map[tid]
            tm['saisons']   += 1
            tm['spiele']    += t.get('games')          or 0
            tm['siege']     += (t.get('won')   or 0) + (t.get('won_ot') or 0)
            tm['tore']      += t.get('goals_scored')   or 0
            tm['gegentore'] += t.get('goals_received') or 0
            tm['punkte']    += t.get('points')         or 0
            if tm['geschlecht'] != geschlecht:
                tm['geschlecht'] = 'gemischt'

    # ── 3. Finalisieren: Sets → Listen, Punkte berechnen, sortieren ───────────
    scorer_liste = []
    for sp in spieler_map.values():
        sp['teams']  = sorted(sp['teams'])
        sp['punkte'] = sp['tore'] + sp['assists']
        scorer_liste.append(sp)
    scorer_liste.sort(key=lambda x: x['punkte'], reverse=True)

    team_liste = sorted(team_map.values(), key=lambda x: x['punkte'], reverse=True)

    # ── 4. alltime.json speichern ─────────────────────────────────────────────
    ergebnis = {
        'generiert':    str(date.today()),
        'ligen_gesamt': len(ligen),
        'scorer':       scorer_liste,
        'teams':        team_liste,
    }

    output = os.path.join(ROOT, 'alltime.json')
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(ergebnis, f, ensure_ascii=False, indent=2)

    # ── 5. Zusammenfassung ────────────────────────────────────────────────────
    print()
    print(f"{'─'*60}")
    print(f"  Fertig!")
    print(f"  {len(scorer_liste):>6} Spieler aggregiert")
    print(f"  {len(team_liste):>6} Teams aggregiert")
    print(f"  {len(ligen):>6} Ligen verarbeitet")
    if fehler_ligen:
        print(f"  {len(fehler_ligen):>6} Ligen fehlgeschlagen:")
        for fl in fehler_ligen:
            print(f"           – {fl}")
    print(f"  Gespeichert: {output}")
    print(f"{'─'*60}")


if __name__ == '__main__':
    main()
