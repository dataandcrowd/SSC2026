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
| `conclusions_bullets.md` | Every conclusion as bullets, including what the paper must not claim |
| `behavioural_extensions.md` | Departure-time and route-choice arms, and who bears the charge |
| `numbers.md` | Every quoted figure with its source table, for checking |
| `decisions_log.md` | Why things were done this way, and what was deferred |
| `../output/논문_개정안_한글.md` | Korean summary of the whole pack |

The presentation `presentation/SSC2026_presentation.pptx` has been updated in
place to the same numbers (backups `SSC2026_presentation.pptx.bak` … `.bak8`,
script `presentation/update_presentation.py`). It grew from 6 slides to 16: the
original numbers came from a pre-calibration 500-agent run, and slides were
added for calibration, equity, the two behavioural extensions, the action-space
comparison and the limitations. Chart images are the plotnine (`_gg`) versions;
the map stays in matplotlib.

2026-07-29 revision: a new slide 7, *How Much to Trust Each Number*, states the
evidence status of every result (measured / derived / superseded / known bias);
the equity slide is retitled *Who Would Pay? Derived, Not Yet Measured* and
carries a provenance strip, since no run records entries by income band; the
displacement slide is captioned with the trip-suppression caveat. The
trip-suppression artefact itself — a declined CBD entry cancelled the agent's
whole day — is now **fixed in the model** (`skip-cbd-stops-today` in
`akl_pricing.nls`); all published numbers predate the fix and the 14-day
`paper-figs` re-run is pending.

Also 2026-07-29: the demand section of `methods_revised.md` was rewritten to
describe the generator the code actually runs. The submitted draft credited
TomTom Move data with the time-of-day profile and NZTA TMS screenlines with
corridor inflow; neither is implemented (see decisions log §9). The
origin-destination matrix is synthetic — origins from Census sector shares,
destinations drawn uniformly from the building stock, departure hours from a
fixed weight list — so only volume and spatial distribution are fitted to
observed counts. The calibration and limitations slides now say so.

Figures referenced by the revised text (all in `output/figures/`):

| Figure | File | Source |
|---|---|---|
| Entry rate by day (mechanism) | `entry_trajectory.png` | `paper-figs` experiment |
| Action space vs the answer | `arms_comparison.png` | `retiming`, `rerouting` |
| Who the charge removes | `equity_by_income.png`, `equity_by_income_gg.png` | derived |
| Departure-time choice | `optin_retiming.png`, `optin_retiming_gg.png` | `retiming` |
| Route choice | `optin_rerouting.png`, `optin_rerouting_gg.png` | `rerouting` |
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
python netlogo/sensitivity_experiment/plot_retiming.py
python netlogo/sensitivity_experiment/plot_arms.py
python netlogo/sensitivity_experiment/plot_equity_optin.py      # matplotlib
python netlogo/sensitivity_experiment/plot_equity_optin_gg.py   # plotnine (_gg)
```

Figures ending `_gg` are the plotnine versions of the same data; both scripts
read the same tables, so either set can be used in the paper.
