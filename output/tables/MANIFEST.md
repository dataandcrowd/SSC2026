# Model-version manifest for output/tables

Every simulation change makes a new model; tables from different versions must
not be compared. From 2026-08-06 the model writes a `model_version` column
(last column) into `days_*`, `hourly_*`, `links_*` and `los_hours_*` exports —
see `model-version` in `netlogo/akl_pricing.nls`. **Files without that column
predate the tagging change**; this manifest records what they are.

## Versions

| Tag | Date | Change |
|---|---|---|
| v1 | 2026-07-27 | calibrated model (scale-factor 160, suburban destinations) |
| v2 | 2026-07-28 | + trip-hour fix (fee hour = travel hour) |
| v3 | 2026-07-30 | + trip-suppression fix (declined CBD entry keeps suburban trips) — `v3-2026-07-30-trip-suppression-fix` |

## Current contents (2026-08-06)

| Files | Version | Written | Notes |
|---|---|---|---|
| `days/hourly/links/los_hours_*_{No-Charge,tou}.csv` (untagged filenames, base arm) | **v3** | 2026-08-06 03:36 | `paper-figs` re-run after the trip-suppression fix |
| `paper-figs-postfix.csv` | **v3** | 2026-08-06 | BehaviorSpace metrics table of the same re-run |
| `days/hourly/links_*_rt.csv`, `_rr.csv`, `_rt_rr.csv` | **v3** | 2026-08-06 (retiming 09:16, rerouting 12:44, rt_rr 16:28) | re-run complete, log `../extension_arms_rerun_20260806.log`; still untagged — the run's JVM predates the tagging change, the column appears from the next run. The retiming OFF cells rewrote the untagged base files byte-identically to the 03:36 `paper-figs` run (determinism check passed) |
| `retiming.csv`, `rerouting.csv`, `retiming-rerouting.csv` | **v3** | 2026-08-06 | BehaviorSpace metrics tables of the same runs |
| `days/hourly/links_*_flat.csv` | pre-v1 | 06-30 | flat-fee cells, never re-run on the calibrated model |
| `sensitivity-*.csv`, `elfarol-seeds.csv` | v1/v2 | 07-27/28 | direction-only until re-run |
| `sensitivity-transit.csv` | v3 + transit-penalty sweep | 2026-08-06 | transit-penalty = 0 arm reproduces v3 exactly |
| `calibration_*.csv`, `calibration-demand*.csv`, `calibration_summary.txt` | v1 | 07-27 | fitted pre-fix; scale-factor 160 needs a post-fix re-check |
| `paper_numbers.txt` | **v3** | 2026-08-06 | regenerated from the v3 base tables |
| `plot_*.csv`, `%los.csv`, `cbd vc over time.csv`, `mean flow vc.csv` | v1/v2 | 07-27/28 | interface-plot exports, superseded |

Full v1/v2 snapshot: `output/tables_prefix_backup_20260805/`.

**Rule of thumb:** after any model change, re-run all four arms (`paper-figs`,
`retiming`, `rerouting`, `retiming-rerouting`) before comparing anything across
arms, and update this manifest.
