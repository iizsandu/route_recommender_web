# ml/data/ingest.py

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

# WHY sys.path manipulation is NOT here: ml/ is run as a package
# (python -m ml.data.ingest), so relative imports work without path hacks.
from ml.data.category_mapping import to_macro

# Sister repo's CosmosReadOnlyClient lives in backend/; we don't import it
# directly. Instead, ingest has its own thin Cosmos fetch (see _fetch_records).
# WHY: ml/ pipeline runs independently of the FastAPI server. Importing
# backend app code would pull in FastAPI, uvicorn, etc. as dependencies.
from azure.cosmos import CosmosClient

logger = logging.getLogger(__name__)

# ── Geographic bounds ─────────────────────────────────────────────────────────
# Delhi-NCR bounding box. Records outside this box are discarded.
LAT_MIN, LAT_MAX = 28.0, 29.5
LNG_MIN, LNG_MAX = 76.5, 78.0

# ── Output path ───────────────────────────────────────────────────────────────
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"

def _fetch_records(connection_string: str, database: str, container: str) -> list[dict]:
    client = CosmosClient.from_connection_string(connection_string)
    db     = client.get_database_client(database)
    ctr    = db.get_container_client(container)

    # WHY enable_cross_partition_query: without it, SELECT * across all
    # logical partitions raises a SDK error. Our container is partitioned
    # by /id so every SELECT * is a cross-partition fan-out.
    items = list(ctr.query_items(
        query="SELECT * FROM c",
        enable_cross_partition_query=True,
    ))
    logger.info("fetched %d raw records from Cosmos", len(items))
    return items


_COSMOS_META = frozenset({"_rid", "_self", "_etag", "_attachments", "_ts"})


def _clean(records: list[dict]) -> pd.DataFrame:
    # Strip Cosmos metadata keys before building DataFrame
    clean = [{k: v for k, v in r.items() if k not in _COSMOS_META}
             for r in records]
    df = pd.DataFrame(clean)

    # WHY to_numeric with errors="coerce": lat/lng may arrive as strings
    # or None; coerce converts bad values to NaN instead of raising.
    df["lat"] = pd.to_numeric(df.get("lat"), errors="coerce")
    df["lng"] = pd.to_numeric(df.get("lng"), errors="coerce")

    # WHY astype(str).str.lower(): is_crime may be bool, int, or string
    # depending on which LLM extraction version wrote the record.
    df["is_crime"] = df.get("is_crime", pd.Series(dtype=object)) \
                       .astype(str).str.lower()
    df = df[df["is_crime"] == "true"].copy()

    # Apply macro category mapping
    df["crime_macro"] = df.get("crime_type", pd.Series(dtype=object)) \
                          .apply(to_macro)

    # Filter to Delhi-NCR bounding box
    before = len(df)
    df = df[
        df["lat"].between(LAT_MIN, LAT_MAX) &
        df["lng"].between(LNG_MIN, LNG_MAX)
    ].copy()
    logger.info("bounding box filter: %d → %d records", before, len(df))

    # Drop any remaining null coordinates
    before = len(df)
    df = df.dropna(subset=["lat", "lng"])
    logger.info("null coordinate drop: %d → %d records", before, len(df))

    return df

def run(
    connection_string: str,
    database: str,
    container: str,
    snapshot_dir: Path = SNAPSHOT_DIR,
) -> Path:
    records = _fetch_records(connection_string, database, container)
    df      = _clean(records)

    if df.empty:
        # WHY raise rather than return: an empty snapshot would silently
        # produce a KDE model trained on zero points. Loud failure here
        # prevents a corrupt model from reaching production.
        raise ValueError("ingest produced 0 records after filtering — aborting")

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    out_path = snapshot_dir / f"crimes_{date.today().isoformat()}.parquet"

    # WHY index=False: the DataFrame index is just 0,1,2,... — meaningless.
    # Writing it wastes space and confuses readers who see an unnamed column.
    df.to_parquet(out_path, index=False)
    logger.info("snapshot written: %s  (%d records)", out_path, len(df))

    return out_path


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)

    run(
        connection_string=os.environ["COSMOS_CONNECTION_STRING"],
        database=os.environ.get("COSMOS_DATABASE_NAME", "route_recommender"),
        container=os.environ.get("COSMOS_CONTAINER_NAME", "structured_crimes"),
    )
