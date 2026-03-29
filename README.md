# Twelve Pressing Analyst

Streamlit app (`pressing_app.py`) for exploring pressing metrics from SkillCorner **Dynamic Events** data.

## Where to put the dataset

The app expects a single **data root folder** (`DATA_DIR`). You can place that folder anywhere on disk; what matters is the layout and file names.

### Folder layout

```
<DATA_DIR>/
├── _pressing_cache.parquet    # Combined Dynamic Events table for all matches
├── dynamic/                   # Optional: one .parquet per match (used to build the file above)
└── meta/
    ├── 12345.json             # Match metadata by match_id (date, teams, score, …)
    ├── 12346.json
    └── ...
```

- **`_pressing_cache.parquet`**: Merged parquet from per-match exports; rows include `match_id` and Dynamic Events columns (see `PRESSING_METRICS_DOCUMENTATION.md` for detail).
- **`meta/`**: One `{match_id}.json` per match. The match picker and labels read from these files.

> **Note:** Data is subject to SkillCorner licensing; do not commit large parquet/meta files to this repo. Keep the data on your machine or wherever you obtain it from SkillCorner.

### Pointing the code at your data

In `pressing_app.py`, `DATA_DIR` is currently a fixed Windows path:

```python
DATA_DIR = Path(r"D:\ContextEngineeringProject\dynamic_events_pl_24\dynamic_events_pl_24")
```

Change that line to **your data folder’s full path**, for example:

```python
DATA_DIR = Path(r"C:\data\dynamic_events_pl_24")
```

or, if the data lives inside the project:

```python
DATA_DIR = Path(__file__).resolve().parent / "dynamic_events_pl_24"
```

The same `DATA_DIR` is used for cache files under `pressing_metrics.py`; one root folder is enough.

---

## How to run

### 1. Python environment

Python 3.10+ is recommended. A virtual environment is a good idea:

```powershell
cd D:\ContextEngineeringProject
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Dependencies

```powershell
pip install -r requirements.txt
```

### 3. Launch the app

```powershell
streamlit run pressing_app.py
```

The UI usually opens at `http://localhost:8501`.

---

## Caches and moving to another computer

League/match **derived** files live next to your data (same `DATA_DIR`):

| File | Role |
|------|------|
| `_pressing_league.meta.json` | Invalidation metadata |
| `_pressing_league_table.parquet` | Cached league table |
| `_pressing_league_dist.pkl` | Cached league distributions |
| `_pressing_match.meta.json` | Invalidation metadata |
| `_pressing_match_dist.pkl` | Cached match-level distributions |

They are rebuilt automatically when `_pressing_cache.parquet`’s modification time or the app’s internal `_CACHE_SCHEMA` (in `pressing_app.py`) no longer matches what is stored in the `.meta.json` files.

**If something looks wrong after copying the folder or switching PCs:** delete the five files above (or run the script below with `--clean-derived`), then start the app again. The first load may take longer while tables and distributions are recomputed.

**Streamlit in-memory cache:** use **Settings → Clear cache** in the sidebar, or restart the `streamlit` process, so it does not keep old `pandas` frames.

### Rebuild `_pressing_cache.parquet` from per-match parquets

If you have the `dynamic/` folder (one `.parquet` per match) but not the merged file, or you want a fresh merge:

```powershell
python scripts/build_pressing_cache.py --data-dir "D:\path\to\your\DATA_DIR"
```

To delete derived caches and write a new merged parquet in one step:

```powershell
python scripts/build_pressing_cache.py --data-dir "D:\path\to\your\DATA_DIR" --clean-derived
```

---

## Related files

| File | Description |
|------|-------------|
| `pressing_app.py` | Pressing Analyst UI |
| `pressing_metrics.py` | Metric computations |
| `PRESSING_METRICS_DOCUMENTATION.md` | Metric documentation |
| `PRESSING_METRICS_SPECIFICATION.md` | Formulas / data contract |
| `scripts/build_pressing_cache.py` | Merge `dynamic/*.parquet` → `_pressing_cache.parquet` |

If you use the older `app.py` dashboard, it relies on **`_all_events_cache.parquet`** and a `dynamic/` layout; that is not the same cache as Pressing Analyst.
