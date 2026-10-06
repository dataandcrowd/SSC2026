"""Cross-arm analysis and figures (PNG, 200 dpi, into runs/figures/). Owner: integrator.

    python -m cordonlite.analysis [--runs runs/] [--out runs/figures] [--include-netlogo]
                                  [--seed S] [--all] [--run-dirs DIR ...]
    python -m cordonlite.analysis --compare runs/R-clock_mock_py_s1 runs/R-clock_mock_netlogo_s1

By default only canonical runs are used: runs without a variant suffix (no --regime, --fee-start,
--capacity-scale, --set, or non-default --n-agents/--days) of one seed (--seed, else the seed with
the most runs). --all includes every run, labelled with its differing settings; --run-dirs takes
an explicit list of run folders.

Public API:
    discover_runs(runs_dir, include_netlogo=False, seed=None, include_all=False) -> dict[str, Path]
    load_run(run_dir: Path) -> dict[str, object]          # DataFrames for each run output + summary dict
    compare_runs(a: Path, b: Path) -> dict                 # byte and frame equality of two run folders
    summary_table(runs) -> pd.DataFrame                    # key numbers per run (day 10 vs day 30)
    fig_mode_shares(runs, out) -> Path
    fig_crossings_hist(runs, out, days=(10, 30)) -> Path  # gate-exit (crossing) histograms
    fig_cordon_entries(runs, out) -> Path                  # entries per 15 min, fee schedule panel above
    fig_queue_delay(runs, out) -> Path                     # mean and peak queue delay by day
    fig_calls_per_day(runs, out) -> Path
    table_who_adapts(run, base=(6, 10), end=(26, 30)) -> pd.DataFrame   # modal mode in two windows, twins excluded, Wilson CIs
    twin_summary(run) -> dict                              # twin divergence by day, conditional on the same day-10 option
    llm_diagnostics(run, rule_run=None) -> dict            # v3 7.5: cache hits, distinct prompts per A cell, entropy
    fig_who_adapts(runs, out) -> Path
    table_twins(run, day=11) -> pd.DataFrame
    fig_vickrey_check(run, cfg, out) -> Path
    main(argv=None) -> int

A single y-axis is used throughout; the ToU schedule is drawn in its own panel, not on a twin axis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from cordonlite import fees as feesmod  # noqa: E402
from cordonlite.config import Config, load_config  # noqa: E402
from cordonlite.types import clock_str  # noqa: E402
from cordonlite.vickrey import equilibrium, queue_length  # noqa: E402

DPI = 200
# Categorical slots (validated reference palette, light mode), assigned in fixed order.
SLOTS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
MODE_COLOURS = {"CAR": SLOTS[0], "PT": SLOTS[2], "WFH": SLOTS[3], "SKIP": SLOTS[1]}
ARM_ORDER = ("R-daily", "R-clock", "L-clock", "L-daily")
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
MODES = ("CAR", "PT", "WFH", "SKIP")
OUTPUT_FILES = ("decisions.csv", "outcomes.csv", "profile.csv", "personas.csv", "summary.json",
                "llm_calls.jsonl", "config_snapshot.toml")


# --------------------------------------------------------------------------- loading


def _label(run_dir: Path, summary: dict) -> str:
    m = summary["meta"]
    lab = m["arm"]
    if m["arm"].startswith("L-"):
        lab += " (mock)" if m.get("backend") == "mock" else " [API]"
    if m.get("traits") == "off":
        lab += " (traits off)"
    if m.get("engine") == "netlogo":
        lab += " [NetLogo]"
    if m.get("variant"):
        lab += f" {{{m['variant'].lstrip('_')}}}"
    return lab


def discover_runs(runs_dir: Path, include_netlogo: bool = False, seed: int | None = None,
                  include_all: bool = False) -> dict[str, Path]:
    """Run folders with a summary.json, labelled by arm; NetLogo duplicates skipped by default.

    Unless include_all, only canonical runs (meta.variant empty) of one seed are kept: ``seed``
    if given, else the seed with the most canonical runs. Labels that would repeat get the folder
    name appended."""
    found: list[tuple[tuple, str, Path, dict]] = []
    for d in sorted(Path(runs_dir).iterdir()):
        s = d / "summary.json"
        if not d.is_dir() or not s.exists():
            continue
        summ = json.loads(s.read_text())
        m = summ["meta"]
        if m.get("engine") == "netlogo" and not include_netlogo:
            continue
        arm_i = ARM_ORDER.index(m["arm"]) if m["arm"] in ARM_ORDER else 9
        key = (m.get("traits") == "off", m.get("engine") == "netlogo", arm_i, d.name)
        found.append((key, _label(d, summ), d, m))
    if not include_all:
        canon = [f for f in found if not f[3].get("variant")]
        if seed is None and canon:
            seeds = [f[3]["seed"] for f in canon]
            seed = max(sorted(set(seeds)), key=seeds.count)
        found = [f for f in canon if seed is None or f[3]["seed"] == seed]
    out: dict[str, Path] = {}
    for _k, lab, d, _m in sorted(found, key=lambda f: f[0]):
        if lab in out:
            lab = f"{lab} [{d.name}]"
        out[lab] = d
    return out


def load_run(run_dir: Path) -> dict[str, object]:
    """DataFrames for decisions, outcomes, profile, personas, plus summary and the config snapshot."""
    d = Path(run_dir)
    run: dict[str, object] = {"dir": d}
    for name in ("decisions", "outcomes", "profile", "personas"):
        run[name] = pd.read_csv(d / f"{name}.csv", keep_default_na=True)
    run["summary"] = json.loads((d / "summary.json").read_text())
    run["days"] = pd.DataFrame(run["summary"]["days"])  # type: ignore[index]
    run["label"] = _label(d, run["summary"])  # type: ignore[arg-type]
    return run


def compare_runs(a: Path, b: Path) -> dict:
    """Equality of two run folders: sha256 of each output file plus frame equality of outcomes/profile.

    summary.json and config_snapshot.toml differ in the engine label only, so they are compared
    without it; the two folders must also hold the same set of files.
    """
    res: dict[str, object] = {"a": str(a), "b": str(b), "files": {}}
    ok = True
    names = [sorted(f.name for f in Path(x).iterdir()) for x in (a, b)]
    res["same_file_set"] = names[0] == names[1]
    ok &= bool(res["same_file_set"])
    for f in OUTPUT_FILES:
        pa, pb = Path(a) / f, Path(b) / f
        if f == "summary.json":
            sa, sb = json.loads(pa.read_text()), json.loads(pb.read_text())
            for s in (sa, sb):
                s["meta"].pop("engine", None)
            same = sa == sb
        elif f == "config_snapshot.toml":
            strip = [[ln for ln in x.read_text().splitlines() if not ln.startswith("engine = ")] for x in (pa, pb)]
            same = strip[0] == strip[1]
        else:
            same = hashlib.sha256(pa.read_bytes()).hexdigest() == hashlib.sha256(pb.read_bytes()).hexdigest()
        res["files"][f] = same  # type: ignore[index]
        ok &= same
    oa, ob = pd.read_csv(Path(a) / "outcomes.csv"), pd.read_csv(Path(b) / "outcomes.csv")
    res["outcomes_rows"] = len(oa)
    res["car_rows"] = int((oa["mode"] == "CAR").sum())
    res["outcomes_frame_equal"] = bool(oa.equals(ob))
    res["identical"] = bool(ok and res["outcomes_frame_equal"])
    return res


# --------------------------------------------------------------------------- tables


def _share(days: pd.DataFrame, day: int, col: str) -> float:
    r = days[days["day"] == day].iloc[0]
    tot = r["cars"] + r["pt"] + r["wfh"] + r["skip"]
    return float(r[col]) / float(tot)


def summary_table(runs: Mapping[str, dict], days: tuple[int, int] = (10, 30)) -> pd.DataFrame:
    """Key numbers per run: mode shares on two days, peak delay, revenue, decider calls."""
    rows = []
    for lab, r in runs.items():
        dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
        meta = r["summary"]["meta"]  # type: ignore[index]
        row: dict[str, object] = {"run": lab}
        for d in days:
            if d > dd["day"].max():
                continue
            rec = dd[dd["day"] == d].iloc[0]
            for c, n in (("cars", "car"), ("pt", "pt"), ("wfh", "wfh"), ("skip", "skip")):
                row[f"{n}_share_d{d}"] = round(_share(dd, d, c), 3)
            if "early_shift" in rec:   # share of all commuters working the early day (car or PT)
                row[f"early_shift_share_d{d}"] = round(_share(dd, d, "early_shift"), 3)
            row[f"peak_delay_d{d}"] = round(float(rec.get("peak_bin_delay_wmean", np.nan)), 1)
            row[f"peak_delay_worst_d{d}"] = round(float(rec["peak_bin_delay"]), 1)
            row[f"mean_delay_d{d}"] = round(float(rec["mean_queue_delay"]), 1)
            row[f"revenue_d{d}"] = round(float(rec["revenue"]), 2)
        row["revenue_total"] = meta["revenue_total"]
        row["decider_calls_total"] = meta["decider_calls_total"]
        row["llm_decisions"] = meta["calls_total"]["llm"]
        row["llm_fallback_rule"] = meta["calls_total"]["llm-fallback-rule"]
        rows.append(row)
    return pd.DataFrame(rows)


ARCHETYPE_SHORT = {1: "hybrid\noffice", 2: "on-site\noffice", 3: "shift/\nservice",
                   4: "trades\n(car only)", 5: "student"}


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial share k/n (nan for n = 0)."""
    if n <= 0:
        return (np.nan, np.nan)
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def _twin_ids(per: pd.DataFrame) -> set[int]:
    from cordonlite.persona import TRAIT_NAMES

    a_cols = [c for c in per.columns if c not in ("agent_id", *TRAIT_NAMES)]
    groups = per.groupby(a_cols, dropna=False)["agent_id"].apply(lambda x: sorted(int(v) for v in x))
    return {i for ids in groups for i in ids[1:]}


