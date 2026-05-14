# ml/data/validate.py

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import great_expectations as gx

logger = logging.getLogger(__name__)

# WHY defined here and not imported from category_mapping: validate.py is
# an independent gate. If category_mapping adds a new macro that isn't
# reflected here, this expectation will catch the inconsistency.
KNOWN_MACROS: frozenset[str] = frozenset({
    "Sexual Violence", "Kidnapping", "Robbery", "Assault",
    "Murder", "Theft", "Drug", "Terrorism", "Fraud", "Unknown",
})

# Macros that count as "known" for the 70% threshold — Unknown does not count.
KNOWN_NON_UNKNOWN_MACROS: frozenset[str] = KNOWN_MACROS - {"Unknown"}

AUDIT_DIR = Path(__file__).parent / "audit"

LAT_MIN, LAT_MAX = 28.0, 29.5
LNG_MIN, LNG_MAX = 76.5, 78.0


def validate(df: pd.DataFrame) -> gx.core.ExpectationSuiteValidationResult:
    context = gx.get_context(mode="ephemeral")

    # WHY add_pandas + add_dataframe_asset: GE's fluent API requires a named
    # datasource and asset before it can accept a DataFrame as a batch.
    ds    = context.sources.add_pandas("crimes_ds")
    asset = ds.add_dataframe_asset("crimes_asset")
    batch_request = asset.build_batch_request(dataframe=df)

    suite_name = "crime_suite"
    suite      = context.add_expectation_suite(expectation_suite_name=suite_name)

    validator = context.get_validator(
        batch_request=batch_request,
        expectation_suite_name=suite_name,
    )

    # ── Expectations ──────────────────────────────────────────────────────────
    # Geographic bounds — no mostly: every coordinate must be in Delhi-NCR.
    # A lat=0.0 geocoding error must block training, not be silently absorbed.
    validator.expect_column_values_to_be_between("lat", min_value=LAT_MIN, max_value=LAT_MAX)
    validator.expect_column_values_to_be_between("lng", min_value=LNG_MIN, max_value=LNG_MAX)

    # Macro category — value must be in the known set (includes Unknown).
    # mostly=1.0 (default): zero tolerance for values outside the known set.
    validator.expect_column_values_to_be_in_set(
        "crime_macro", value_set=list(KNOWN_MACROS),
    )

    # effective_date non-null — 80% threshold (LLM can't always parse dates).
    validator.expect_column_values_to_not_be_null("effective_date", mostly=0.80)

    # crime_macro known (not Unknown) — 70% threshold.
    # WHY be_in_set not not_be_null: "Unknown" is not null, it's a string.
    # not_be_null would pass Unknown rows; be_in_set on the non-Unknown set catches them.
    validator.expect_column_values_to_be_in_set(
        "crime_macro",
        value_set=list(KNOWN_NON_UNKNOWN_MACROS),
        mostly=0.70,
    )

    validator.save_expectation_suite(discard_failed_expectations=False)
    return validator.validate()


def run(snapshot_path: Path, audit_dir: Path = AUDIT_DIR) -> Path:
    df = pd.read_parquet(snapshot_path)
    logger.info("loaded snapshot: %s  (%d records)", snapshot_path, len(df))

    results = validate(df)

    # ── Write audit JSON before raising ──────────────────────────────────────
    # WHY before raise: the audit file IS the diagnosis. If we raise first,
    # the file never gets written and engineers have nothing to read.
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / f"audit_{date.today().isoformat()}.json"

    audit_payload = {
        "run_date":      date.today().isoformat(),
        "snapshot":      str(snapshot_path),
        "record_count":  len(df),
        "success":       bool(results.success),
        "results": [
            {
                "expectation": r.expectation_config.expectation_type,
                "column":      r.expectation_config.kwargs.get("column"),
                "success":     bool(r.success),
                "observed":    r.result.get("observed_value"),
            }
            for r in results.results
        ],
    }

    audit_path.write_text(json.dumps(audit_payload, indent=2), encoding="utf-8")
    logger.info("audit written: %s", audit_path)

    # ── Block training if any expectation failed ──────────────────────────────
    if not results.success:
        failed = [r for r in results.results if not r.success]
        raise ValueError(
            f"data validation failed — {len(failed)} expectation(s) not met. "
            f"See {audit_path}"
        )

    return audit_path


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("usage: python -m ml.data.validate <path/to/snapshot.parquet>")
        sys.exit(1)

    run(Path(sys.argv[1]))
