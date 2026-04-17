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
import threading
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

# Projektverzeichnis (eine Ebene über tools/)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

API_BASE   = 'https://saisonmanager.de/api/v2'
TIMEOUT    = 15   # Sekunden bis ein einzelner Request aufgibt
MAX_WORKER = 8    # Gleichzeitige Verbindungen
REQ_PRO_SEK = 6  # Globales Request-Limit (verhindert Rate-Limiting)

# ── Globaler Rate-Limiter ─────────────────────────────────────────────────────
_rate_lock      = threading.Lock()
_letzter_request = 0.0

def rate_wait():
    """Stellt sicher dass nie mehr als REQ_PRO_SEK Requests pro Sekunde gesendet werden."""
    global _letzter_request
    min_abstand = 1.0 / REQ_PRO_SEK
    with _rate_lock:
        jetzt = time.time()
        warten = min_abstand - (jetzt - _letzter_request)
        if warten > 0:
            time.sleep(warten)
        _letzter_request = time.time()


def fetch_json(url, versuche=4):
    """Lädt eine URL mit bis zu `versuche` Wiederholungen bei Fehlern."""
    for i in range(versuche):
        rate_wait()
        try:
            with urlopen(url, timeout=TIMEOUT) as resp:
                data = resp.read()
                return json.loads(data.decode('utf-8'))
        except HTTPError:
            return None   # 404 etc. → Liga hat keine Daten, kein Retry nötig
        except Exception:
            if i < versuche - 1:
                time.sleep(2.0 * (i + 1))  # 2s, 4s, 6s Pause bei echten Fehlern
    return None


