# ml/data/category_mapping.py

# WHY keys are lowercase: LLM output is inconsistent in casing; normalise
# once here rather than at every call site.
CRIME_TYPE_TO_MACRO: dict[str, str] = {
    # Sexual violence cluster
    "rape":                  "Sexual Violence",
    "sexual assault":        "Sexual Violence",
    "eve teasing":           "Sexual Violence",
    "molestation":           "Sexual Violence",
    "sexual harassment":     "Sexual Violence",

    # Kidnapping cluster
    "kidnapping":            "Kidnapping",
    "abduction":             "Kidnapping",
    "human trafficking":     "Kidnapping",

    # Robbery cluster
    "robbery":               "Robbery",
    "dacoity":               "Robbery",
    "snatching":             "Robbery",
    "loot":                  "Robbery",

    # Assault / murder cluster
    "assault":               "Assault",
    "murder":                "Murder",
    "attempt to murder":     "Murder",
    "hit and run":           "Assault",

    # Property crime cluster
    "theft":                 "Theft",
    "burglary":              "Theft",
    "arson":                 "Theft",       # property destruction

    # Drug / trafficking
    "drug trafficking":      "Drug",
    "narcotics":             "Drug",
    "drug":                  "Drug",

    # Terror / riot
    "terrorism":             "Terrorism",
    "riot":                  "Terrorism",
    "communal violence":     "Terrorism",

    # Fraud / cybercrime — weight 0.0, kept for completeness
    "fraud":                 "Fraud",
    "cybercrime":            "Fraud",
    "cheating":              "Fraud",
    "extortion":             "Fraud",
}


def to_macro(raw_crime_type: str | None) -> str:
    # WHY return "Unknown" not None: downstream groupby and KDE training
    # filter on string values; None would require extra null checks everywhere.
    if raw_crime_type is None:
        return "Unknown"
    return CRIME_TYPE_TO_MACRO.get(raw_crime_type.strip().lower(), "Unknown")
