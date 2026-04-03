import requests

cap_url = "https://data.linz.govt.nz/services;key=fcef26216c464b36838abf21777e793c/wfs/layer-101290/?service=WFS&request=GetCapabilities"
params = {"service": "WFS", "request": "GetCapabilities"}

resp = requests.get(cap_url, params=params, timeout=60)
print("Status:", resp.status_code)
print("Content-Type:", resp.headers.get("Content-Type"))
print(resp.text[:300])

with open("wfs_capabilities.xml", "w", encoding="utf-8") as f:
    f.write(resp.text)


import xml.etree.ElementTree as ET
import pandas as pd

tree = ET.parse("wfs_capabilities.xml")
root = tree.getroot()

def local(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag

# Find FeatureTypeList regardless of namespace
ft_list = None
for el in root.iter():
    if local(el.tag) == "FeatureTypeList":
        ft_list = el
        break

if ft_list is None:
    raise ValueError("Could not find FeatureTypeList in capabilities XML")

layers = []
for ft in ft_list:
    if local(ft.tag) != "FeatureType":
        continue

    name = title = default_crs = None
    bbox = None

    for child in ft:
        t = local(child.tag)
        if t == "Name":
            name = (child.text or "").strip()
        elif t == "Title":
            title = (child.text or "").strip()
        elif t in ["DefaultCRS", "DefaultSRS", "SRS"]:
            default_crs = (child.text or "").strip()
        elif t in ["WGS84BoundingBox", "LatLongBoundingBox", "BoundingBox"]:
            # Try to capture any bbox metadata
            bbox = ET.tostring(child, encoding="unicode")

    layers.append({
        "name": name,
        "title": title,
        "default_crs": default_crs,
        "bbox_raw": bbox
    })

df = pd.DataFrame(layers).dropna(subset=["name"]).sort_values("name")
print(df[["name", "title", "default_crs"]].head(30))
print("Total layers:", len(df))


import geopandas as gpd

# Auckland CBD approximate bounding box (EPSG:4326 - WGS84)
bbox = "174.74,-36.86,174.78,-36.84"

# Include API key in the base URL
base_url = "https://data.linz.govt.nz/services;key=fcef26216c464b36838abf21777e793c/wfs/layer-101290/"

params = {
    "service": "WFS",
    "version": "2.0.0",
    "request": "GetFeature",
    "typeNames": "data.linz.govt.nz:layer-101290",
    "outputFormat": "application/json",
    "srsName": "EPSG:4326",
    "bbox": bbox
}

response = requests.get(base_url, params=params)
response.raise_for_status()

# Save the GeoJSON response
with open("auckland_cbd_buildings.geojson", "w") as f:
    f.write(response.text)

# Load into geopandas
buildings = gpd.read_file("auckland_cbd_buildings.geojson")
buildings

df.to_csv("wfs_layers.csv", index=False)



# Auckland CBD approximate bounding box (EPSG:4326 - WGS84)
# Roughly bounded by waterfront, Symonds St, Mayoral Drive, Freemans Bay
# Your corner coordinates
corners = [
    (174.7509714, -36.83631523),   # top left
    (174.7895860, -36.83734080),   # top right
    (174.7492335, -36.85990188),   # bottom left
    (174.7870022, -36.86440114)    # bottom right
]

# Calculate bounding box envelope
lons = [c[0] for c in corners]
lats = [c[1] for c in corners]
minx, maxx = min(lons), max(lons)
miny, maxy = min(lats), max(lats)

print(f"Bounding box: {minx},{miny},{maxx},{maxy}")

# Fetch buildings
base_url = "https://data.linz.govt.nz/services;key=fcef26216c464b36838abf21777e793c/wfs/layer-101290/"
params = {
    "service": "WFS",
    "version": "2.0.0",
    "request": "GetFeature",
    "typeNames": "data.linz.govt.nz:layer-101290",
    "outputFormat": "application/json",
    "bbox": f"{minx},{miny},{maxx},{maxy},EPSG:4326"
}

response = requests.get(base_url, params=params)
response.raise_for_status()

buildings = gpd.GeoDataFrame.from_features(response.json()['features'])
buildings.set_crs("EPSG:2193", inplace=True)  # NZTM projection

print(f"Downloaded {len(buildings)} buildings")
buildings.plot(figsize=(10, 10))


# Load the SA3 CBD boundary
cbd_boundary = gpd.read_file("SA3_CBD.shp")
cbd_boundary.head()# Load the buildings

# Check the CRS and columns
print("CRS:", cbd_boundary.crs)
print("\nColumns:", cbd_boundary.columns.tolist())

# Clip buildings to the CBD boundary
buildings_clipped = gpd.clip(buildings, cbd_boundary)

print(f"Clipped building count: {len(buildings_clipped)}")

# Save the clipped result
#buildings_clipped.to_file("auckland_cbd_buildings_clipped.shp", driver="shp")

buildings_clipped.to_file("auckland_cbd_buildings_clipped.shp")



