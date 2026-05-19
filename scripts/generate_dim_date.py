"""
generate_dim_date.py
====================

Generates the seed data for `dim_date` conformed dimension table.

Project:    Internal Analytics Platform (PBI replacement, 32Degrees)
Layer:      DWD (Kimball dimensional model)
Target:     mvdevdatabricks.analytics_platform_32degrees.dim_date
Author:     Sia Song
Created:    2026-05-18

Why Python (and not SQL)?
-------------------------
ISO 8601 week semantics are notoriously tricky at year boundaries (e.g.
2024-12-30 belongs to ISO week 2025-W01). Python's `datetime.date.isocalendar()`
is a mature, well-tested standard-library implementation that we trust more
than any single SQL dialect's WEEK function. Generating once in Python and
loading the result into Delta means:

  - Single source of truth for date semantics (no dialect drift)
  - Unit-testable (see sanity checks at the bottom)
  - Version-controlled (committed to git like any other code)
  - Idempotent re-runs (deterministic output for same date range)

Output
------
Writes two files to the same directory:
  1. dim_date_seed.csv      — human-readable, diff-friendly for git
  2. dim_date_seed.parquet  — efficient for Databricks bulk load (optional)

Parquet output requires `pandas` and `pyarrow`. If unavailable, CSV-only
fallback runs without raising.

Usage
-----
  python generate_dim_date.py
  python generate_dim_date.py --start 2020-01-01 --end 2035-12-31
  python generate_dim_date.py --output-dir ../data/seeds

Schema (must match DDL in docs/data_modeling/star_schema_ddl.sql)
-----------------------------------------------------------------
  date_key             INT   YYYYMMDD as integer
  date_value           DATE
  year, quarter, month, month_name
  day_of_month, day_of_year
  iso_year, iso_week, iso_day_of_week, iso_year_week
  iso_week_start_date, iso_week_end_date
  month_start_date, month_end_date
  quarter_start_date, quarter_end_date
  day_name
  is_weekend           BOOLEAN
  created_at           TIMESTAMP
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

# ----------------------------------------------------------------------------
# Defaults
# ----------------------------------------------------------------------------

DEFAULT_START = date(2023, 1, 1)
DEFAULT_END = date(2030, 12, 31)
DEFAULT_OUTPUT_DIR = Path(__file__).parent


# ----------------------------------------------------------------------------
# Row dataclass — order matters, this is the column order in output
# ----------------------------------------------------------------------------

@dataclass
class DimDateRow:
    date_key: int
    date_value: date
    year: int
    quarter: int
    month: int
    month_name: str
    day_of_month: int
    day_of_year: int
    iso_year: int
    iso_week: int
    iso_day_of_week: int
    iso_year_week: str
    iso_week_start_date: date
    iso_week_end_date: date
    month_start_date: date
    month_end_date: date
    quarter_start_date: date
    quarter_end_date: date
    day_name: str
    is_weekend: bool
    created_at: datetime


# ----------------------------------------------------------------------------
# Core generation
# ----------------------------------------------------------------------------

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


def _last_day_of_month(d: date) -> date:
    """Return the last calendar day of d's month."""
    if d.month == 12:
        next_month = date(d.year + 1, 1, 1)
    else:
        next_month = date(d.year, d.month + 1, 1)
    return next_month - timedelta(days=1)


def _quarter_of(month: int) -> int:
    """Return quarter number (1-4) for the given month (1-12)."""
    return (month - 1) // 3 + 1


def _quarter_start(d: date) -> date:
    """Return first day of d's quarter."""
    q = _quarter_of(d.month)
    return date(d.year, (q - 1) * 3 + 1, 1)


def _quarter_end(d: date) -> date:
    """Return last day of d's quarter."""
    q = _quarter_of(d.month)
    end_month = q * 3
    return _last_day_of_month(date(d.year, end_month, 1))


def build_row(d: date, now: datetime) -> DimDateRow:
    """Construct a single DimDateRow from a calendar date."""
    iso = d.isocalendar()  # (iso_year, iso_week, iso_weekday)
    iso_year, iso_week, iso_weekday = iso[0], iso[1], iso[2]

    # ISO week starts on Monday (iso_weekday=1), ends on Sunday (iso_weekday=7)
    iso_week_start = d - timedelta(days=iso_weekday - 1)
    iso_week_end = iso_week_start + timedelta(days=6)

    return DimDateRow(
        date_key=int(d.strftime("%Y%m%d")),
        date_value=d,
        year=d.year,
        quarter=_quarter_of(d.month),
        month=d.month,
        month_name=MONTH_NAMES[d.month],
        day_of_month=d.day,
        day_of_year=d.timetuple().tm_yday,
        iso_year=iso_year,
        iso_week=iso_week,
        iso_day_of_week=iso_weekday,
        iso_year_week=f"{iso_year}-W{iso_week:02d}",
        iso_week_start_date=iso_week_start,
        iso_week_end_date=iso_week_end,
        month_start_date=date(d.year, d.month, 1),
        month_end_date=_last_day_of_month(d),
        quarter_start_date=_quarter_start(d),
        quarter_end_date=_quarter_end(d),
        day_name=DAY_NAMES[d.weekday()],
        is_weekend=d.weekday() >= 5,  # Saturday=5, Sunday=6
        created_at=now,
    )


