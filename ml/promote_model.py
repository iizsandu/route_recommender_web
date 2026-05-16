# ml/promote_model.py
#
# Champion/challenger gate for the KDE risk model.
#
# Decision rule (from spec):
#   Promote challenger to Production if:
#     PR-AUC improvement  >= 1 percentage point  AND
#     recall@10%          >= 0  (no regression)
#   Otherwise: register as Staging and log reason.
#
# Usage:
#   python -m ml.promote_model <snapshot.parquet> <artifacts_dir>
#
# MLflow model name: "kde_crime_risk"
# Stages: Production (serving), Staging (gated out), Archived (old Production)

from __future__ import annotations

import logging
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

from ml import evaluate

logger = logging.getLogger(__name__)

MODEL_NAME = "kde_crime_risk"

# Gate thresholds from spec Phase 3 plan
MIN_PR_AUC_DELTA  = 0.01   # +1 percentage point
MIN_RECALL_DELTA  = 0.00   # no regression allowed


# ── Champion lookup ───────────────────────────────────────────────────────────

def _champion_metrics(client: MlflowClient) -> dict[str, float] | None:
    # WHY try/except: get_latest_versions raises MlflowException when the
    # registered model doesn't exist yet (first-ever retrain). We treat
    # that as "no champion" and auto-promote the challenger.
    try:
        versions = client.get_latest_versions(MODEL_NAME, stages=["Production"])
    except Exception:
        return None

    if not versions:
        return None

    # WHY tags not a fresh evaluate() pass: re-evaluating the old pkl would
    # require it to still be on disk (not guaranteed after weeks of retrains).
    # Instead, we stamped eval metrics onto the version tags when it was promoted.
    v = versions[0]
    try:
        return {
            "pr_auc":          float(v.tags["pr_auc"]),
            "recall_at_10pct": float(v.tags["recall_at_10pct"]),
        }
    except (KeyError, ValueError):
        # Tags missing = model was registered manually (e.g. bootstrap).
        # Treat as no champion so the first automated run auto-promotes.
        logger.warning(
            "Production model v%s has no eval tags — treating as no champion",
            v.version,
        )
        return None


# ── Gate decision ─────────────────────────────────────────────────────────────

def _decide(
    challenger: dict[str, float],
    champion: dict[str, float] | None,
) -> tuple[bool, str]:
    if champion is None:
        return True, "no_champion_found:auto_promote"

    pr_delta     = challenger["pr_auc"]          - champion["pr_auc"]
    recall_delta = challenger["recall_at_10pct"] - champion["recall_at_10pct"]

    reason = (
        f"pr_auc_delta={pr_delta:+.4f}"
        f" recall_delta={recall_delta:+.4f}"
        f" thresholds=(pr>={MIN_PR_AUC_DELTA}, recall>={MIN_RECALL_DELTA})"
    )

    promoted = pr_delta >= MIN_PR_AUC_DELTA and recall_delta >= MIN_RECALL_DELTA
    return promoted, reason


# ── MLflow run lookup ─────────────────────────────────────────────────────────

def _find_run_id_for_dir(client: MlflowClient, artifacts_dir: Path) -> str:
    # train_kde.py logs all kde_*.pkl files via mlflow.log_artifacts() inside
    # a run, grouped under the "kde_artifacts" artifact path.
    # We search recent runs for one that logged any artifact matching the
    # kde_ prefix — a reliable signal that this run produced the directory.
    # WHY prefix match not exact path: log_artifacts() stores files under
    # "kde_artifacts/kde_{slug}.pkl", so we match on the "kde_" prefix.
    experiments = client.search_experiments()

    for exp in experiments:
        runs = client.search_runs(
            experiment_ids=[exp.experiment_id],
            order_by=["start_time DESC"],
            max_results=50,
        )
        for run in runs:
            # List top-level artifacts, then recurse one level into
            # "kde_artifacts/" where log_artifacts() places the files.
            top_level = [a.path for a in client.list_artifacts(run.info.run_id)]
            artifact_paths: list[str] = list(top_level)
            if "kde_artifacts" in top_level:
                artifact_paths += [
                    a.path
                    for a in client.list_artifacts(
                        run.info.run_id, path="kde_artifacts"
                    )
                ]
            if any(
                Path(p).name.startswith("kde_") and p.endswith(".pkl")
                for p in artifact_paths
            ):
                logger.info(
                    "matched run %s for kde_*.pkl artifacts in %s",
                    run.info.run_id, artifacts_dir,
                )
                return run.info.run_id

    raise FileNotFoundError(
        f"No MLflow run found that logged kde_*.pkl artifacts. "
        "Ensure train_kde.py ran inside mlflow.start_run() before promoting."
    )


