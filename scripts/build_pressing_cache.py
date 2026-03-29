"""
Build `_pressing_cache.parquet` from per-match parquet files under `<DATA_DIR>/dynamic/`.

Same layout as `app.py` expects: one `.parquet` per match in `dynamic/`.

Usage:
  python scripts/build_pressing_cache.py --data-dir "D:/path/to/dynamic_events_pl_24"
  python scripts/build_pressing_cache.py --data-dir "..." --clean-derived
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DERIVED_NAMES = (
    "_pressing_league.meta.json",
    "_pressing_league_table.parquet",
    "_pressing_league_dist.pkl",
    "_pressing_match.meta.json",
    "_pressing_match_dist.pkl",
)


def clean_derived(data_dir: Path) -> None:
    for name in DERIVED_NAMES:
        fp = data_dir / name
        if fp.is_file():
            fp.unlink()
            print(f"Removed {fp}")


def build_cache(data_dir: Path) -> Path:
    dynamic = data_dir / "dynamic"
    files = sorted(dynamic.glob("*.parquet"))
    if not files:
        raise SystemExit(f"No parquet files under {dynamic}")

    frames = [pd.read_parquet(f) for f in files]
    combined = pd.concat(frames, ignore_index=True)
    out = data_dir / "_pressing_cache.parquet"
    data_dir.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(out, index=False, engine="pyarrow")
    print(f"Wrote {out} ({len(combined):,} rows, {len(files)} files)")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Build _pressing_cache.parquet from dynamic/*.parquet")
    p.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Folder containing `dynamic/` (parquets) and optionally `meta/`",
    )
    p.add_argument(
        "--clean-derived",
        action="store_true",
        help="Delete league/match derived caches so the app rebuilds them on next run",
    )
    args = p.parse_args()
    data_dir = args.data_dir.resolve()

    if args.clean_derived:
        clean_derived(data_dir)

    build_cache(data_dir)

    if args.clean_derived:
        print("Derived caches were cleared before build; first app load will recreate them.")


if __name__ == "__main__":
    main()
