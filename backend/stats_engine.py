"""
stats_engine.py – Nachberechnung aller Statistiken nach der Gemini-Analyse.

Wird von main.py nach jeder Analyse aufgerufen. Wandelt Zonen-Namen in
x/y-Koordinaten um, berechnet xGoals, Zweikampf-Statistiken und
Spieler-spezifische Zweikampfdaten.
"""

# ── Zonen → Koordinaten (Spielfeld 40m × 20m) ────────────────────────────────
# x=0 linkes Tor, x=40 rechtes Tor, y=0 unten, y=20 oben
# Alle Koordinaten aus Team-A-Perspektive (Team A greift nach rechts)

ZONE_COORDS = {
    # Schuss-Zonen mit Oben/Mitte/Unten-Suffix
    'EIGN_TOR_MITTE':      ( 1.0, 10.0),
    'EIGN_TOR_OBEN':       ( 1.0,  4.0),
    'EIGN_TOR_UNTEN':      ( 1.0, 16.0),
    'EIGN_TORRAUM_MITTE':  ( 4.0, 10.0),
    'EIGN_TORRAUM_OBEN':   ( 4.0,  5.0),
    'EIGN_TORRAUM_UNTEN':  ( 4.0, 15.0),
    'EIGN_SLOT_MITTE':     ( 9.0, 10.0),
    'EIGN_SLOT_OBEN':      ( 9.0,  4.5),
    'EIGN_SLOT_UNTEN':     ( 9.0, 15.5),
    'EIGN_HALB_MITTE':     (15.0, 10.0),
    'EIGN_HALB_OBEN':      (15.0,  4.0),
    'EIGN_HALB_UNTEN':     (15.0, 16.0),
    'RUECKRAUM_MITTE':     (20.0, 10.0),
    'RUECKRAUM_OBEN':      (20.0,  4.0),
    'RUECKRAUM_UNTEN':     (20.0, 16.0),
    'GEGN_HALB_MITTE':     (25.0, 10.0),
    'GEGN_HALB_OBEN':      (25.0,  4.0),
    'GEGN_HALB_UNTEN':     (25.0, 16.0),
    'GEGN_SLOT_MITTE':     (31.0, 10.0),
    'GEGN_SLOT_OBEN':      (31.0,  4.5),
    'GEGN_SLOT_UNTEN':     (31.0, 15.5),
    'GEGN_TORRAUM_MITTE':  (36.0, 10.0),
    'GEGN_TORRAUM_OBEN':   (36.0,  5.0),
    'GEGN_TORRAUM_UNTEN':  (36.0, 15.0),
    'GEGN_TOR_MITTE':      (39.5, 10.0),
    'GEGN_TOR_OBEN':       (39.5,  4.0),
    'GEGN_TOR_UNTEN':      (39.5, 16.0),
    'PENALTY':             (35.0, 10.0),
    # Zweikampf- und Konter-Zonen (nur Bereich, kein Suffix)
    'EIGN_TOR':            ( 1.5, 10.0),
    'EIGN_TORRAUM':        ( 5.0, 10.0),
    'EIGN_SLOT':           (10.0, 10.0),
    'EIGN_HALB':           (16.0, 10.0),
    'RUECKRAUM':           (20.0, 10.0),
    'GEGN_HALB':           (25.0, 10.0),
    'GEGN_SLOT':           (31.0, 10.0),
    'GEGN_TORRAUM':        (36.0, 10.0),
    'GEGN_TOR':            (39.0, 10.0),
}

# ── xGoal-Werte pro Zone ──────────────────────────────────────────────────────

XG_BY_ZONE = {
    'GEGN_TORRAUM_MITTE':  0.32,
    'GEGN_TORRAUM_OBEN':   0.14,
    'GEGN_TORRAUM_UNTEN':  0.14,
    'GEGN_SLOT_MITTE':     0.18,
    'GEGN_SLOT_OBEN':      0.09,
    'GEGN_SLOT_UNTEN':     0.09,
    'GEGN_HALB_MITTE':     0.08,
    'GEGN_HALB_OBEN':      0.05,
    'GEGN_HALB_UNTEN':     0.05,
    'RUECKRAUM_MITTE':     0.04,
    'RUECKRAUM_OBEN':      0.02,
    'RUECKRAUM_UNTEN':     0.02,
    'GEGN_TOR_MITTE':      0.02,
    'GEGN_TOR_OBEN':       0.01,
    'GEGN_TOR_UNTEN':      0.01,
    'PENALTY':             0.72,
    # Eigene Zonen (Kontersituationen o.ä.)
    'EIGN_SLOT_MITTE':     0.03,
    'EIGN_HALB_MITTE':     0.02,
    'EIGN_SLOT_OBEN':      0.01,
    'EIGN_SLOT_UNTEN':     0.01,
    # Default
    'DEFAULT':             0.05,
}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _ermittle_teams(ereignisse: list) -> tuple:
    """
    Ermittelt Team A und Team B aus den Ereignissen (Reihenfolge erstes Auftreten).
    Gibt (team_a, team_b) zurück. Einer kann leer sein wenn nur 1 Team vorkommt.
    """
    team_set = []
    for ev in ereignisse:
        t = (ev.get('team') or '').strip()
        if t and t != 'unbekannt' and t not in team_set:
            team_set.append(t)
    ta = team_set[0] if len(team_set) > 0 else ''
    tb = team_set[1] if len(team_set) > 1 else ''
    return ta, tb