def generate_rows(start: date, end: date) -> list[DimDateRow]:
    """Generate all dim_date rows in [start, end] inclusive."""
    if start > end:
        raise ValueError(f"start ({start}) must be <= end ({end})")

    now = datetime.utcnow().replace(microsecond=0)
    rows: list[DimDateRow] = []
    d = start
    while d <= end:
        rows.append(build_row(d, now))
        d += timedelta(days=1)
    return rows


# ----------------------------------------------------------------------------
# Output writers
# ----------------------------------------------------------------------------

def write_csv(rows: list[DimDateRow], path: Path) -> None:
    """Write rows to CSV with header."""
    if not rows:
        raise ValueError("No rows to write.")

    fieldnames = list(asdict(rows[0]).keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            d = asdict(row)
            # Normalize date/datetime to ISO strings for CSV
            for k, v in d.items():
                if isinstance(v, (date, datetime)):
                    d[k] = v.isoformat()
            writer.writerow(d)


def write_parquet(rows: list[DimDateRow], path: Path) -> bool:
    """Write rows to Parquet. Returns False if pandas/pyarrow unavailable."""
    try:
        import pandas as pd  # noqa: F401
        import pyarrow  # noqa: F401
    except ImportError:
        return False

    import pandas as pd
    df = pd.DataFrame([asdict(r) for r in rows])
    # Ensure dtypes are explicit (avoid pandas auto-inference surprises)
    df["date_value"] = pd.to_datetime(df["date_value"])
    df["iso_week_start_date"] = pd.to_datetime(df["iso_week_start_date"])
    df["iso_week_end_date"] = pd.to_datetime(df["iso_week_end_date"])
    df["month_start_date"] = pd.to_datetime(df["month_start_date"])
    df["month_end_date"] = pd.to_datetime(df["month_end_date"])
    df["quarter_start_date"] = pd.to_datetime(df["quarter_start_date"])
    df["quarter_end_date"] = pd.to_datetime(df["quarter_end_date"])
    df["created_at"] = pd.to_datetime(df["created_at"])
    df.to_parquet(path, index=False, engine="pyarrow")
    return True


# ----------------------------------------------------------------------------
# Sanity checks — these MUST pass or we have a bug
# ----------------------------------------------------------------------------

def run_sanity_checks(rows: list[DimDateRow]) -> None:
    """Validate known ISO 8601 edge cases. Fails loudly on regression."""
    by_date = {r.date_value: r for r in rows}

    cases = [
        # (date,                  expected_iso_year, expected_iso_week, label)
        (date(2024, 12, 30), 2025, 1,  "2024-12-30 is Monday of ISO 2025-W01"),
        (date(2024, 12, 31), 2025, 1,  "2024-12-31 is Tuesday of ISO 2025-W01"),
        (date(2025, 1, 1),   2025, 1,  "2025-01-01 is Wednesday of ISO 2025-W01"),
        (date(2023, 1, 1),   2022, 52, "2023-01-01 is Sunday of ISO 2022-W52"),
        (date(2024, 1, 1),   2024, 1,  "2024-01-01 is Monday of ISO 2024-W01"),
    ]

    print("\n--- Sanity checks ---")
    failed = 0
    for d, exp_iso_year, exp_iso_week, label in cases:
        if d not in by_date:
            print(f"  SKIP: {label} (date {d} not in range)")
            continue
        row = by_date[d]
        ok = row.iso_year == exp_iso_year and row.iso_week == exp_iso_week
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  {status}: {label}  (got iso_year={row.iso_year}, iso_week={row.iso_week})")

    # Weekend check
    sat = next((r for r in rows if r.date_value == date(2025, 1, 4)), None)
    if sat is not None:
        ok = sat.is_weekend is True and sat.day_name == "Saturday"
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  {status}: 2025-01-04 is_weekend=True, day_name=Saturday")

    if failed > 0:
        print(f"\n  ❌ {failed} sanity check(s) FAILED — investigate before loading.")
        sys.exit(1)
    print("  ✅ All sanity checks passed.\n")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate dim_date seed data for the analytics platform.",
    )
    p.add_argument(
        "--start",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=DEFAULT_START,
        help=f"Start date inclusive (YYYY-MM-DD). Default: {DEFAULT_START}",
    )
    p.add_argument(
        "--end",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=DEFAULT_END,
        help=f"End date inclusive (YYYY-MM-DD). Default: {DEFAULT_END}",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write output files. Default: script's own directory.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print(f"Generating dim_date rows from {args.start} to {args.end} ...")
    rows = generate_rows(args.start, args.end)
    print(f"Generated {len(rows):,} rows.")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = args.output_dir / "dim_date_seed.csv"
    write_csv(rows, csv_path)
    print(f"  ✓ CSV written:     {csv_path}")

    parquet_path = args.output_dir / "dim_date_seed.parquet"
    if write_parquet(rows, parquet_path):
        print(f"  ✓ Parquet written: {parquet_path}")
    else:
        print(
            f"  ⚠ Parquet skipped: pandas/pyarrow not installed.\n"
            f"    To enable: pip install pandas pyarrow"
        )

    run_sanity_checks(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