# ── Registration ──────────────────────────────────────────────────────────────

def _archive_current_production(client: MlflowClient) -> None:
    # WHY archive before registering: MLflow allows multiple Production
    # versions, but get_latest_versions() returns all of them and the
    # backend's load logic expects exactly one. Archive first → clean state.
    try:
        for v in client.get_latest_versions(MODEL_NAME, stages=["Production"]):
            client.transition_model_version_stage(
                MODEL_NAME, v.version, "Archived"
            )
            logger.info("archived previous Production v%s", v.version)
    except Exception:
        pass  # no existing Production version is fine


def _register_challenger(
    client: MlflowClient,
    run_id: str,
    artifacts_dir: Path,
    challenger_metrics: dict,
    stage: str,
    reason: str,
) -> str:
    # WHY log_artifacts inside a nested run context: register_model needs a
    # model URI pointing to an artifact logged in a run. We re-open the
    # existing run (nested=True) to log the directory, then register via
    # the "kde_artifacts" sub-path within that run.
    with mlflow.start_run(run_id=run_id, nested=True):
        mlflow.log_artifacts(str(artifacts_dir), artifact_path="kde_artifacts")

    # WHY runs:/ URI with artifact sub-path: register_model needs a URI that
    # points to the logged artifact group, not the local filesystem path.
    artifact_uri = f"runs:/{run_id}/kde_artifacts"
    mv = mlflow.register_model(artifact_uri, MODEL_NAME)

    client.transition_model_version_stage(MODEL_NAME, mv.version, stage)

    # Stamp eval metrics as tags so the next promote_model can read them
    # without needing the pkls to still exist on disk.
    for k, v in challenger_metrics.items():
        if isinstance(v, (int, float)):
            client.set_model_version_tag(MODEL_NAME, mv.version, k, f"{v:.6f}")

    client.set_model_version_tag(MODEL_NAME, mv.version, "gate_decision", stage)
    client.set_model_version_tag(MODEL_NAME, mv.version, "gate_reason", reason)

    return mv.version


# ── Main ──────────────────────────────────────────────────────────────────────

def run(snapshot_path: Path, artifacts_dir: Path) -> dict:
    logger.info("evaluating challenger artifacts in: %s", artifacts_dir)

    # 1. Evaluate challenger — creates its own MLflow run, logs all metrics
    challenger_metrics = evaluate.run(snapshot_path, artifacts_dir)

    client = MlflowClient()

    # 2. Read champion metrics from Production model version tags
    champion_metrics = _champion_metrics(client)
    if champion_metrics:
        logger.info(
            "champion   PR-AUC=%.4f  recall@10%%=%.4f",
            champion_metrics["pr_auc"], champion_metrics["recall_at_10pct"],
        )
    else:
        logger.info("no champion found — challenger will be auto-promoted")

    logger.info(
        "challenger PR-AUC=%.4f  recall@10%%=%.4f",
        challenger_metrics["pr_auc"], challenger_metrics["recall_at_10pct"],
    )

    # 3. Gate decision
    promoted, reason = _decide(challenger_metrics, champion_metrics)
    stage = "Production" if promoted else "Staging"
    logger.info("gate decision: %s  (%s)", stage, reason)

    # 4. Find the MLflow run that produced these artifacts
    run_id = _find_run_id_for_dir(client, artifacts_dir)

    # 5. Archive old Production only if we're promoting
    if promoted:
        _archive_current_production(client)

    # 6. Register challenger at the decided stage, stamped with eval metrics
    version = _register_challenger(
        client,
        run_id=run_id,
        artifacts_dir=artifacts_dir,
        challenger_metrics=challenger_metrics,
        stage=stage,
        reason=reason,
    )

    logger.info("registered '%s' v%s as %s", MODEL_NAME, version, stage)

    return {
        "promoted": promoted,
        "stage":    stage,
        "version":  version,
        "reason":   reason,
        **{f"challenger_{k}": v for k, v in challenger_metrics.items()},
        **({f"champion_{k}": v for k, v in champion_metrics.items()}
           if champion_metrics else {}),
    }


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 3:
        print(
            "usage: python -m ml.promote_model "
            "<snapshot.parquet> <artifacts_dir>"
        )
        sys.exit(1)

    result = run(Path(sys.argv[1]), Path(sys.argv[2]))

    print(f"\n── Gate decision: {result['stage']} ──")
    print(f"  promoted : {result['promoted']}")
    print(f"  version  : {result['version']}")
    print(f"  reason   : {result['reason']}")