def _modal_mode(dec: pd.DataFrame, d0: int, d1: int) -> pd.Series:
    """Most frequent mode per agent over days d0..d1 (ties: CAR, PT, WFH, SKIP order)."""
    w = dec[(dec["day"] >= d0) & (dec["day"] <= d1)]
    cnt = w.groupby(["agent_id", "mode"]).size().unstack(fill_value=0).reindex(columns=list(MODES), fill_value=0)
    return cnt.idxmax(axis=1)


def table_who_adapts(run: dict, base: tuple[int, int] = (6, 10),
                     end: tuple[int, int] | None = None) -> pd.DataFrame:
    """Share of drivers (modal mode CAR over the ``base`` days) whose modal mode over the ``end``
    days (default: the last 5 days) is not CAR, by archetype, VoT quintile and each trait level.

    Twins (agents that copy another agent's Layer A) are excluded so no Layer A profile counts
    twice. Shares carry 95% Wilson intervals. Archetype 4 (car only) cannot leave the car except
    by skipping: a structural zero, flagged in ``structural_zero``."""
    dec: pd.DataFrame = run["decisions"]  # type: ignore[assignment]
    per: pd.DataFrame = run["personas"]  # type: ignore[assignment]
    last = int(dec["day"].max())
    end = (max(1, last - 4), last) if end is None else end
    twins = _twin_ids(per)
    a = _modal_mode(dec, *base)
    b = _modal_mode(dec, *end)
    df = per[~per["agent_id"].isin(twins)].set_index("agent_id")[
        ["archetype", "vot_quintile", "H", "F", "P", "S", "must_drive"]].copy()
    df["car_base"] = (a.reindex(df.index) == "CAR")
    df["left_car"] = df["car_base"] & (b.reindex(df.index) != "CAR")
    rows = []
    for g in ("archetype", "vot_quintile", "H", "F", "P", "S"):
        for lv, sub in df.groupby(g):
            cars = sub[sub["car_base"]]
            n, k = len(cars), int(cars["left_car"].sum())
            lo, hi = wilson(k, n)
            rows.append({"group": g, "level": int(lv), "n": len(sub), "n_car_base": n,
                         "left_car_share": round(k / n, 3) if n else np.nan,
                         "ci_low": round(lo, 3), "ci_high": round(hi, 3),
                         "structural_zero": bool(g == "archetype" and len(sub) and sub["must_drive"].all()),
                         "base_days": f"{base[0]}-{base[1]}", "end_days": f"{end[0]}-{end[1]}"})
    return pd.DataFrame(rows)


