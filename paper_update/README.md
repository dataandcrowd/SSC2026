# Manuscript update pack — calibrated model (2026-07-27)

Revised text and figures for `SSC2026_congestion.docm`, rebuilt on the
**calibrated** NetLogo model (scale-factor 160 + suburban destinations,
14 simulated days, seed 11). Every number in the draft's Results section came
from the pre-calibration model and is superseded here.

| File | What it is |
|---|---|
| `abstract_revised.md` | Replacement result sentences for the abstract |
| `methods_revised.md` | Replacement text for *Simulation → Study area and model* and a new *Calibration* subsection |
| `results_revised.md` | Replacement text for *Results* (both subsections) |
| `conclusion_revised.md` | Replacement text for *Conclusion* |
| `numbers.md` | Every quoted figure with its source table, for checking |
| `../output/논문_개정안_한글.md` | Korean summary of the whole pack |

The presentation `presentation/SSC2026_presentation.pptx` has been updated in
place to the same numbers (backup: `SSC2026_presentation.pptx.bak`, script:
`presentation/update_presentation.py`). Slides 2, 3, 5 and 6 carried
pre-calibration figures from a 500-agent run; two results slides were added
after slide 5, one for the hour-of-day profile and one for the map.

Figures referenced by the revised text (all in `output/figures/`):

| Figure | File | Source |
|---|---|---|
| Entry rate by day (mechanism) | `entry_trajectory.png` | `paper-figs` experiment |
| Hour-of-day V/C profile | `sensitivity_hourly_profile.png` | `hourly-profile` experiment |
| Spatial redistribution map | `map_redistribution.png` | `paper-figs` experiment |
| LoS mix by time band | `sensitivity_los_bands.png` | `los-bands` experiment |
| LoS mix by day | `sensitivity_los_daily.png` | `los-bands` experiment |
| BPR curve and LoS bands | `los_bpr_schematic.png` | analytic, no run |

`map_baseline_los.png` is also produced but is **not** recommended for the
paper: it grades each link on the daily peak of the flow EMA, which saturates
at grade F on nearly every link, so the map is almost uniformly dark. Use the
LoS band figure for the same information with the time dimension kept.

Regenerate everything from the tables with:

```bash
python netlogo/sensitivity_experiment/paper_numbers.py
python netlogo/sensitivity_experiment/plot_hourly_profile.py
python netlogo/sensitivity_experiment/plot_los_bands.py
python netlogo/sensitivity_experiment/plot_map_redistribution.py
python netlogo/sensitivity_experiment/plot_entry_trajectory.py
```
