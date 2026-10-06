"""prep/build_netlogo_layers.py on toy inputs (no real data, no NetLogo)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import pytest
import shapely
from shapely.geometry import LineString, Polygon, box

from cordonlite.config import load_config
from prep import build_netlogo_layers as bl

CRS = "EPSG:2193"
CORDON = box(1000.0, 1000.0, 2000.0, 2000.0)


def _toy_inputs(d: Path) -> dict[str, Path]:
    """Roads GeoPackage (layer tomtom), SA3 GeoPackage and a building shapefile."""
    roads = gpd.GeoDataFrame({
        "newSegmentId": ["-0000a-1", "-0000a-2", "-0000a-3"],
        "speedLimit": [50, 80, 30],
        "frc": [3, 0, 4],
        "streetName": ["Queen Street", "Southern Motorway", None],
        "distance": [500.0, 1200.0, 80.0],
    }, geometry=[LineString([(0, 0), (500, 0)]), LineString([(500, 0), (1500, 700), (1500, 1500)]),
                 LineString([(1500, 1500), (1580, 1500)])], crs=CRS)
    roads.to_file(d / "roads.gpkg", layer="tomtom", driver="GPKG")
    sa3 = gpd.GeoDataFrame({"SA32025_V1_00_NAME": ["Auckland City Centre", "Elsewhere"]},
                           geometry=[CORDON, box(3000, 3000, 4000, 4000)], crs=CRS)
    sa3.to_file(d / "sa3.gpkg", driver="GPKG")
    # an L-shaped footprint whose centroid lies outside it, one square inside, one outside the cordon
    ell = Polygon([(1100, 1100), (1400, 1100), (1400, 1150), (1150, 1150), (1150, 1400), (1100, 1400)])
    blds = gpd.GeoDataFrame({"building_i": [11, 12, 13], "use": ["Unknown", None, "School"]},
                            geometry=[ell, box(1500, 1500, 1520, 1530), box(2500, 2500, 2520, 2520)], crs=CRS)
    blds.to_file(d / "blds.shp")
    return {"roads": d / "roads.gpkg", "sa3": d / "sa3.gpkg", "blds": d / "blds.shp"}


@pytest.fixture
def built(tmp_path: Path) -> dict:
    src = _toy_inputs(tmp_path)
    cfg = load_config(overrides={"prep.roads_gpkg": str(src["roads"]), "prep.cordon_gpkg": str(src["sa3"])})
    out = tmp_path / "gis"
    stats = bl.build_layers(cfg, out_dir=out, buildings_path=src["blds"], roads_out=tmp_path / "roads.shp")
    return {"stats": stats, "out": out, "roads_shp": tmp_path / "roads.shp", "src": src}


def test_roads_shapefile_is_a_faithful_copy(built: dict) -> None:
    src = gpd.read_file(built["src"]["roads"], layer="tomtom")
    shp = gpd.read_file(built["roads_shp"])
    assert shp.crs.to_epsg() == 2193
    assert list(shp.columns) == ["segment_id", "speedLimit", "frc", "streetName", "distance", "geometry"]
    assert shp.geometry.geom_equals_exact(src.geometry, tolerance=1e-9).all()     # same order, same lines
    assert shp["segment_id"].tolist() == src["newSegmentId"].tolist()
    assert shp["speedLimit"].tolist() == [50, 80, 30] and shp["frc"].tolist() == [3, 0, 4]
    assert shp["streetName"].fillna("").tolist() == ["Queen Street", "Southern Motorway", ""]
    assert shp["distance"].tolist() == [500.0, 1200.0, 80.0]
    assert all(len(f) <= 10 for f in pyogrio.read_info(built["roads_shp"])["fields"])
    assert built["roads_shp"].with_suffix(".cpg").read_text().strip().upper() in {"UTF-8", "UTF8"}
    assert built["stats"]["n_segments"] == 3
    assert built["stats"]["frc_counts"] == {0: 1, 3: 1, 4: 1}


def test_default_roads_shapefile_goes_to_the_layer_folder(tmp_path: Path) -> None:
    src = _toy_inputs(tmp_path)
    cfg = load_config(overrides={"prep.roads_gpkg": str(src["roads"]), "prep.cordon_gpkg": str(src["sa3"])})
    st = bl.build_layers(cfg, out_dir=tmp_path / "gis", buildings_path=src["blds"])
    assert st["roads_out"] == tmp_path / "gis" / "tomtom_major_roads.shp"
    assert (tmp_path / "gis" / "tomtom_major_roads.shp").exists()


def test_cordon_shapefile_is_the_named_sa3(built: dict) -> None:
    cor = gpd.read_file(built["out"] / bl.CORDON_SHP)
    assert len(cor) == 1 and cor.crs.to_epsg() == 2193
    assert cor.geometry.iloc[0].symmetric_difference(CORDON).area < 1e-6


def test_buildings_inside_the_cordon_with_points_inside_footprints(built: dict) -> None:
    table = pd.read_csv(built["out"] / bl.BUILDINGS_CSV)
    assert list(table.columns) == list(bl.BUILDINGS_COLUMNS)
    assert table["building_id"].tolist() == [11, 12]                  # 13 is outside the cordon
    assert table["use"].tolist() == ["Unknown", "Unknown"]
    foot = gpd.read_file(built["out"] / bl.BUILDINGS_SHP)
    assert foot["building_i"].tolist() == [11, 12] and foot.crs.to_epsg() == 2193
    pts = shapely.points(table["x_nztm"], table["y_nztm"])
    assert shapely.contains(foot.geometry.values, pts).all()           # even for the L shape
    assert not foot.geometry.iloc[0].contains(foot.geometry.iloc[0].centroid)
    assert built["stats"]["n_buildings_in"] == 2 and built["stats"]["n_buildings_read"] == 3


def test_rerun_replaces_the_previous_files(built: dict) -> None:
    cfg = load_config(overrides={"prep.roads_gpkg": str(built["src"]["roads"]),
                                 "prep.cordon_gpkg": str(built["src"]["sa3"])})
    bl.build_layers(cfg, out_dir=built["out"], buildings_path=built["src"]["blds"], roads_out=built["roads_shp"])
    assert len(gpd.read_file(built["roads_shp"])) == 3
    assert len(pd.read_csv(built["out"] / bl.BUILDINGS_CSV)) == 2


def test_no_building_inside_raises() -> None:
    far = gpd.GeoDataFrame({"building_i": [1]}, geometry=[box(5000, 5000, 5010, 5010)], crs=CRS)
    with pytest.raises(ValueError, match="no building"):
        bl.building_points(far, CORDON)


def test_roads_missing_columns_raise() -> None:
    roads = gpd.GeoDataFrame({"frc": [1]}, geometry=[LineString([(0, 0), (1, 1)])], crs=CRS)
    with pytest.raises(ValueError, match="lacks columns"):
        bl.roads_for_shapefile(roads)
