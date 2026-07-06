"""Regelbasierte Spielanalyse - ersetzt den fruehreren Live-Call an Claude.

Nimmt Profil-Stats + Top-Scores von der osu! API entgegen und leitet daraus,
rein ueber Schwellenwerte/Formeln, Schwaechen und Empfehlungen ab. Jede Regel
ist unabhaengig testbar und liefert 0..1 Findings.
"""

from dataclasses import dataclass


@dataclass
class Finding:
    title: str
    text: str
    category: str = "general"  # steuert Symbol + Farbe in der GUI (siehe theme.py)


def _mod_acronyms(score: dict) -> set[str]:
    mods = score.get("mods", [])
    acronyms = set()
    for mod in mods:
        if isinstance(mod, dict):
            acronyms.add(mod.get("acronym", ""))
        else:
            acronyms.add(str(mod))
    acronyms.discard("")
    return acronyms


def _star_rating(score: dict) -> float:
    return score.get("beatmap", {}).get("difficulty_rating", 0.0) or 0.0


def rule_accuracy_vs_star_rating(scores: list[dict]) -> Finding | None:
    rated = [(s, _star_rating(s)) for s in scores if _star_rating(s) > 0]
    if len(rated) < 4:
        return None

    rated.sort(key=lambda pair: pair[1])
    midpoint = len(rated) // 2
    easier = rated[:midpoint]
    harder = rated[midpoint:]

    avg_acc_easier = sum(s.get("accuracy", 0) for s, _ in easier) / len(easier)
    avg_acc_harder = sum(s.get("accuracy", 0) for s, _ in harder) / len(harder)

    drop = (avg_acc_easier - avg_acc_harder) * 100
    if drop >= 1.5:
        return Finding(
            "Genauigkeit sinkt bei schwierigeren Maps",
            f"Deine Accuracy faellt bei hoeherer Sternebewertung um ca. {drop:.1f}%. "
            "Das deutet auf ein Lese- oder Reaktionsproblem bei schwierigeren Maps hin. "
            "Empfehlung: gezielt Maps 0.3-0.5 Sterne ueber deinem aktuellen Komfortbereich "
            "ueben, statt direkt grosse Spruenge in der Sternebewertung zu machen.",
        )
    return None


def rule_mod_usage(scores: list[dict]) -> Finding | None:
    if not scores:
        return None

    mod_counts: dict[str, int] = {}
    for score in scores:
        for acronym in _mod_acronyms(score):
            mod_counts[acronym] = mod_counts.get(acronym, 0) + 1

    total = len(scores)
    underused = [
        mod for mod in ("HD", "HR", "DT")
        if mod_counts.get(mod, 0) / total < 0.2
    ]

    if underused:
        mods_text = ", ".join(underused)
        return Finding(
            "Ungenutztes PP-Potenzial durch Mods",
            f"In deinen Top-Scores tauchen die Mods {mods_text} kaum auf. Da osu!'s "
            "PP-Formel diese Mods durch Multiplikatoren belohnt, kannst du mit gezieltem "
            f"Farmen mit {mods_text} auf bekannten Maps vergleichsweise einfach PP gewinnen.",
        )
    return None


def rule_pp_star_rating_spread(scores: list[dict]) -> Finding | None:
    rated_srs = [_star_rating(s) for s in scores if _star_rating(s) > 0]
    if len(rated_srs) < 4:
        return None

    spread = max(rated_srs) - min(rated_srs)
    if spread < 0.8:
        avg = sum(rated_srs) / len(rated_srs)
        return Finding(
            "Enges Sternebewertungs-Fenster",
            f"Deine Top-Scores liegen fast alle nah bei {avg:.1f} Sternen (Spanne nur "
            f"{spread:.1f}). Du steckst wahrscheinlich in einem engen Schwierigkeitsband fest. "
            "Empfehlung: bewusst einzelne Maps 0.5-1.0 Sterne darueber ausprobieren, um neues "
            "PP-Potenzial zu erschliessen, statt nur im gewohnten Bereich zu grinden.",
        )
    return None


RANK_ORDER = ["D", "C", "B", "A", "S", "SH", "SS", "SSH"]
LOW_RANKS = {"D", "C", "B"}


def rule_rank_consistency(scores: list[dict]) -> Finding | None:
    if not scores:
        return None

    low_rank_count = sum(1 for s in scores if s.get("rank") in LOW_RANKS)
    ratio = low_rank_count / len(scores)

    if ratio >= 0.3:
        return Finding(
            "Konsistenzproblem trotz hoher PP",
            f"{low_rank_count} von {len(scores)} Top-Scores haben nur B-Rang oder schlechter. "
            "Das deutet eher auf Konsistenzprobleme (Miss-Kontrolle, Fokus ueber die volle "
            "Map-Laenge) als auf ein reines Skill-Limit hin. Empfehlung: bekannte Maps erneut "
            "spielen und gezielt auf FC/SS statt auf neue PP-Rekorde fokussieren.",
        )
    return None


