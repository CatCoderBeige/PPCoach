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
            "Accuracy drops on harder maps",
            f"Your accuracy falls by about {drop:.1f}% as star rating increases. "
            "This points to a reading or reaction problem on harder maps. "
            "Recommendation: deliberately practice maps 0.3-0.5 stars above your current "
            "comfort zone instead of making big jumps in star rating.",
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
            "Untapped PP potential from mods",
            f"The mods {mods_text} barely show up in your top scores. Since osu!'s PP "
            "formula rewards these mods with multipliers, you can gain PP comparatively "
            f"easily by farming known maps with {mods_text}.",
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
            "Narrow star-rating window",
            f"Almost all your top scores sit near {avg:.1f} stars (range only "
            f"{spread:.1f}). You're likely stuck in a narrow difficulty band. "
            "Recommendation: deliberately try individual maps 0.5-1.0 stars higher to "
            "unlock new PP potential instead of only grinding your usual range.",
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
            "Consistency issue despite high PP",
            f"{low_rank_count} of {len(scores)} top scores are only B rank or worse. "
            "This points more to consistency problems (miss control, focus over the full "
            "map) than to a pure skill ceiling. Recommendation: replay known maps and aim "
            "for FC/SS instead of chasing new PP records.",
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
            "Misses pile up on higher star ratings",
            "Your miss count rises disproportionately on harder maps. That suggests a "
            "reading/stamina problem on unfamiliar patterns rather than a pure aim "
            "weakness. Recommendation: slower, controlled practice of new patterns before "
            "focusing on speed.",
        )
    if low_sr_misses >= 3 and high_sr_misses <= low_sr_misses:
        return Finding(
            "Misses even on easier maps",
            "You have noticeably many misses even on maps in the lower star range of your "
            "top scores. This points more to focus/consistency problems than a missing "
            "skill ceiling. Recommendation: focus on clean runs instead of speed.",
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
            "Playtime out of proportion to PP progress",
            f"At about {hours:.0f} hours played and {pp:.0f}pp, your PP gain per hour is "
            "comparatively low. That suggests practicing smarter rather than longer: train "
            "specific weak areas (see the other tips above) in a focused way instead of "
            "grinding broadly.",
        )
    return None


PP_BRACKETS = [
    (0, 500, "Focus on 2-3 star maps with high accuracy (>97%). Build a solid foundation "
             "in timing and basic aim first, before pushing star rating higher."),
    (500, 2000, "Deliberately expand to 3-4 star maps and try HD on maps you already know "
                "for extra PP from the mod multiplier."),
    (2000, 5000, "Use DT/HR on maps you already play well nomod to raise PP efficiently. "
                 "Target: a 4-5.5 star core range."),
    (5000, 10000, "Focus on consistency in your current star range (S/SS instead of new "
                  "PP records) plus deliberately shoring up individual weaknesses."),
    (10000, float("inf"), "In this bracket fine-tuning matters: targeted maps for known "
                          "weaknesses (see the tips above) and mod combinations for maximum "
                          "PP efficiency per score."),
]


def rule_farming_strategy(stats: dict) -> Finding:
    pp = stats.get("statistics", {}).get("pp") or 0
    for low, high, advice in PP_BRACKETS:
        if low <= pp < high:
            return Finding(
                f"Next steps for your current PP level (~{pp:.0f}pp)",
                advice,
            )
    return Finding("Next steps", PP_BRACKETS[-1][2])


def generate_report(stats: dict, scores: list[dict]) -> list[Finding]:
    """Runs all rules and returns the applicable findings."""
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