def twin_summary(run: dict, days: Sequence[int] = (1, 10, 11, 12, 20, 30)) -> dict:
    """Twin pairs (identical Layer A): how many choose different options on each day, and on day
    11 how many differ among the pairs that held the same option on day 10 (same starting state)."""
    per: pd.DataFrame = run["personas"]  # type: ignore[assignment]
    dec: pd.DataFrame = run["decisions"]  # type: ignore[assignment]
    from cordonlite.persona import TRAIT_NAMES

    a_cols = [c for c in per.columns if c not in ("agent_id", *TRAIT_NAMES)]
    groups = per.groupby(a_cols, dropna=False)["agent_id"].apply(lambda x: sorted(int(v) for v in x))
    pairs = [(ids[0], j) for ids in groups if len(ids) > 1 for j in ids[1:]]
    opt = dec.set_index(["day", "agent_id"])["option_id"]
    last = int(dec["day"].max())
    out: dict[str, object] = {"run": run["label"], "n_pairs": len(pairs)}
    for d in days:
        if d <= last:
            out[f"differ_d{d}"] = int(sum(opt[(d, i)] != opt[(d, j)] for i, j in pairs))
    if 11 <= last:
        same10 = [(i, j) for i, j in pairs if opt[(10, i)] == opt[(10, j)]]
        out["same_d10"] = len(same10)
        out["differ_d11_given_same_d10"] = int(sum(opt[(11, i)] != opt[(11, j)] for i, j in same10))
    return out


