"""Census travel to work -> car drivers into the cordon by home SA2 (data/od_sa2.csv).

Owner: prep builder. See INTERFACES.md. Run before prep.build_inputs, which reads the output as
``prep.od_csv``.

    python -m prep.build_od [--config config.toml] [--out-dir data]

Source: Stats NZ, 2023 Census main means of travel to work by statistical area 2 (usual residence
SA2 x workplace SA2, counts by mode; ``prep.census_od_csv``), with SA2 polygons (``prep.sa2_gpkg``)
to locate the SA2s. Licensed CC BY 4.0 by Stats NZ.

Definitions [author decision 2026-10-16]:
    - workplace SA2s in the cordon: SA2s whose representative point lies inside the cordon polygon
      (load_cordon; the 17 SA2s of SA3 "Auckland City Centre");
    - commuters: usual residence outside the cordon, workplace in the cordon (residents of the cordon
      never cross it);
    - drivers: the sum of ``prep.od_modes`` (drive a private car, truck or van; drive a company car,
      truck or van), the 2023 columns.

Suppression [A]. Stats NZ shows every count below 6 as -999 (no zero appears in the table) and randomly
rounds the others to base 3. A suppressed cell of a residence x workplace pair whose total
(2023_Total_stated) is shown receives part of the pair's residual (total minus its shown cells), split
over the pair's suppressed cells in proportion to the mode shares of the shown cells of all
outside-to-cordon pairs and capped at ``prep.od_suppressed_cap`` (5) per cell. A pair whose total is
suppressed too (1 to 5 commuters) is given a total of ``prep.od_suppressed_total`` (3), split the same
way. Driver counts are then summed over the cordon workplaces of each residence SA2.

Outputs (out_dir, default run.data_dir):
    od_sa2.csv     one row per residence SA2 with drivers: sa2_code, sa2_name, x_nztm, y_nztm
                   (representative point of the SA2 polygon), drivers_shown, drivers_imputed,
                   drivers_to_cordon (= shown + imputed; the origin weight prep.build_inputs reads),
                   commuters_shown (shown Total_stated, all modes)
    od_report.md   totals, suppression, unmatched SA2s, distance bands

Public API:
    load_od(cfg) -> pd.DataFrame                       # raw table, renamed columns
    cordon_sa2(sa2, cordon) -> set[str]
    impute_pairs(pairs, modes, shares, cap, total_if_suppressed) -> pd.DataFrame
    build_od(cfg) -> tuple[pd.DataFrame, dict]
    main(argv=None) -> int
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry.base import BaseGeometry

from cordonlite.config import Config, load_config
from prep.build_inputs import load_cordon

SUPPRESSED = -999
TOTAL_COL = "2023_Total_stated"
OD_COLUMNS: tuple[str, ...] = ("sa2_code", "sa2_name", "x_nztm", "y_nztm", "drivers_shown",
                               "drivers_imputed", "drivers_to_cordon", "commuters_shown")


def load_od(cfg: Config) -> pd.DataFrame:
    """The Census table with res / work / res_name / work_name columns (codes as strings)."""
    od = pd.read_csv(cfg.resolve_path(cfg.prep.census_od_csv),
                     dtype={"SA22023_V1_00_usual_residence_address": str,
                            "SA22023_V1_00_workplace_address": str})
    return od.rename(columns={
        "SA22023_V1_00_usual_residence_address": "res", "SA22023_V1_00_workplace_address": "work",
        "SA22023_V1_00_NAME_ASCII_usual_residence_address": "res_name",
        "SA22023_V1_00_NAME_ASCII_workplace_address": "work_name"})


def load_sa2(cfg: Config) -> gpd.GeoDataFrame:
    """SA2 polygons with ``code`` and ``name`` columns, in the prep CRS."""
    p = cfg.prep
    sa2 = gpd.read_file(cfg.resolve_path(p.sa2_gpkg)).to_crs(epsg=p.crs_epsg)
    sa2["code"] = sa2[p.sa2_code_field].astype(str)
    sa2["name"] = sa2[p.sa2_name_field].astype(str)
    return sa2


def cordon_sa2(sa2: gpd.GeoDataFrame, cordon: BaseGeometry) -> set[str]:
    """Codes of the SA2s whose representative point lies inside the cordon."""
    return set(sa2.loc[sa2.geometry.representative_point().within(cordon), "code"])


def mode_columns(od: pd.DataFrame) -> list[str]:
    """The 2023 mode columns, Total_stated excluded."""
    return [c for c in od.columns if c.startswith("2023_") and c != TOTAL_COL]


def _allocate(residual: float, weights: np.ndarray, cap: float) -> np.ndarray:
    """Split ``residual`` over cells in proportion to ``weights``, each at most ``cap``; what a capped
    cell cannot take goes to the others, so the result sums to min(residual, cap x cells with weight)."""
    out = np.zeros(len(weights))
    free = weights > 0
    left = float(residual)
    while left > 1e-9 and free.any():
        w = np.where(free, weights, 0.0)
        add = left * w / w.sum()
        room = cap - out
        take = np.minimum(add, room)
        out += take
        left -= float(take.sum())
        free &= (cap - out) > 1e-9
    return out


def impute_pairs(pairs: pd.DataFrame, modes: Sequence[str], shares: pd.Series, cap: float,
                 total_if_suppressed: float) -> pd.DataFrame:
    """Mode counts of every pair with its suppressed cells filled (see the module docstring)."""
    shown = pairs[list(modes)].to_numpy(dtype=float)
    supp = shown == SUPPRESSED
    known = np.where(supp, 0.0, shown)
    total = pairs[TOTAL_COL].to_numpy(dtype=float)
    w = shares.reindex(list(modes)).fillna(0.0).to_numpy(dtype=float)
    filled = known.copy()
    for i in np.flatnonzero(supp.any(axis=1)):
        t = total_if_suppressed if total[i] == SUPPRESSED else total[i]
        resid = max(0.0, t - known[i].sum())
        filled[i, supp[i]] = _allocate(resid, w[supp[i]], cap)
    return pd.DataFrame(filled, columns=list(modes), index=pairs.index)


def build_od(cfg: Config) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Drivers into the cordon by residence SA2, and statistics for the report."""
    p = cfg.prep
    cordon = load_cordon(cfg)
    sa2 = load_sa2(cfg)
    od = load_od(cfg)
    cbd = cordon_sa2(sa2, cordon)
    modes = mode_columns(od)
    missing = [m for m in p.od_modes if m not in modes]
    if missing:
        raise ValueError(f"prep.od_modes not in the Census table: {missing}")
    pairs = od[od["work"].isin(cbd) & ~od["res"].isin(cbd)].copy()
    shown = pairs[modes].where(pairs[modes] != SUPPRESSED, 0)
    shares = shown.sum() / shown.to_numpy().sum()
    filled = impute_pairs(pairs, modes, shares, p.od_suppressed_cap, p.od_suppressed_total)
    drv_cols = list(p.od_modes)
    pairs["drivers_shown"] = shown[drv_cols].sum(axis=1)
    pairs["drivers_to_cordon"] = filled[drv_cols].sum(axis=1)
    pairs["commuters_shown"] = pairs[TOTAL_COL].where(pairs[TOTAL_COL] != SUPPRESSED, 0)
    by = pairs.groupby("res").agg(sa2_name=("res_name", "first"), drivers_shown=("drivers_shown", "sum"),
                                  drivers_to_cordon=("drivers_to_cordon", "sum"),
                                  commuters_shown=("commuters_shown", "sum"))
    by = by[by["drivers_to_cordon"] > 0]
    pt = sa2.set_index("code").geometry.representative_point()
    located = by.index.isin(pt.index)
    unmatched = by[~located]
    by = by[located].copy()
    by["x_nztm"] = pt.reindex(by.index).x.round(1)
    by["y_nztm"] = pt.reindex(by.index).y.round(1)
    by["drivers_imputed"] = by["drivers_to_cordon"] - by["drivers_shown"]
    by = by.reset_index().rename(columns={"res": "sa2_code"})
    for c in ("drivers_shown", "drivers_imputed", "drivers_to_cordon", "commuters_shown"):
        by[c] = by[c].round(3)
    by = by.sort_values("sa2_code").reset_index(drop=True)[list(OD_COLUMNS)]

    cx, cy = cordon.centroid.x, cordon.centroid.y
    km = np.hypot(by["x_nztm"] - cx, by["y_nztm"] - cy) / 1000.0
    bands = pd.cut(km, [0, 5, 10, 15, 20, 30, 50, 1000])
    supp_pairs = pairs[TOTAL_COL] == SUPPRESSED
    stats = {
        "n_cbd_sa2": len(cbd), "cbd_names": sorted(sa2.loc[sa2["code"].isin(cbd), "name"]),
        "n_pairs": len(pairs), "n_pairs_total_suppressed": int(supp_pairs.sum()),
        "n_driver_cells": len(pairs) * len(drv_cols),
        "n_driver_cells_suppressed": int((pairs[drv_cols] == SUPPRESSED).to_numpy().sum()),
        "shares": shares, "drv_cols": drv_cols,
        "by_mode_shown": shown.sum(), "by_mode_filled": filled.sum(),
        "commuters_shown": float(pairs["commuters_shown"].sum()),
        "drivers_shown": float(pairs["drivers_shown"].sum()),
        "drivers_filled": float(pairs["drivers_to_cordon"].sum()),
        "drivers_filled_from_total_suppressed": float(pairs.loc[supp_pairs, "drivers_to_cordon"].sum()),
        "unmatched": unmatched, "n_sa2": len(by),
        "by_band": by.groupby(bands, observed=False)["drivers_to_cordon"].sum(),
    }
    return by, stats


