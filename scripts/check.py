"""Spot-check 7 facilities against the published raster. Usage: python scripts/check.py"""
import json, os
import rasterio

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
fs = json.load(open(os.path.join(D, "facilities.geojson")))["features"]
s = json.load(open(os.path.join(D, "summary.json")))
assert len(fs) == s["analysed"] == 428 and s["dropped"] == 1
by = {f["properties"]["name"]: f for f in fs}
assert "KD KEPALA BATAS" not in by
fixed = [by["KK PINTU GENG"], by["KD DALAM RHU"]]
assert fixed[0]["geometry"]["coordinates"] == [102.2305135, 6.1016354] and fixed[0]["properties"]["district"] == "Kota Bharu"
assert fixed[1]["properties"]["coord_source"].startswith("adjusted") and fixed[1]["properties"]["district"] == "Pasir Puteh"
inside = [f for f in fs if f["properties"]["in_flood"]]
near = sorted((f for f in fs if not f["properties"]["in_flood"]), key=lambda f: f["properties"]["dist_m"])
far = sorted(fs, key=lambda f: -f["properties"]["dist_m"])
sample = inside[:1] + near[:2] + far[:2] + fixed
with rasterio.open(os.path.join(D, "flood_extent_gfm_2024.tif")) as r:
    for f in sample:
        p, (lon, lat) = f["properties"], f["geometry"]["coordinates"]
        v = next(r.sample([(lon, lat)]))[0]
        assert (v == 1) == p["in_flood"], p
        assert p["within_500m"] == (p["dist_m"] <= 500), p
        assert p["in_flood"] or p["dist_m"] > 0, p
        print(f"ok {p['name']:<40} pixel={v} dist={p['dist_m']}m")
print("all checks passed")
