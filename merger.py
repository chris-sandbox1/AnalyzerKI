"""
merger.py – Führt mehrere Teil-Analysen zu einer Gesamt-JSON zusammen.

Offset-Regel:
    Gemini sieht jeden Sequenz-Clip ab 00:00.
    Der Zeitversatz einer Sequenz in der Gesamt-Timeline =
    summierte Dauer aller Vorgänger-Sequenzen (NICHT die Startzeit im Originalvideo).

    Beispiel: Seq 1 = 24 Min, Seq 2 = 25 Min → Offset für Seq 3 = 49 Min.
    Pausen zwischen den Sequenzen im Originalvideo werden so herausgerechnet.
"""

from stats_engine import berechne_stats, zusammenfuehren_zweikampf_stats


def parse_zeit(ts: str) -> int:
    """Wandelt MM:SS oder HH:MM:SS in Sekunden um. Gibt 0 bei ungültigem Format."""
    teile = ts.strip().split(":")
    try:
        if len(teile) == 2:
            return int(teile[0]) * 60 + int(teile[1])
        if len(teile) == 3:
            return int(teile[0]) * 3600 + int(teile[1]) * 60 + int(teile[2])
    except (ValueError, IndexError):
        pass
    return 0


def format_zeit(sek: int) -> str:
    """Wandelt Sekunden in MM:SS um."""
    sek = max(0, int(sek))
    return f"{sek // 60:02d}:{sek % 60:02d}"


def _addiere_offset(ts: str, offset_sek: int) -> str:
    """Addiert einen Offset (Sekunden) zu einem Timestamp-String."""
    return format_zeit(parse_zeit(ts) + offset_sek)


def merge_ergebnisse(teilergebnisse: list, sequenzen: list) -> dict:
    """
    Führt Teil-Analyse-JSONs zu einem Gesamt-JSON zusammen.

    teilergebnisse : Liste geparster JSON-Dicts (je eine Sequenz, direkt von Gemini)
    sequenzen      : Liste der Sequenz-Definitionen:
                     [{"start": "MM:SS", "end": "MM:SS", "label": "Drittel 1"}, ...]

    Offset-Berechnung:
        offset[i] = Summe der Dauern aller vorherigen Sequenzen
        dauer[j]  = parse_zeit(end) - parse_zeit(start)
    """
    stat_keys = [
        "tore_team_a", "tore_team_b",
        "torschuesse_team_a", "torschuesse_team_b",
        "konter_gesamt", "chancen_gesamt",
        "penalties_team_a", "penalties_team_b",
        "zweikampf_gesamt_a", "zweikampf_gesamt_b",
    ]
    dict_stat_keys = [
        "zweikampf_zonen_a", "zweikampf_zonen_b",
        "konter_zonen_a", "konter_zonen_b",
    ]

    gesamt_ereignisse = []
    gesamt_zusammenfassung = []
    gesamt_statistik = {k: 0 for k in stat_keys}
    for k in dict_stat_keys:
        gesamt_statistik[k] = {}
    teile_stats = []

    kum_dauer_sek = 0  # Kumulierte Dauer aller bisherigen Sequenzen

    for i, (ergebnis, seq) in enumerate(zip(teilergebnisse, sequenzen)):
        offset_sek = kum_dauer_sek
        label = seq.get("label") or f"Teil {i + 1}"

        # Zusammenfassung sammeln
        zf = ergebnis.get("zusammenfassung", "")
        if zf:
            gesamt_zusammenfassung.append(f"[{label}] {zf}")

        # Events mit Offset versehen und Label anhängen
        for ev in ergebnis.get("ereignisse", []):
            neu = dict(ev)
            if "timestamp" in neu:
                neu["timestamp"] = _addiere_offset(neu["timestamp"], offset_sek)
            neu["sequenz"] = label
            gesamt_ereignisse.append(neu)

        # Integer-Statistiken addieren
        stat = ergebnis.get("statistik", {})
        for k in stat_keys:
            gesamt_statistik[k] += int(stat.get(k, 0))

        # Dict-Statistiken (Zonen-Verteilungen) zusammenführen
        for k in dict_stat_keys:
            teildict = stat.get(k, {})
            if isinstance(teildict, dict):
                for zone, count in teildict.items():
                    gesamt_statistik[k][zone] = gesamt_statistik[k].get(zone, 0) + count

        teile_stats.append(stat)

        # Dauer dieser Sequenz akkumulieren → wird Offset für nächste Sequenz
        start_sek = parse_zeit(seq.get("start", "00:00"))
        end_sek   = parse_zeit(seq.get("end",   "00:00"))
        kum_dauer_sek += max(0, end_sek - start_sek)

    # Zweikampf-Quoten über alle Teile korrekt zusammenführen
    zk = zusammenfuehren_zweikampf_stats(teile_stats)
    gesamt_statistik["zweikampf_quote_a"] = zk["zweikampf_quote_a"]
    gesamt_statistik["zweikampf_quote_b"] = zk["zweikampf_quote_b"]

    gesamt_obj = {
        "zusammenfassung": " | ".join(gesamt_zusammenfassung),
        "ereignisse": gesamt_ereignisse,
        "statistik": gesamt_statistik,
    }
    # stats_engine für vollständige abgeleitete Statistiken aufrufen
    return berechne_stats(gesamt_obj)
