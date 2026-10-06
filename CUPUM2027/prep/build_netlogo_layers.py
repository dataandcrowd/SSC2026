"""NetLogo map layers (run once): TomTom roads as a shapefile, cordon and city-centre buildings.

Owner: prep builder. See INTERFACES.md. Neither Cordon-Lite engine reads these files, so they never
change a run. The GUI of netlogo7/cordon_lite.nlogox loads them (Cordon-Lite cars driving on the
TomTom network).

    python -m prep.build_netlogo_layers [--config config.toml] [--out-dir netlogo7/gis]
                                        [--roads-out PATH] [--buildings PATH]

Outputs, all EPSG:2193 (NZTM2000): shapefiles (.prj, UTF-8 .cpg) and one CSV. The .dbf header date is
fixed (DBF_DATE), so a rerun reproduces every file byte for byte:
  in --out-dir (default netlogo7/gis):
    tomtom_major_roads.shp   prep.roads_gpkg (layer prep.roads_layer) as a shapefile: every
                             segment, same order; attributes segment_id (TomTom newSegmentId; a
                             shapefile field name has at most 10 characters), speedLimit, frc,
                             streetName, distance (--roads-out writes it elsewhere)
    cordon.shp               the cordon polygon (load_cordon, the same geometry as data/cordon.geojson)
    cbd_buildings.shp        building footprints whose representative point lies inside the cordon
    cbd_buildings.csv        building_id, x_nztm, y_nztm, use: one row per footprint above; the point
                             is the footprint's representative point (always inside the footprint)

Public API:
    load_buildings(path, cfg) -> gpd.GeoDataFrame
    building_points(buildings, cordon) -> tuple[gpd.GeoDataFrame, pd.DataFrame]
    roads_for_shapefile(roads) -> gpd.GeoDataFrame
    build_layers(cfg, out_dir=None, buildings_path=None, roads_out=None) -> dict[str, Any]
    main(argv=None) -> int
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

from cordonlite.config import Config, load_config
from prep.build_inputs import inside_mask, load_cordon, load_roads

# Building footprints clipped to the SA3 "Auckland City Centre" polygon (LINZ building outlines,
# fetched by ../netlogo/Data/building_api/building_api.py). Relative to the config file folder.
DEFAULT_BUILDINGS = "../netlogo/Data/building_api/auckland_cbd_buildings_clipped.shp"
DEFAULT_OUT_DIR = "netlogo7/gis"

ROADS_SHP = "tomtom_major_roads.shp"
CORDON_SHP = "cordon.shp"
BUILDINGS_SHP = "cbd_buildings.shp"
BUILDINGS_CSV = "cbd_buildings.csv"
BUILDINGS_COLUMNS: tuple[str, ...] = ("building_id", "x_nztm", "y_nztm", "use")
# gpkg column -> shapefile field (at most 10 characters, so nothing is silently truncated)
ROAD_FIELDS: dict[str, str] = {
    "newSegmentId": "segment_id", "speedLimit": "speedLimit", "frc": "frc",
    "streetName": "streetName", "distance": "distance",
}
SHAPEFILE_SUFFIXES: tuple[str, ...] = (".shp", ".shx", ".dbf", ".prj", ".cpg")
DBF_DATE = "2026-10-06"   # last-update date written into every .dbf header (otherwise the run date)


def load_buildings(path: Path, cfg: Config) -> gpd.GeoDataFrame:
    """Building footprints in EPSG cfg.prep.crs_epsg; empty or null geometries dropped."""
    b = gpd.read_file(path)
    if b.crs is None:
        raise ValueError(f"{path} has no CRS (.prj missing)")
    if b.crs.to_epsg() != cfg.prep.crs_epsg:
        b = b.to_crs(epsg=cfg.prep.crs_epsg)
    b = b[b.geometry.notna() & ~b.geometry.is_empty].reset_index(drop=True)
    b["geometry"] = shapely.make_valid(b.geometry.values)
    return b


def building_points(buildings: gpd.GeoDataFrame,
                    cordon: BaseGeometry) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Footprints whose representative point is inside the cordon, and those points as a table.

    The id is the LINZ building_id ("building_i" in the clipped shapefile) when present and unique,
    otherwise the row number. A representative point lies inside its polygon, unlike a centroid
    of an L-shaped footprint.
    """
    pts = shapely.point_on_surface(buildings.geometry.values)
    xy = shapely.get_coordinates(pts)
    keep = inside_mask(cordon, xy)
    if not keep.any():
        raise ValueError("no building lies inside the cordon")
    ids = buildings["building_i"] if "building_i" in buildings.columns else pd.Series(range(len(buildings)))
    if not ids.is_unique:
        ids = pd.Series(range(len(buildings)))
    use = buildings["use"].fillna("Unknown").astype(str) if "use" in buildings.columns else "Unknown"
    table = pd.DataFrame({
        "building_id": ids.astype("int64").to_numpy(),
        "x_nztm": xy[:, 0].round(1),
        "y_nztm": xy[:, 1].round(1),
        "use": use,
    })[keep].reset_index(drop=True)[list(BUILDINGS_COLUMNS)]
    shp = gpd.GeoDataFrame({"building_i": table["building_id"].to_numpy(), "use": table["use"].to_numpy()},
                           geometry=buildings.geometry.values[keep], crs=buildings.crs)
    return shp, table


