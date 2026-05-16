# ml/data/category_mapping.py
"""
Single source of truth for crime_type → crime_macro mapping.

Both ingest.py (snapshot pipeline) and train_kde.py (model training) import
from here. Any change to categories or patterns is made once and flows through
the entire pipeline automatically.

Priority order = female-safety weight descending. First regex match wins.
This means for compound crime types (e.g. "Murder / Robbery"), the higher-
weight category (Robbery, 2.0) takes precedence over Murder (1.5).
"""

from __future__ import annotations

import re

import numpy as np

# ── KDE-eligible categories and their female-safety weights ──────────────────
# Fraud / Cybercrime is included in MACRO_PRIORITY for completeness but is
# intentionally excluded from KDE_ELIGIBLE — no spatial routing signal.
KDE_ELIGIBLE: list[str] = [
    "Sexual Violence",
    "Kidnapping",
    "Robbery",
    "Murder",
    "Assault",
    "Terrorism / Riot",
    "Theft / Burglary",
    "Drug / Trafficking",
]

FEMALE_WEIGHTS: dict[str, float] = {
    "Sexual Violence"   : 3.0,
    "Kidnapping"        : 2.5,
    "Robbery"           : 2.0,
    "Murder"            : 1.5,
    "Assault"           : 1.5,
    "Terrorism / Riot"  : 1.0,
    "Theft / Burglary"  : 0.7,
    "Drug / Trafficking": 0.5,
}

# ── Regex priority list (ported from EDA crime_data_analysis_v2.py) ───────────
# Each entry: (macro_category_name, [regex_patterns])
# Patterns are matched case-insensitively against the lowercased crime_type string.
MACRO_PRIORITY: list[tuple[str, list[str]]] = [
    ("Sexual Violence", [
        r"rape", r"sexual.?assault", r"molestation", r"molest",
        r"eve.?teas", r"sexual.?harass", r"outrage.*modesty",
        r"gang.?rape", r"gangrape", r"pocso", r"sexual.?abuse",
        r"sexual.?violence", r"sexual.?offence", r"indecent.?assault",
        r"sex.?crime", r"voyeur", r"sexual.?attack",
        r"stalk", r"grope", r"groping",
    ]),
    ("Kidnapping", [
        r"kidnap", r"abduct", r"human.?trafficking",
        r"trafficking.*person", r"person.*trafficking",
        r"child.*trafficking", r"trafficking.*child",
        r"hostage", r"ransom", r"missing.*child", r"child.*missing",
    ]),
    ("Robbery", [
        r"robbery", r"dacoity", r"dacoit", r"\bloot\b", r"looting",
        r"carjack", r"snatch", r"extortion", r"armed.?robbery",
        r"mugging", r"land.?grab",
    ]),
    ("Murder", [
        r"murder", r"homicide", r"culpable.?homicide",
        r"\bkill(ed|ing)\b", r"shot.?dead", r"found.?dead",
        r"body.?found", r"body.?recover", r"strangl",
        r"manslaughter", r"honour.?kill", r"dowry.?death",
        r"suspicious.?death", r"dead.?body",
        r"custodial", r"torture",
    ]),
    ("Assault", [
        r"assault", r"\bbeating\b", r"\bthrash", r"beat.?up",
        r"lynch", r"\bbrawl\b", r"\bstab", r"knife.?attack",
        r"acid.?attack", r"domestic.?violence", r"grievous.?hurt",
        r"attempt.*murder", r"attempt.*homicide",
        r"gunshot", r"physical.?violence", r"\bhurt\b",
        r"racial.?abuse", r"racial.?harass",
    ]),
    ("Terrorism / Riot", [
        r"terror", r"\bbomb\b", r"explos", r"\bblast\b", r"riot",
        r"communal.*(violence|clash)", r"mob.?violence", r"sedition",
        r"\bied\b", r"naxal", r"maoist", r"militant", r"insurgent",
        r"vandal", r"\barson\b", r"hoax.*bomb", r"espionage",
        r"conspiracy.*terror", r"terror.*conspiracy",
        r"conspiracy.*state", r"state.*conspiracy",
        r"public.?disorder", r"clash", r"mischief.*fire",
    ]),
    ("Theft / Burglary", [
        r"theft", r"burglary", r"\bstolen\b", r"pickpocket",
        r"shoplifting", r"house.?break", r"break.?in",
        r"vehicle.?theft", r"pilferage", r"\bburgle",
        r"two.?wheeler.*theft", r"bike.?theft", r"car.?theft",
    ]),
    ("Drug / Trafficking", [
        r"drug", r"narcotic", r"cocaine", r"heroin", r"\bganja\b",
        r"marijuana", r"\bmdma\b", r"amphetamine", r"smuggling",
        r"contraband", r"illegal.*liquor", r"liquor.*illegal",
        r"\bopium\b", r"\bsmack\b", r"cannabis",
        r"arms.*smuggl", r"smuggl.*arms", r"arms.*traffic",
        r"weapon.*smuggl", r"illegal.*weapon", r"weapon.*possess",
        r"arms.*possess", r"illegal.*arm",
    ]),
    ("Fraud / Cybercrime", [
        r"fraud", r"cyber", r"\bscam\b", r"phish", r"\bcheat",
        r"swindl", r"ponzi", r"embezzl", r"misappropriat",
        r"\bbribe", r"corrupt", r"blackmail", r"forgery",
        r"counterfeit", r"money.?launder", r"defamation",
        r"impersonat", r"fake.*document", r"financial.*crime",
        r"financial.*fraud", r"bank.*fraud", r"investment.*fraud",
        r"insurance.*fraud",
    ]),
]


def map_crime_macro(crime_type_str: object) -> str:
    """Map a free-text crime_type string to a macro category.

    Returns:
        'Unknown'  — input is None or NaN
        'Other'    — no regex pattern matched
        category   — first match in MACRO_PRIORITY (highest weight wins)
    """
    if crime_type_str is None or (
        isinstance(crime_type_str, float) and np.isnan(crime_type_str)
    ):
        return "Unknown"
    text = str(crime_type_str).lower().strip()
    for macro, patterns in MACRO_PRIORITY:
        for pattern in patterns:
            if re.search(pattern, text):
                return macro
    return "Other"


# ── Backward-compat alias ─────────────────────────────────────────────────────
# ingest.py previously imported `to_macro` from this module.
# Keep the alias so any external code that used the old name still works
# without a breaking change.
to_macro = map_crime_macro