def _koordinaten_aus_zone(zone: str) -> tuple:
    """Gibt (x, y) für eine Zone zurück, oder None wenn Zone unbekannt."""
    return ZONE_COORDS.get(zone)


def _dict_addieren(ziel: dict, quelle: dict):
    """Addiert Werte aus quelle zu ziel (beide string→int Dicts)."""
    for k, v in quelle.items():
        ziel[k] = ziel.get(k, 0) + v


# ── Hauptfunktion ─────────────────────────────────────────────────────────────

def berechne_stats(analyse_obj: dict) -> dict:
    """
    Erweitert ein Analyse-Dict (Gemini-Output) um berechnete Statistiken.

    - Fügt position.x/y aus Zone-Namen ein (für das Dashboard)
    - Berechnet Zweikampf-Quoten und Zonen-Verteilung
    - Berechnet Konter-Startpunkte
    - Aggregiert Spieler-spezifische Zweikampfdaten
    Gibt das erweiterte Dict zurück (Original wird nicht verändert).
    """
    import copy
    obj = copy.deepcopy(analyse_obj)

    ereignisse = obj.get('ereignisse', [])
    if not isinstance(ereignisse, list):
        return obj

    ta, tb = _ermittle_teams(ereignisse)

    # ── Koordinaten aus Zone berechnen ────────────────────────────────────────
    for ev in ereignisse:
        zone = ev.get('zone')
        if not zone:
            continue
        # Wenn noch kein position-Feld vorhanden (oder vom alten System übrig)
        if 'position' not in ev or ev['position'] is None:
            coords = _koordinaten_aus_zone(zone)
            if coords:
                ev['position'] = {'x': coords[0], 'y': coords[1]}

    # ── Zweikampf-Statistiken ─────────────────────────────────────────────────
    zk_gesamt_a = 0
    zk_gesamt_b = 0
    zk_gewonnen_a = 0
    zk_gewonnen_b = 0
    zk_zonen_a = {}
    zk_zonen_b = {}

    for ev in ereignisse:
        if ev.get('typ') != 'ZWEIKAMPF':
            continue
        team = ev.get('team', '')
        gewonnen = ev.get('gewonnen', False)
        zone = ev.get('zone', '')

        if team == ta:
            zk_gesamt_a += 1
            if gewonnen:
                zk_gewonnen_a += 1
            if zone:
                zk_zonen_a[zone] = zk_zonen_a.get(zone, 0) + 1
        elif team == tb:
            zk_gesamt_b += 1
            if gewonnen:
                zk_gewonnen_b += 1
            if zone:
                zk_zonen_b[zone] = zk_zonen_b.get(zone, 0) + 1

    zk_quote_a = round(zk_gewonnen_a / zk_gesamt_a * 100) if zk_gesamt_a > 0 else 0
    zk_quote_b = round(zk_gewonnen_b / zk_gesamt_b * 100) if zk_gesamt_b > 0 else 0

    # ── Konter-Zonen-Statistiken ──────────────────────────────────────────────
    konter_zonen_a = {}
    konter_zonen_b = {}

    for ev in ereignisse:
        if ev.get('typ') != 'KONTER':
            continue
        team = ev.get('team', '')
        zone = ev.get('zone', '')
        if not zone:
            continue
        if team == ta:
            konter_zonen_a[zone] = konter_zonen_a.get(zone, 0) + 1
        elif team == tb:
            konter_zonen_b[zone] = konter_zonen_b.get(zone, 0) + 1

    # ── Statistik-Felder erweitern ────────────────────────────────────────────
    if 'statistik' not in obj or not isinstance(obj['statistik'], dict):
        obj['statistik'] = {}

    obj['statistik'].update({
        'zweikampf_quote_a':  zk_quote_a,
        'zweikampf_quote_b':  zk_quote_b,
        'zweikampf_gesamt_a': zk_gesamt_a,
        'zweikampf_gesamt_b': zk_gesamt_b,
        'zweikampf_zonen_a':  zk_zonen_a,
        'zweikampf_zonen_b':  zk_zonen_b,
        'konter_zonen_a':     konter_zonen_a,
        'konter_zonen_b':     konter_zonen_b,
    })

    # ── Spieler-spezifische Zweikampfdaten ────────────────────────────────────
    spieler_stats = {}

    for ev in ereignisse:
        if ev.get('typ') != 'ZWEIKAMPF':
            continue
        zone = ev.get('zone', 'UNBEKANNT')
        team_gewinner = ev.get('team', '')
        team_verlierer = tb if team_gewinner == ta else ta

        # Gewinner-Spieler
        gewinner_key = ev.get('spieler_gewinner', '')
        if gewinner_key:
            if gewinner_key not in spieler_stats:
                spieler_stats[gewinner_key] = {
                    'team': team_gewinner,
                    'zweikampf_gewonnen': 0,
                    'zweikampf_verloren': 0,
                    'zweikampf_zonen': {},
                }
            spieler_stats[gewinner_key]['zweikampf_gewonnen'] += 1
            spieler_stats[gewinner_key]['zweikampf_zonen'][zone] = \
                spieler_stats[gewinner_key]['zweikampf_zonen'].get(zone, 0) + 1

        # Verlierer-Spieler
        verlierer_key = ev.get('spieler_verlierer', '')
        if verlierer_key:
            if verlierer_key not in spieler_stats:
                spieler_stats[verlierer_key] = {
                    'team': team_verlierer,
                    'zweikampf_gewonnen': 0,
                    'zweikampf_verloren': 0,
                    'zweikampf_zonen': {},
                }
            spieler_stats[verlierer_key]['zweikampf_verloren'] += 1
            spieler_stats[verlierer_key]['zweikampf_zonen'][zone] = \
                spieler_stats[verlierer_key]['zweikampf_zonen'].get(zone, 0) + 1

    # Gesamtquote pro Spieler berechnen
    for sp in spieler_stats.values():
        g = sp['zweikampf_gewonnen']
        v = sp['zweikampf_verloren']
        gesamt = g + v
        sp['zweikampf_gesamt'] = gesamt
        sp['zweikampf_quote'] = round(g / gesamt * 100) if gesamt > 0 else 0

    # Nur setzen wenn Daten vorhanden
    if spieler_stats:
        obj['spieler_zweikampf'] = spieler_stats

    return obj