def roads_for_shapefile(roads: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The TomTom attributes renamed to shapefile-safe field names, segment order unchanged."""
    missing = [c for c in ROAD_FIELDS if c not in roads.columns]
    if missing:
        raise ValueError(f"roads layer lacks columns {missing}")
    out = roads[list(ROAD_FIELDS)].rename(columns=ROAD_FIELDS)
    return gpd.GeoDataFrame(out, geometry=roads.geometry.values, crs=roads.crs)


def _write_shapefile(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Shapefile with a UTF-8 .cpg; stale sidecar files of the same name are removed first.

    RESIZE shrinks each text field to its longest value (the .dbf of the roads halves in size).
    The fixed DBF_DATE_LAST_UPDATE keeps the file identical from one run to the next.
    """
    for suffix in SHAPEFILE_SUFFIXES:
        path.with_suffix(suffix).unlink(missing_ok=True)
    gdf.to_file(path, driver="ESRI Shapefile", engine="pyogrio", encoding="UTF-8",
                layer_options={"RESIZE": "YES", "DBF_DATE_LAST_UPDATE": DBF_DATE})


def build_layers(cfg: Config, out_dir: Path | None = None, buildings_path: Path | None = None,
                 roads_out: Path | None = None) -> dict[str, Any]:
    """Write the roads shapefile and the three Cordon-Lite layers; returns counts and extent."""
    out_dir = out_dir or cfg.resolve_path(DEFAULT_OUT_DIR)
    buildings_path = buildings_path or cfg.resolve_path(DEFAULT_BUILDINGS)
    roads_out = roads_out or out_dir / ROADS_SHP
    out_dir.mkdir(parents=True, exist_ok=True)
    crs = f"EPSG:{cfg.prep.crs_epsg}"

    roads = roads_for_shapefile(load_roads(cfg))
    _write_shapefile(roads, roads_out)

    cordon = load_cordon(cfg)
    _write_shapefile(gpd.GeoDataFrame({"name": [";".join(cfg.prep.cordon_names)]}, geometry=[cordon], crs=crs),
                     out_dir / CORDON_SHP)

    buildings = load_buildings(buildings_path, cfg)
    shp, table = building_points(buildings, cordon)
    _write_shapefile(shp, out_dir / BUILDINGS_SHP)
    table.to_csv(out_dir / BUILDINGS_CSV, index=False)

    return {
        "out_dir": out_dir, "roads_out": roads_out, "n_segments": len(roads),
        "roads_bounds": tuple(float(v) for v in roads.total_bounds.round(1)),
        "frc_counts": {int(k): int(v) for k, v in roads["frc"].value_counts().sort_index().items()},
        "n_buildings_read": len(buildings), "n_buildings_in": len(table),
        "cordon_area_km2": round(cordon.area / 1e6, 3),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="NetLogo layers: TomTom roads shapefile, cordon and city-centre "
                                             "buildings")
    ap.add_argument("--config", default=None, help="path to config.toml")
    ap.add_argument("--out-dir", default=None, help=f"output folder (default: {DEFAULT_OUT_DIR})")
    ap.add_argument("--buildings", default=None, help=f"building footprints (default: {DEFAULT_BUILDINGS})")
    ap.add_argument("--roads-out", default=None,
                    help=f"roads shapefile (default: {ROADS_SHP} in --out-dir)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    st = build_layers(cfg, Path(args.out_dir) if args.out_dir else None,
                      Path(args.buildings) if args.buildings else None,
                      Path(args.roads_out) if args.roads_out else None)
    print(f"wrote {st['roads_out']} and {st['out_dir']}")
    print(f"roads: {st['n_segments']} segments, frc {st['frc_counts']}, bounds {st['roads_bounds']}")
    print(f"cordon: {st['cordon_area_km2']} km2; buildings inside the cordon: {st['n_buildings_in']} "
          f"of {st['n_buildings_read']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