def lade_liga(liga):
    """Lädt scorer.json + table.json für eine Liga (wird parallel aufgerufen)."""
    liga_id = liga['id']
    scorer  = fetch_json(f'{API_BASE}/leagues/{liga_id}/scorer.json')
    tabelle = fetch_json(f'{API_BASE}/leagues/{liga_id}/table.json')
    return liga, scorer, tabelle


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
    print(f"  Lade Daten mit {MAX_WORKER} parallelen Verbindungen…\n")

    # ── 2. Alle Ligen parallel laden ──────────────────────────────────────────
    ergebnisse  = []   # (liga, scorer, tabelle)
    fehler_ligen = []
    fertig = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKER) as pool:
        futures = {pool.submit(lade_liga, liga): liga for liga in ligen}
        for future in as_completed(futures):
            fertig += 1
            liga, scorer, tabelle = future.result()
            liga_name = liga.get('name', f"Liga {liga['id']}")
            game_op   = liga.get('game_operation', '—')

            if scorer is None and tabelle is None:
                fehler_ligen.append(f"{liga_name} (ID {liga['id']})")
                status = 'FEHLER'
            else:
                ergebnisse.append((liga, scorer, tabelle))
                status = f"{len(scorer or []):>3} Scorer, {len(tabelle or []):>3} Teams"

            print(f"  [{fertig:>3}/{len(ligen)}] {liga_name:<38} [{game_op[:20]:<20}]  {status}",
                  flush=True)

    # ── 3. Aggregieren ────────────────────────────────────────────────────────
    print("\nAggregiere…", flush=True)
    spieler_map      = {}
    team_map         = {}
    team_player_map  = {}   # (team_name, player_id) → per-Team-Stats

    for liga, scorer, tabelle in ergebnisse:
        liga_name  = liga.get('name', '')
        game_op    = liga.get('game_operation', '')
        geschlecht = 'damen' if ist_damen(liga_name) else 'herren'

        # ── Spieler ───────────────────────────────────────────────────────────
        for s in (scorer or []):
            pid = s.get('player_id')
            if not pid:
                continue
            if pid not in spieler_map:
                spieler_map[pid] = {
                    'player_id':    pid,
                    'first_name':   s.get('first_name', ''),
                    'last_name':    s.get('last_name',  ''),
                    'teams':        set(),
                    'verbaende':    set(),
                    'spiele':       0,
                    'tore':         0,
                    'assists':      0,
                    'strafminuten': 0,
                    'p2':     0,
                    'p2and2': 0,
                    'p5':     0,
                    'p10':    0,
                    'ms':     0,
                    'geschlecht':   geschlecht,
                }
            sp = spieler_map[pid]
            sp['first_name'] = s.get('first_name') or sp['first_name']
            sp['last_name']  = s.get('last_name')  or sp['last_name']
            sp['spiele']       += s.get('games')         or 0
            sp['tore']         += s.get('goals')         or 0
            sp['assists']      += s.get('assists')        or 0
            sp['strafminuten'] += pim(s)
            sp['p2']           += s.get('penalty_2')     or 0
            sp['p2and2']       += s.get('penalty_2and2') or 0
            sp['p5']           += s.get('penalty_5')     or 0
            sp['p10']          += s.get('penalty_10')    or 0
            # Alle Matchstraf-Typen in einer Zahl zusammenfassen
            ms_val = (
                (s.get('penalty_match')   or 0) +
                (s.get('penalty_ms_tech') or 0) +
                (s.get('penalty_ms_full') or 0) +
                (s.get('penalty_ms1')     or 0) +
                (s.get('penalty_ms2')     or 0)
            )
            sp['ms'] += ms_val
            if s.get('team_name'):
                sp['teams'].add(s['team_name'])
            if game_op:
                sp['verbaende'].add(game_op)
            if sp['geschlecht'] != geschlecht:
                sp['geschlecht'] = 'gemischt'

            # ── Team-Kader: Stats pro Spieler+Team ───────────────────────────
            team_name_raw = (s.get('team_name') or '').strip()
            if team_name_raw:
                tp_key = (team_name_raw, pid)
                if tp_key not in team_player_map:
                    team_player_map[tp_key] = {
                        'player_id':    pid,
                        'first_name':   s.get('first_name', ''),
                        'last_name':    s.get('last_name',  ''),
                        'team_name':    team_name_raw,
                        'verbaende':    set(),
                        'spiele':       0,
                        'tore':         0,
                        'assists':      0,
                        'strafminuten': 0,
                        'p2':     0,
                        'p2and2': 0,
                        'p5':     0,
                        'p10':    0,
                        'ms':     0,
                        'geschlecht':   geschlecht,
                    }
                tp = team_player_map[tp_key]
                tp['first_name'] = s.get('first_name') or tp['first_name']
                tp['last_name']  = s.get('last_name')  or tp['last_name']
                tp['spiele']       += s.get('games')         or 0
                tp['tore']         += s.get('goals')         or 0
                tp['assists']      += s.get('assists')        or 0
                tp['strafminuten'] += pim(s)
                tp['p2']           += s.get('penalty_2')     or 0
                tp['p2and2']       += s.get('penalty_2and2') or 0
                tp['p5']           += s.get('penalty_5')     or 0
                tp['p10']          += s.get('penalty_10')    or 0
                tp['ms']           += ms_val
                if game_op:
                    tp['verbaende'].add(game_op)

        # ── Teams ─────────────────────────────────────────────────────────────
        for t in (tabelle or []):
            tid = t.get('team_id')
            if not tid:
                continue
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
            tm['siege']     += (t.get('won') or 0) + (t.get('won_ot') or 0)
            tm['tore']      += t.get('goals_scored')   or 0
            tm['gegentore'] += t.get('goals_received') or 0
            tm['punkte']    += t.get('points')         or 0
            if tm['geschlecht'] != geschlecht:
                tm['geschlecht'] = 'gemischt'

    # ── 4. Finalisieren ───────────────────────────────────────────────────────
    scorer_liste = []
    for sp in spieler_map.values():
        sp['teams']    = sorted(sp['teams'])
        sp['verbaende']= sorted(sp['verbaende'])
        sp['punkte']   = sp['tore'] + sp['assists']
        scorer_liste.append(sp)
    scorer_liste.sort(key=lambda x: x['punkte'], reverse=True)

    team_liste = sorted(team_map.values(), key=lambda x: x['punkte'], reverse=True)

    # ── Team-Kader-Dict aufbauen ──────────────────────────────────────────────
    team_rosters = {}   # team_name → [spieler_liste sortiert nach punkte]
    for tp in team_player_map.values():
        tp['verbaende'] = sorted(tp['verbaende'])
        tp['punkte']    = tp['tore'] + tp['assists']
        tn = tp['team_name']
        if tn not in team_rosters:
            team_rosters[tn] = []
        team_rosters[tn].append(tp)
    for roster in team_rosters.values():
        roster.sort(key=lambda x: x['punkte'], reverse=True)

    # ── 5. Speichern ──────────────────────────────────────────────────────────
    os.makedirs(os.path.join(ROOT, 'data'), exist_ok=True)

    # Datei 1: alltime.json — nur scorer + teams, kein indent
    output_main = os.path.join(ROOT, 'data', 'alltime.json')
    with open(output_main, 'w', encoding='utf-8') as f:
        json.dump({
            'generiert':    str(date.today()),
            'ligen_gesamt': len(ligen),
            'scorer':       scorer_liste,
            'teams':        team_liste,
        }, f, ensure_ascii=False)

    # Datei 2: team_rosters.json — nur team_rosters, kein indent
    output_rosters = os.path.join(ROOT, 'data', 'team_rosters.json')
    with open(output_rosters, 'w', encoding='utf-8') as f:
        json.dump(team_rosters, f, ensure_ascii=False)

    # ── 6. Zusammenfassung ────────────────────────────────────────────────────
    print()
    print(f"{'─'*60}")
    print(f"  Fertig!")
    print(f"  {len(scorer_liste):>6} Spieler aggregiert")
    print(f"  {len(team_liste):>6} Teams aggregiert")
    print(f"  {len(team_rosters):>6} Team-Kader erstellt")
    print(f"  {len(ligen):>6} Ligen verarbeitet")
    if fehler_ligen:
        print(f"  {len(fehler_ligen):>6} Ligen fehlgeschlagen:")
        for fl in fehler_ligen:
            print(f"           – {fl}")
    print(f"  Gespeichert: {output_main}")
    print(f"  Gespeichert: {output_rosters}")
    print(f"{'─'*60}")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\nUNERWARTETER FEHLER: {e}")
        import traceback
        traceback.print_exc()
    input("\nDrücke Enter zum Beenden…")