def render_report(cfg: Config, by: pd.DataFrame, st: dict[str, Any]) -> str:
    """Markdown report of the Census OD step."""
    p = cfg.prep
    L = ["# Cordon-Lite Census OD report", "",
         "Source: Stats NZ, 2023 Census main means of travel to work by statistical area 2 "
         f"(`{p.census_od_csv}`), SA2 polygons `{p.sa2_gpkg}` (codes `{p.sa2_code_field}`). "
         "Licensed CC BY 4.0 by Stats NZ.", "",
         "## Definitions", "",
         f"- Workplace SA2s in the cordon ({st['n_cbd_sa2']}): " + ", ".join(st["cbd_names"]) + ".",
         "- Commuters: usual residence outside the cordon, workplace in the cordon.",
         "- Drivers: " + " + ".join(f"`{c}`" for c in st["drv_cols"]) + ".",
         f"- Suppressed cells (-999, a count of 0 to 5): the pair's residual (Total_stated minus shown cells) "
         f"split by the outside-to-cordon mode shares of the shown cells, at most {p.od_suppressed_cap:g} per "
         f"cell; a pair whose total is suppressed is given {p.od_suppressed_total:g} commuters [A].", "",
         "## Totals", "",
         f"- Residence x workplace pairs: {st['n_pairs']}; with the total suppressed: "
         f"{st['n_pairs_total_suppressed']}.",
         f"- Driver cells: {st['n_driver_cells']}, suppressed: {st['n_driver_cells_suppressed']}.",
         f"- Commuters, shown totals: {st['commuters_shown']:.0f}.",
         f"- Drivers, shown cells only (a lower bound): {st['drivers_shown']:.0f}.",
         f"- Drivers with suppressed cells filled: {st['drivers_filled']:.0f} "
         f"({st['drivers_filled'] - st['drivers_shown']:.0f} imputed, of which "
         f"{st['drivers_filled_from_total_suppressed']:.0f} in pairs whose total is suppressed).",
         f"- Residence SA2s with drivers and a polygon: {st['n_sa2']}, drivers "
         f"{by['drivers_to_cordon'].sum():.0f}.",
         f"- Residence SA2s with drivers but no polygon in `{p.sa2_gpkg}` (dropped): "
         f"{len(st['unmatched'])}, drivers {st['unmatched']['drivers_to_cordon'].sum():.1f}"
         + (" (" + ", ".join(f"{r.sa2_name} {r.drivers_to_cordon:.1f}"
                             for r in st["unmatched"].itertuples()) + ")" if len(st["unmatched"]) else "")
         + ".",
         f"- For comparison, `engine.agents_represented` = {cfg.engine.agents_represented:.0f} cars entering "
         "in the charged morning hours (AT/AC option 1a): the Census table has no time of day, so it counts "
         "drivers to a cordon workplace whenever they travel.", "",
         "## Commuters by mode (outside to cordon)", "",
         "| mode | shown | with suppressed cells filled | share of shown |", "|---|---|---|---|"]
    for m in st["by_mode_shown"].index:
        L.append(f"| {m.removeprefix('2023_')} | {st['by_mode_shown'][m]:.0f} | {st['by_mode_filled'][m]:.0f} | "
                 f"{st['shares'][m]:.3f} |")
    L += ["", "## Drivers by crow-fly distance from the cordon centroid", "",
          "| km | drivers | share |", "|---|---|---|"]
    tot = float(st["by_band"].sum())
    for band, v in st["by_band"].items():
        L.append(f"| {band.left:g}-{band.right:g} | {v:.0f} | {v / tot:.1%} |")
    L += ["", "Top 15 residence SA2s by drivers:", "", "| SA2 | name | drivers (shown) | drivers |",
          "|---|---|---|---|"]
    for r in by.sort_values("drivers_to_cordon", ascending=False).head(15).itertuples():
        L.append(f"| {r.sa2_code} | {r.sa2_name} | {r.drivers_shown:.0f} | {r.drivers_to_cordon:.1f} |")
    return "\n".join(L) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Cordon-Lite Census OD preparation")
    ap.add_argument("--config", default=None, help="path to config.toml")
    ap.add_argument("--out-dir", default=None, help="output folder (default: run.data_dir)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    out = Path(args.out_dir) if args.out_dir else cfg.resolve_path(cfg.run.data_dir)
    out.mkdir(parents=True, exist_ok=True)
    by, st = build_od(cfg)
    by.to_csv(out / "od_sa2.csv", index=False)
    (out / "od_report.md").write_text(render_report(cfg, by, st), encoding="utf-8")
    print(f"residence SA2s {len(by)}, drivers shown {st['drivers_shown']:.0f}, "
          f"with suppressed cells filled {st['drivers_filled']:.0f}, kept {by['drivers_to_cordon'].sum():.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
