"""
Metrics Loader

Loads metric definitions from YAML and provides lookup functions.
Caches the loaded YAML in memory for performance.
"""

from pathlib import Path
from typing import Optional
import yaml


# Path to the YAML file (relative to project root)
METRICS_FILE = Path(__file__).parent.parent / "metrics" / "definitions.yaml"


# Module-level cache: load once, reuse forever
_metrics_cache: Optional[dict] = None


def load_metrics() -> dict:
    """
    Load metric definitions from YAML.
    Cached after first call for performance.
    """
    global _metrics_cache

    if _metrics_cache is not None:
        return _metrics_cache

    if not METRICS_FILE.exists():
        raise FileNotFoundError(f"Metrics file not found: {METRICS_FILE}")

    with open(METRICS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if "metrics" not in data:
        raise ValueError("Invalid YAML: missing 'metrics' key")

    _metrics_cache = data["metrics"]
    return _metrics_cache


def get_metric(metric_id: str) -> Optional[dict]:
    """Get a single metric definition by ID. Returns None if not found."""
    metrics = load_metrics()
    return metrics.get(metric_id)


def list_metrics() -> list[dict]:
    """Return summary info for all metrics (for catalog)."""
    metrics = load_metrics()
    return [
        {
            "id": metric_id,
            "name": metric["name"],
            "description": metric["description"],
            "owner": metric["owner"],
            "unit": metric["unit"],
            "version": metric["version"],
            "status": metric["status"],
            "source_tables": metric.get("source_tables", []),
        }
        for metric_id, metric in metrics.items()
    ]


def reload_metrics() -> None:
    """Force reload from disk (for dev / when YAML changes)."""
    global _metrics_cache
    _metrics_cache = None
    load_metrics()