def llm_diagnostics(run: dict, rule_run: dict | None = None) -> dict:
    """v3 section 7.5 heterogeneity diagnostics for an LLM arm (empty dict for a rule arm).

    cache hit rate and shared answers; distinct prompts / LLM-decided agents, overall and per Layer A
    cell (archetype x VoT quintile) on the first charged day; within-cell mode entropy on that
    day, and its ratio to the rule arm ``rule_run`` (flattening check, v3 10.4)."""
    meta = run["summary"]["meta"]  # type: ignore[index]
    if not meta["arm"].startswith("L-"):
        return {}
    log = Path(run["dir"]) / "llm_calls.jsonl"  # type: ignore[arg-type]
    recs = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    final = {}
    for r in recs:  # last attempt per agent-day
        final[(r["day"], r["agent_id"])] = r
    per = run["personas"].set_index("agent_id")  # type: ignore[union-attr]
    fs = int(meta.get("fee_start_day") or 0)
    out: dict[str, object] = {
        "run": run["label"], "records": len(recs), "agent_days": len(final),
        "cache_hit_rate": round(float(np.mean([r["cache_hit"] for r in final.values()])), 4) if final else None,
        "shared_answers": int(sum(r.get("shared", False) for r in final.values())),
        "distinct_prompts_per_agent": round(len({r["cache_key"] for r in final.values()}) / len(final), 4) if final else None,
    }
    day_recs = [r for (d, _a), r in final.items() if d == fs]
    if day_recs:
        cells: dict[tuple, set] = {}
        n_cell: dict[tuple, int] = {}
        for r in day_recs:
            p = per.loc[r["agent_id"]]
            c = (int(p["archetype"]), int(p["vot_quintile"]))
            cells.setdefault(c, set()).add(r["cache_key"])
            n_cell[c] = n_cell.get(c, 0) + 1
        out[f"distinct_prompts_per_agent_in_cell_d{fs}"] = round(
            float(np.mean([len(cells[c]) / n_cell[c] for c in cells])), 4)

    def entropy(r: dict, day: int) -> float:
        dec = r["decisions"]
        pp = r["personas"].set_index("agent_id")
        sub = dec[dec["day"] == day].join(pp[["archetype", "vot_quintile"]], on="agent_id")
        hs, ws = [], []
        for _c, g in sub.groupby(["archetype", "vot_quintile"]):
            q = g["mode"].value_counts(normalize=True).to_numpy()
            hs.append(float(-(q * np.log2(q)).sum()))
            ws.append(len(g))
        return float(np.average(hs, weights=ws)) if ws else float("nan")
    if fs:
        h_llm = entropy(run, fs)
        out[f"within_cell_mode_entropy_d{fs}"] = round(h_llm, 4)
        if rule_run is not None:
            h_rule = entropy(rule_run, fs)
            out[f"within_cell_mode_entropy_d{fs}_rule"] = round(h_rule, 4)
            out["entropy_ratio_llm_over_rule"] = round(h_llm / h_rule, 4) if h_rule > 0 else None
    return out


def table_twins(run: dict, day: int = 11) -> pd.DataFrame:
    """Twin pairs (identical Layer A, own Layer B): traits, day-10 and day-`day` choices and reasons."""
    from cordonlite.persona import TRAIT_NAMES

    per: pd.DataFrame = run["personas"]  # type: ignore[assignment]
    dec: pd.DataFrame = run["decisions"]  # type: ignore[assignment]
    a_cols = [c for c in per.columns if c not in ("agent_id", *TRAIT_NAMES)]
    groups = per.groupby(a_cols, dropna=False)["agent_id"].apply(lambda s: sorted(int(x) for x in s))
    d0 = dec[dec["day"] == day - 1].set_index("agent_id")
    d1 = dec[dec["day"] == day].set_index("agent_id")
    pt = per.set_index("agent_id")
    rows = []
    for ids in groups:
        if len(ids) < 2:
            continue
        orig = ids[0]
        for twin in ids[1:]:
            for role, aid in (("original", orig), ("twin", twin)):
                p = pt.loc[aid]
                rows.append({
                    "pair": f"{orig}-{twin}", "role": role, "agent_id": aid,
                    "archetype": int(p["archetype"]), "vot": round(float(p["vot"]), 2),
                    "tstar": clock_str(int(p["tstar_min"])),
                    "HFPS": "".join(str(int(p[t])) for t in TRAIT_NAMES),
                    f"option_d{day - 1}": d0.loc[aid, "option_id"],
                    f"option_d{day}": d1.loc[aid, "option_id"],
                    "decider": d1.loc[aid, "decider"],
                    "reason": d1.loc[aid, "reason"] if isinstance(d1.loc[aid, "reason"], str) else "",
                })
    out = pd.DataFrame(rows)
    if len(out):
        diff = out.groupby("pair")[f"option_d{day}"].nunique() > 1
        out["pair_differs"] = out["pair"].map(diff)
    return out


# --------------------------------------------------------------------------- figure helpers


def _style(ax: plt.Axes) -> None:
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=7)
    ax.title.set_color(INK)
    ax.xaxis.label.set_color(INK2)
    ax.yaxis.label.set_color(INK2)


def _events(ax: plt.Axes, meta: dict) -> None:
    fs = meta.get("fee_start_day")
    if meta.get("fee_regime") != "none" and fs:
        ax.axvline(fs - 0.5, color=INK2, linewidth=0.8, linestyle="--")
    dd = meta.get("pt_disruption_day")
    if dd and dd <= meta.get("n_days", 0):
        ax.axvline(dd, color=INK2, linewidth=0.8, linestyle=":")