def rule_miss_pattern(scores: list[dict]) -> Finding | None:
    misses_by_sr = [
        (_star_rating(s), s.get("statistics", {}).get("count_miss", 0))
        for s in scores
        if _star_rating(s) > 0
    ]
    if len(misses_by_sr) < 4:
        return None

    misses_by_sr.sort(key=lambda pair: pair[0])
    midpoint = len(misses_by_sr) // 2
    low_sr_misses = sum(m for _, m in misses_by_sr[:midpoint])
    high_sr_misses = sum(m for _, m in misses_by_sr[midpoint:])

    if high_sr_misses > low_sr_misses * 2 and high_sr_misses >= 3:
        return Finding(
            "Misses haeufen sich bei hoeherer Sternebewertung",
            "Deine Miss-Anzahl steigt bei schwierigeren Maps ueberproportional an. Das "
            "spricht eher fuer ein Reading-/Stamina-Problem auf ungewohnten Patterns als "
            "fuer reine Aim-Schwaeche. Empfehlung: langsameres, kontrolliertes Ueben neuer "
            "Patterns vor dem Tempo-Fokus.",
        )
    if low_sr_misses >= 3 and high_sr_misses <= low_sr_misses:
        return Finding(
            "Misses auch auf einfacheren Maps",
            "Du hast auffaellig viele Misses auch auf Maps im unteren Sternebereich deiner "
            "Top-Scores. Das deutet eher auf Konzentrations-/Konsistenzprobleme als auf "
            "fehlendes Skill-Ceiling hin. Empfehlung: Fokus auf saubere Runs statt Tempo.",
        )
    return None


HOURS_PER_SECOND = 1 / 3600


def rule_playtime_efficiency(stats: dict) -> Finding | None:
    statistics = stats.get("statistics", {})
    play_time = statistics.get("play_time") or 0
    pp = statistics.get("pp") or 0

    hours = play_time * HOURS_PER_SECOND
    if hours < 20:
        return None

    pp_per_hour = pp / hours
    if pp_per_hour < 5:
        return Finding(
            "Spielzeit steht nicht im Verhaeltnis zum PP-Fortschritt",
            f"Bei ca. {hours:.0f} Spielstunden und {pp:.0f}pp liegt dein PP-Ertrag pro "
            "Stunde vergleichsweise niedrig. Das spricht dafuer, gezielter statt laenger zu "
            "ueben: einzelne schwache Bereiche (siehe andere Hinweise oben) fokussiert "
            "trainieren statt breit zu grinden.",
        )
    return None


PP_BRACKETS = [
    (0, 500, "Fokussiere dich auf 2-3 Sterne Maps mit hoher Genauigkeit (>97%). "
             "Baue zuerst ein solides Fundament in Timing und Basic-Aim auf, bevor du "
             "die Sternebewertung steigerst."),
    (500, 2000, "Erweitere gezielt auf 3-4 Sterne Maps und probiere HD auf bereits "
                "bekannten Maps fuer zusaetzliche PP durch den Mod-Multiplikator."),
    (2000, 5000, "Nutze DT/HR auf Maps, die du bereits ohne Mod gut spielst, um PP "
                 "effizient zu steigern. Ziel: 4-5.5 Sterne Kernbereich."),
    (5000, 10000, "Fokus auf Konsistenz in deinem aktuellen Sternebereich (S/SS statt "
                  "neuer PP-Rekorde) plus gezieltes Ausbauen einzelner Schwaechen."),
    (10000, float("inf"), "In diesem Bracket zaehlt Feintuning: gezielte Maps mit "
                          "bekannten Schwaechen (siehe Hinweise oben) und Mod-Kombinationen "
                          "fuer maximale PP-Effizienz pro Score."),
]


def rule_farming_strategy(stats: dict) -> Finding:
    pp = stats.get("statistics", {}).get("pp") or 0
    for low, high, advice in PP_BRACKETS:
        if low <= pp < high:
            return Finding(
                f"Naechste Schritte fuer dein aktuelles PP-Level (~{pp:.0f}pp)",
                advice,
            )
    return Finding("Naechste Schritte", PP_BRACKETS[-1][2])


def generate_report(stats: dict, scores: list[dict]) -> list[Finding]:
    """Fuehrt alle Regeln aus und gibt die zutreffenden Findings zurueck."""
    findings: list[Finding] = []

    # Jede Regel bekommt eine Kategorie, die in der GUI Symbol + Akzentfarbe bestimmt.
    rules = (
        ("accuracy", lambda: rule_accuracy_vs_star_rating(scores)),
        ("mods", lambda: rule_mod_usage(scores)),
        ("spread", lambda: rule_pp_star_rating_spread(scores)),
        ("consistency", lambda: rule_rank_consistency(scores)),
        ("misses", lambda: rule_miss_pattern(scores)),
        ("playtime", lambda: rule_playtime_efficiency(stats)),
    )
    for category, rule in rules:
        result = rule()
        if result:
            result.category = category
            findings.append(result)

    strategy = rule_farming_strategy(stats)
    strategy.category = "strategy"
    findings.append(strategy)
    return findings