def zusammenfuehren_zweikampf_stats(teile_stats: list) -> dict:
    """
    Führt Zweikampf-Statistiken aus mehreren Teil-Analysen zusammen.
    teile_stats: Liste von statistik-Dicts aus den Teilen.
    Gibt ein zusammengeführtes Dict zurück.
    """
    gesamt = {
        'zweikampf_gesamt_a': 0,
        'zweikampf_gesamt_b': 0,
        'zweikampf_quote_a': 0,
        'zweikampf_quote_b': 0,
        'zweikampf_zonen_a': {},
        'zweikampf_zonen_b': {},
        'konter_zonen_a': {},
        'konter_zonen_b': {},
    }
    zk_gewonnen_a = 0
    zk_gewonnen_b = 0

    for s in teile_stats:
        gesamt['zweikampf_gesamt_a'] += s.get('zweikampf_gesamt_a', 0)
        gesamt['zweikampf_gesamt_b'] += s.get('zweikampf_gesamt_b', 0)
        # Gewonnene aus Quote rückrechnen
        ga = s.get('zweikampf_gesamt_a', 0)
        qa = s.get('zweikampf_quote_a', 0)
        zk_gewonnen_a += round(ga * qa / 100) if ga > 0 else 0
        gb = s.get('zweikampf_gesamt_b', 0)
        qb = s.get('zweikampf_quote_b', 0)
        zk_gewonnen_b += round(gb * qb / 100) if gb > 0 else 0
        _dict_addieren(gesamt['zweikampf_zonen_a'], s.get('zweikampf_zonen_a', {}))
        _dict_addieren(gesamt['zweikampf_zonen_b'], s.get('zweikampf_zonen_b', {}))
        _dict_addieren(gesamt['konter_zonen_a'], s.get('konter_zonen_a', {}))
        _dict_addieren(gesamt['konter_zonen_b'], s.get('konter_zonen_b', {}))

    ga_total = gesamt['zweikampf_gesamt_a']
    gb_total = gesamt['zweikampf_gesamt_b']
    gesamt['zweikampf_quote_a'] = round(zk_gewonnen_a / ga_total * 100) if ga_total > 0 else 0
    gesamt['zweikampf_quote_b'] = round(zk_gewonnen_b / gb_total * 100) if gb_total > 0 else 0

    return gesamt