def _grid(n: int, w: float = 3.4, h: float = 2.6) -> tuple[plt.Figure, np.ndarray]:
    ncol = min(n, 3) if n != 4 else 2
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(w * ncol, h * nrow), squeeze=False)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    return fig, axes


def _save(fig: plt.Figure, out: Path, name: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    p = out / name
    fig.savefig(p, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def _arm_ls(lab: str) -> str:
    """Dashed for L-daily so it stays visible where it overlaps R-daily."""
    return "--" if lab.startswith("L-daily") else "-"


def _arm_colour(lab: str, i: int) -> str:
    base = lab.split(" ")[0]
    if base in ARM_ORDER and "traits off" not in lab:
        return SLOTS[ARM_ORDER.index(base)]
    return SLOTS[4 + (i % 4)]


# --------------------------------------------------------------------------- figures


def fig_mode_shares(runs: Mapping[str, dict], out: Path) -> Path:
    """Daily mode shares, one stacked-area panel per run (dashed: charge starts; dotted: PT disruption)."""
    fig, axes = _grid(len(runs))
    for ax, (lab, r) in zip(axes.flat, runs.items()):
        dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
        tot = dd[["cars", "pt", "wfh", "skip"]].sum(axis=1)
        ys = [dd[c] / tot for c in ("cars", "pt", "wfh", "skip")]
        ax.stackplot(dd["day"], *ys, colors=[MODE_COLOURS[m] for m in MODES], labels=MODES,
                     edgecolor="white", linewidth=0.6)
        _events(ax, r["summary"]["meta"])  # type: ignore[index]
        ax.set_ylim(0, 1)
        ax.set_xlim(dd["day"].min(), dd["day"].max())
        ax.set_title(lab, fontsize=9)
        ax.set_xlabel("day", fontsize=8)
        ax.set_ylabel("share of commuters", fontsize=8)
        _style(ax)
    h, l_ = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l_, loc="lower center", ncol=4, frameon=False, fontsize=8, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Daily mode shares by arm", fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return _save(fig, out, "mode_shares.png")


def _fee_panel(ax: plt.Axes, cfg: Config, lo: int, hi: int) -> None:
    tbl = feesmod.fee_table_from_config(cfg, "tou" if cfg.fees.regime == "none" else None)
    m = np.arange(lo, hi + 1)
    ax.plot(m, [tbl[i] for i in m], color=INK2, linewidth=1.5)
    ax.set_ylabel("charge NZ$", fontsize=7)
    ax.set_ylim(0, max(tbl) * 1.25)
    _style(ax)


def _clock_ticks(ax: plt.Axes, lo: int, hi: int, step: int = 60) -> None:
    t = list(range(lo - lo % step + (step if lo % step else 0), hi + 1, step))
    ax.set_xticks(t)
    ax.set_xticklabels([clock_str(x) for x in t])


X_LO, X_HI = 360, 615   # 06:00 to 10:15: no crossings happen after 10:00 in practice


def fig_crossings_hist(runs: Mapping[str, dict], out: Path, days: tuple[int, int] = (10, 30),
                       cfg: Config | None = None) -> Path:
    """Gate-exit (cordon-crossing) histograms, 15-min bins, day 10 vs day 30, one panel per run."""
    cfg = cfg or load_config()
    lo, hi = X_LO, X_HI
    bins = np.arange(lo, hi + 15, 15)
    n = len(runs)
    ncol = 2 if n == 4 else min(n, 3)
    nrow = int(np.ceil(n / ncol))
    fig = plt.figure(figsize=(3.6 * ncol, 3.0 * nrow + 0.9))
    gs = fig.add_gridspec(nrow + 1, ncol, height_ratios=[0.35] + [1.0] * nrow)
    for c in range(ncol):
        _fee_panel(fig.add_subplot(gs[0, c]), cfg, lo, hi)
        fig.axes[-1].set_xlim(lo, hi)
        _clock_ticks(fig.axes[-1], lo, hi)
        fig.axes[-1].set_title("ToU charge at crossing time", fontsize=8)
    cols = (SLOTS[0], SLOTS[1])
    for i, (lab, r) in enumerate(runs.items()):
        ax = fig.add_subplot(gs[1 + i // ncol, i % ncol])
        o: pd.DataFrame = r["outcomes"]  # type: ignore[assignment]
        for d, col in zip(days, cols):
            x = o[(o["day"] == d) & (o["mode"] == "CAR") & (o["gate_exit_min"] >= 0)]["gate_exit_min"]
            ax.hist(x, bins=bins, histtype="step", linewidth=2, color=col, label=f"day {d} ({len(x)} cars)")
        ax.set_xlim(lo, hi)
        _clock_ticks(ax, lo, hi)
        ax.set_title(lab, fontsize=9)
        ax.set_ylabel("cars crossing per 15 min", fontsize=8)
        ax.legend(fontsize=7, frameon=False)
        _style(ax)
    fig.suptitle("Cordon crossings (gate exits) before and after the charge", fontsize=10, color=INK)
    fig.tight_layout()
    return _save(fig, out, "crossings_hist.png")


def fig_cordon_entries(runs: Mapping[str, dict], out: Path, cfg: Config | None = None,
                       pre: tuple[int, int] = (6, 10), post: tuple[int, int] = (21, 30)) -> Path:
    """Cordon entries per 15 min (mean over pre-charge and post-charge days), one line per run,
    with the ToU schedule in a panel above (no twin axis)."""
    cfg = cfg or load_config()
    lo, hi = X_LO, X_HI
    fig, (axf, ax1, ax2) = plt.subplots(3, 1, figsize=(7.0, 7.0), sharex=True,
                                        gridspec_kw={"height_ratios": [0.4, 1, 1]})
    _fee_panel(axf, cfg, lo, hi)
    axf.set_title("ToU charge (from day %d)" % cfg.fees.fee_start_day, fontsize=9)
    for ax, (d0, d1), ttl in ((ax1, pre, "before the charge"), (ax2, post, "with the charge")):
        for i, (lab, r) in enumerate(runs.items()):
            dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
            sub = dd[(dd["day"] >= d0) & (dd["day"] <= d1)]
            if len(sub) == 0:
                continue
            ent = pd.DataFrame(list(sub["entries_per_15min"])).mean()
            mins = [int(k[:2]) * 60 + int(k[3:]) for k in ent.index]
            ax.plot(np.array(mins) + 7.5, ent.to_numpy(), color=_arm_colour(lab, i), linewidth=2,
                    marker="o", markersize=3, label=lab)
        ax.set_title(f"Cordon entries per 15 min, mean of days {d0}-{d1} ({ttl})", fontsize=9)
        ax.set_ylabel("cars per 15 min", fontsize=8)
        ax.legend(fontsize=7, frameon=False, ncol=2)
        _style(ax)
    ax2.set_xlim(lo, hi)
    _clock_ticks(ax2, lo, hi)
    fig.tight_layout()
    return _save(fig, out, "cordon_entries.png")


def fig_queue_delay(runs: Mapping[str, dict], out: Path) -> Path:
    """Mean queue delay of cars, and the peak 15-min-bin mean delay by day: car-weighted mean over
    corridors (the calibrated metric, solid) and the worst corridor (thin dotted)."""
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.4))
    meta0 = None
    for i, (lab, r) in enumerate(runs.items()):
        dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
        meta0 = r["summary"]["meta"]  # type: ignore[index]
        col = _arm_colour(lab, i)
        axes[0].plot(dd["day"], dd["mean_queue_delay"], color=col, linewidth=2, linestyle=_arm_ls(lab), label=lab)
        if "peak_bin_delay_wmean" in dd:
            axes[1].plot(dd["day"], dd["peak_bin_delay_wmean"], color=col, linewidth=2,
                         linestyle=_arm_ls(lab), label=lab)
        axes[1].plot(dd["day"], dd["peak_bin_delay"], color=col, linewidth=0.8, linestyle=":")
    for ax, t in zip(axes, ("Mean queue delay per car (min)",
                            "Peak 15-min mean delay (min): car-weighted mean of\ncorridors (solid, "
                            "calibrated metric); worst corridor (dotted)")):
        if meta0:
            _events(ax, meta0)
        ax.set_title(t, fontsize=9)
        ax.set_xlabel("day", fontsize=8)
        _style(ax)
    axes[0].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    return _save(fig, out, "queue_delay.png")


def fig_calls_per_day(runs: Mapping[str, dict], out: Path) -> Path:
    """Decider calls per day (rule, LLM and fallback; standing days excluded), log scale."""
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    meta0 = None
    for i, (lab, r) in enumerate(runs.items()):
        dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
        meta0 = r["summary"]["meta"]  # type: ignore[index]
        calls = [c["rule"] + c["llm"] + c["llm-fallback-rule"] for c in dd["calls"]]
        tot = sum(calls)
        ax.plot(dd["day"], np.maximum(calls, 0.8), color=_arm_colour(lab, i), linewidth=2,
                linestyle=_arm_ls(lab), marker="o", markersize=3, label=f"{lab} (total {tot})")
    if meta0:
        _events(ax, meta0)
    ax.set_yscale("log")
    ax.set_ylabel("decider calls per day (log)", fontsize=8)
    ax.set_xlabel("day", fontsize=8)
    ax.set_title("Decider calls per day: daily arms vs cognitive clock (0 drawn at 0.8)", fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    _style(ax)
    fig.tight_layout()
    return _save(fig, out, "calls_per_day.png")


def fig_who_adapts(runs: Mapping[str, dict], out: Path) -> Path:
    """Share of drivers (modal mode CAR on days 6-10) not driving (modal mode, last 5 days), by
    group and level, per run, with 95% Wilson intervals; groups with n < 10 drivers are greyed
    out and annotated, structural zeros (car only) marked."""
    groups = ("archetype", "vot_quintile", "H", "F", "P", "S")
    titles = {"archetype": "archetype", "vot_quintile": "VoT quintile", "H": "habit H",
              "F": "flexibility F", "P": "PT openness P", "S": "cost salience S"}
    tabs = {lab: table_who_adapts(r) for lab, r in runs.items()}
    fig, axes = plt.subplots(2, 3, figsize=(11.5, 6.2))
    k = len(runs)
    w = 0.8 / max(k, 1)
    for ax, g in zip(axes.flat, groups):
        for i, (lab, t) in enumerate(tabs.items()):
            sub = t[t["group"] == g]
            x = sub["level"].to_numpy() + (i - (k - 1) / 2) * w
            y = sub["left_car_share"].to_numpy(dtype=float)
            small = sub["n_car_base"].to_numpy() < 10
            col = _arm_colour(lab, i)
            ax.bar(x[~small], np.nan_to_num(y[~small]), width=w * 0.9, color=col, label=lab,
                   edgecolor="white", linewidth=0.5)
            ax.bar(x[small], np.nan_to_num(y[small]), width=w * 0.9, color=col, alpha=0.25,
                   edgecolor="white", linewidth=0.5)
            err = np.vstack([y - sub["ci_low"].to_numpy(dtype=float), sub["ci_high"].to_numpy(dtype=float) - y])
            ax.errorbar(x, y, yerr=np.nan_to_num(err), fmt="none", ecolor=INK2, elinewidth=0.6, capsize=1.5)
            if i == 0:
                for lv, n, sz in zip(sub["level"], sub["n_car_base"], sub["structural_zero"]):
                    txt = "car only" if sz else f"n={n}"
                    ax.text(lv, 1.02, txt, ha="center", va="bottom", fontsize=5.5, color=INK2)
        ax.set_title(titles[g], fontsize=9, pad=12)
        ax.set_ylim(0, 1.1)
        ax.set_xticks([1, 2, 3, 4, 5])
        if g == "archetype":
            ax.set_xticklabels([ARCHETYPE_SHORT[i] for i in range(1, 6)], fontsize=6)
        _style(ax)
    for a in (axes.flat[0], axes.flat[3]):
        a.set_ylabel("share of drivers (days 6-10)\nnot driving (last 5 days)", fontsize=8)
    h, l_ = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l_, loc="lower center", ncol=min(k, 6), frameon=False, fontsize=8, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Who adapts: leaving the car by persona group (twins excluded; 95% Wilson intervals; "
                 "pale bars: fewer than 10 drivers; n = drivers of the first run)", fontsize=9, color=INK)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return _save(fig, out, "who_adapts.png")


def fig_vickrey_check(run: dict, cfg: Config, out: Path, days: tuple[int, int] = (6, 10)) -> Path:
    """Simulated queue length at the busiest corridor (pre-charge days) against the analytical
    Vickrey no-toll equilibrium for the same N and capacity (homogeneous commuters, mean VoT,
    Small 1982 ratios, t* at the gate = median of the drivers' t* minus gate-to-destination time)."""
    prof: pd.DataFrame = run["profile"]  # type: ignore[assignment]
    o: pd.DataFrame = run["outcomes"]  # type: ignore[assignment]
    per: pd.DataFrame = run["personas"]  # type: ignore[assignment]
    meta = run["summary"]["meta"]  # type: ignore[index]
    d0, d1 = days
    cars = o[(o["mode"] == "CAR") & (o["day"] >= d0) & (o["day"] <= d1)]
    busiest = int(cars["corridor_id"].value_counts().idxmax())
    s = float(meta["capacity_per_min"][str(busiest)])
    N = float((cars["corridor_id"] == busiest).sum()) / (d1 - d0 + 1)
    ids = cars[cars["corridor_id"] == busiest]["agent_id"].unique()
    pp = per[per["agent_id"].isin(ids)]
    tstar_gate = float(np.median(pp["tstar_min"] - pp["fftt_gate_to_dest_min"]))
    alpha = float(pp["vot"].mean()) / 60.0
    res = equilibrium(N, s, alpha, cfg.costs.beta_ratio * alpha, cfg.costs.gamma_ratio * alpha, tstar_gate)
    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    p = prof[(prof["corridor_id"] == busiest) & (prof["day"] >= d0) & (prof["day"] <= d1)]
    for d, sub in p.groupby("day"):
        ax.plot(sub["minute"], sub["queue_len"], color=SLOTS[0], linewidth=1, alpha=0.45,
                label="simulated, days %d-%d" % (d0, d1) if d == d0 else None)
    t = np.linspace(res.t_first - 10, res.t_last + 10, 400)
    ax.plot(t, queue_length(res, t), color=SLOTS[1], linewidth=2,
            label=f"Vickrey equilibrium, one t* (N={N:.0f}, s={s:.2f}/min)")
    ax.set_xlim(360, 690)
    _clock_ticks(ax, 360, 690)
    ax.set_ylabel("queue length (cars)", fontsize=8)
    name = meta["corridor_names"][str(busiest)]
    ax.set_title(f"{run['label']}: corridor {busiest} {name}\nrush length N/s = {res.rush_len:.0f} min, "
                 f"equilibrium cost delta*N/s = NZ${res.cost_per_commuter:.2f}", fontsize=8)
    ax.legend(fontsize=7, frameon=False)
    _style(ax)
    fig.tight_layout()
    return _save(fig, out, "vickrey_check.png")


# --------------------------------------------------------------------------- CLI


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cordonlite.analysis")
    ap.add_argument("--runs", default=None, help="runs folder (default run.runs_dir)")
    ap.add_argument("--out", default=None, help="figures folder (default <runs>/figures)")
    ap.add_argument("--include-netlogo", action="store_true")
    ap.add_argument("--seed", type=int, default=None, help="seed of the canonical runs (default: most runs)")
    ap.add_argument("--all", action="store_true", help="include variant runs (labelled by their settings)")
    ap.add_argument("--run-dirs", nargs="+", default=None, help="explicit run folders instead of discovery")
    ap.add_argument("--compare", nargs=2, metavar=("RUN_A", "RUN_B"), default=None)
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.compare:
        res = compare_runs(Path(args.compare[0]), Path(args.compare[1]))
        print(json.dumps(res, indent=1))
        return 0 if res["identical"] else 1
    runs_dir = Path(args.runs) if args.runs else cfg.resolve_path(cfg.run.runs_dir)
    out = Path(args.out) if args.out else runs_dir / "figures"
    if args.run_dirs:
        found = {}
        for d in args.run_dirs:
            lab = _label(Path(d), json.loads((Path(d) / "summary.json").read_text()))
            found[lab if lab not in found else f"{lab} [{Path(d).name}]"] = Path(d)
    else:
        found = discover_runs(runs_dir, args.include_netlogo, args.seed, args.all)
    if not found:
        print(f"no runs with summary.json under {runs_dir}", file=sys.stderr)
        return 1
    runs = {lab: load_run(d) for lab, d in found.items()}
    main_runs = {k: v for k, v in runs.items() if "traits off" not in k} or runs
    out.mkdir(parents=True, exist_ok=True)
    written = [
        fig_mode_shares(runs, out),
        fig_crossings_hist(main_runs, out, cfg=cfg),
        fig_cordon_entries(main_runs, out, cfg=cfg),
        fig_queue_delay(runs, out),
        fig_calls_per_day(runs, out),
        fig_who_adapts(runs, out),
    ]
    ref = next((v for k, v in runs.items() if k.startswith("R-daily")), next(iter(runs.values())))
    written.append(fig_vickrey_check(ref, cfg, out))
    st = summary_table(runs)
    st.to_csv(out / "summary_table.csv", index=False)
    (out / "summary_table.md").write_text(_md_table(st))
    for stale in ("departure_hist.png",):  # renamed outputs of earlier versions
        (out / stale).unlink(missing_ok=True)
    for f in list(out.glob("who_adapts_*.csv")) + list(out.glob("twins_day11_*.csv")):
        f.unlink()
    rule_refs = {False: runs.get("R-clock"), True: runs.get("R-clock (traits off)")}  # matched information
    twins, diags = [], []
    for lab, r in runs.items():
        slug = (lab.replace(" ", "_").replace("(", "").replace(")", "").replace("[", "")
                .replace("]", "").replace("{", "").replace("}", ""))
        table_who_adapts(r).to_csv(out / f"who_adapts_{slug}.csv", index=False)
        tw = table_twins(r)
        tw.to_csv(out / f"twins_day11_{slug}.csv", index=False)
        twins.append(twin_summary(r))
        dg = llm_diagnostics(r, rule_refs["traits off" in lab])
        if dg:
            diags.append(dg)
    tws = pd.DataFrame(twins)
    tws.to_csv(out / "twins_summary.csv", index=False)
    (out / "twins_summary.md").write_text(
        _md_table(tws) + "\nTwins share Layer A. Rule noise uses common random numbers for twins and MockLLM "
        "is seeded by the prompt, so with traits off (identical A and B) a difference comes from "
        "history only. MockLLM is a pipeline check, not an LLM.\n")
    if diags:
        dgf = pd.DataFrame(diags)
        dgf.to_csv(out / "llm_diagnostics.csv", index=False)
        (out / "llm_diagnostics.md").write_text(_md_table(dgf))
    for p in written:
        print(p)
    print(out / "summary_table.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
