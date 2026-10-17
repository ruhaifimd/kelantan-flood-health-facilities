"""Kelantan health facilities x observed flood extent (Copernicus GFM, Nov-Dec 2024).

Usage:  python scripts/pipeline.py [cache_dir]
Writes everything under data/. Re-runnable; downloads are cached in cache_dir.
"""
import csv, io, json, os, sys, urllib.request
from collections import Counter, defaultdict

import numpy as np
import geopandas as gpd
import rasterio
import shapely
from pyproj import Transformer
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import reproject, calculate_default_transform

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, ".cache")

MOH_COMMIT = "f79256f50f0da205c364072e39e2f2f0fabc7478"  # facilities_master.csv, snapshot 31 Dec 2025
MOH_URL = f"https://raw.githubusercontent.com/MoH-Malaysia/data-resources-public/{MOH_COMMIT}/facilities_master.csv"
GB_URL = "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/MYS/ADM2/geoBoundaries-MYS-ADM2.geojson"
KELANTAN_ADM2 = ["Tumpat", "Kota Bharu", "Bachok", "Pasir Mas", "Pasir Puteh", "Tanah Merah", "Machang",
                 "Jeli", "Kuala Krai", "Gua Musang", "Kecil Lojing"]
GFM_STAC = "https://stac.eodc.eu/api/v1"
EVENT = "2024-11-25/2024-12-20"  # main Kelantan wave (late Nov) + 11 Dec wave
RES = 0.0002                      # ~22 m analysis grid, EPSG:4326 (GFM native is 20 m Equi7)
NEAR_M = 500
METRIC = "EPSG:3375"              # GDM2000 / Peninsula RSO

GROUPS = {"HOSPITAL": "Hospital", "KLINIK KESIHATAN": "Klinik Kesihatan", "KLINIK KOMUNITI": "Klinik Kesihatan",
          "KLINIK DESA": "Klinik Desa"}


def group(row):
    if row["KATEGORI_FASILITI"] in ("KLINIK PERGIGIAN", "PEJABAT KESIHATAN PERGIGIAN"):
        return "Dental"
    return GROUPS.get(row["JENIS_FASILITI"], GROUPS.get(row["KATEGORI_FASILITI"], "Other (office, lab, etc.)"))


def fetch(url, name):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, name)
    if not os.path.exists(p):
        urllib.request.urlretrieve(url, p)
    return p


def flood_union(bounds):
    """Max observed flood extent = any GFM ensemble pixel == 1 in the event window."""
    out = os.path.join(CACHE, "gfm_union.tif")
    w, s, e, n = bounds
    W, H = int(round((e - w) / RES)), int(round((n - s) / RES))
    T = from_origin(w, n, RES, RES)
    items = sorted(Client.open(GFM_STAC).search(collections=["GFM"], bbox=list(bounds), datetime=EVENT).items(),
                   key=lambda i: i.id)
    with open(os.path.join(DATA, "gfm_scenes.csv"), "w", newline="") as f:
        csv.writer(f).writerows([["item_id", "datetime", "flooded_pixels_in_tile"]] +
                                [[i.id, i.properties["datetime"], i.properties.get("flooded_pixels")] for i in items])
    if os.path.exists(out):
        with rasterio.open(out) as r:
            return r.read(1), r.read(2), T
    flood = np.zeros((H, W), bool)
    obs = np.zeros((H, W), bool)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4"):
        for k, it in enumerate(items):
            with rasterio.open(it.assets["ensemble_flood_extent"].href) as src, \
                 WarpedVRT(src, crs="EPSG:4326", transform=T, width=W, height=H,
                           resampling=Resampling.nearest, nodata=255) as v:
                a = v.read(1)
            flood |= a == 1
            obs |= a <= 1   # 0/1 = valid observation; 255 = no data / GFM exclusion mask
            print(f"  {k + 1}/{len(items)} {it.id} flooded={int((a == 1).sum())}")
    with rasterio.open(out, "w", driver="GTiff", width=W, height=H, count=2, dtype="uint8", crs="EPSG:4326",
                       transform=T, compress="deflate") as d:
        d.write(flood.astype("uint8"), 1)
        d.write(obs.astype("uint8"), 2)
    return flood.astype("uint8"), obs.astype("uint8"), T


def main():
    os.makedirs(DATA, exist_ok=True)
    # --- boundaries (geoBoundaries ADM2, full resolution) ---
    adm2 = gpd.read_file(fetch(GB_URL, "geoBoundaries-MYS-ADM2.geojson"))
    kel = adm2[adm2.shapeName.isin(KELANTAN_ADM2)][["shapeName", "geometry"]]
    assert len(kel) == 11, kel.shapeName.tolist()
    state = shapely.union_all(kel.geometry.values)
    w, s, e, n = state.bounds
    bounds = (round(w - 0.01, 4), round(s - 0.01, 4), round(e + 0.01, 4), round(n + 0.01, 4))
    kel.assign(geometry=kel.geometry.simplify(0.0003)).to_file(os.path.join(DATA, "districts.geojson"),
                                                              driver="GeoJSON", COORDINATE_PRECISION=5)

    # --- facilities ---
    text = open(fetch(MOH_URL, "facilities_master.csv"), encoding="utf-8-sig").read()
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r["NEGERI"] == "KELANTAN"]
    print("Kelantan rows:", len(rows))
    keep, dropped = [], []
    for r in rows:
        lat, lon = float(r["LATITUD"]), float(r["LONGITUD"])
        if not state.covers(shapely.Point(lon, lat)):
            dropped.append([r["KOD_FASILITI"], r["NAMA"], r["DAERAH"], lat, lon, "outside Kelantan boundary"])
            continue
        keep.append(r)
    with open(os.path.join(DATA, "dropped.csv"), "w", newline="") as f:
        csv.writer(f).writerows([["code", "name", "district", "lat", "lon", "reason"]] + dropped)
    print("dropped:", len(dropped))

    # --- flood extent ---
    flood, obs, T = flood_union(bounds)
    with rasterio.open(os.path.join(DATA, "flood_extent_gfm_2024.tif"), "w", driver="GTiff",
                       width=flood.shape[1], height=flood.shape[0], count=1, dtype="uint8", crs="EPSG:4326",
                       transform=T, compress="deflate", predictor=2, nodata=255) as d:
        d.write(np.where(flood == 1, 1, np.where(obs == 1, 0, 255)).astype("uint8"), 1)

    # --- exposure: point-in-pixel + distance to nearest flooded pixel centre ---
    tr = Transformer.from_crs("EPSG:4326", METRIC, always_xy=True)
    rr, cc = np.nonzero(flood)
    fx, fy = tr.transform(T.c + (cc + 0.5) * RES, T.f - (rr + 0.5) * RES)
    tree = shapely.STRtree(shapely.points(fx, fy))
    feats = []
    for r in keep:
        lat, lon = float(r["LATITUD"]), float(r["LONGITUD"])
        row, col = int((T.f - lat) // RES), int((lon - T.c) // RES)
        inside = bool(flood[row, col])
        px, py = tr.transform(lon, lat)
        p = shapely.Point(px, py)
        _, dist = tree.query_nearest(p, return_distance=True)
        dist_m = 0 if inside else int(round(float(dist[0])))
        district = r["DAERAH"].replace("JAJAHAN ", "").title()
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {
            "code": r["KOD_FASILITI"], "name": r["NAMA"], "group": group(r), "type": r["JENIS_FASILITI"],
            "district": district, "in_flood": inside, "dist_m": dist_m, "within_500m": dist_m <= NEAR_M,
            "observed": bool(obs[row, col]), "coord_dp": min(len(r["LATITUD"].split(".")[-1]),
                                                             len(r["LONGITUD"].split(".")[-1]))}})
    json.dump({"type": "FeatureCollection", "features": feats},
              open(os.path.join(DATA, "facilities.geojson"), "w"), ensure_ascii=False, separators=(",", ":"))

    # --- district summary ---
    groups = ["Hospital", "Klinik Kesihatan", "Klinik Desa", "Dental", "Other (office, lab, etc.)"]
    agg = defaultdict(Counter)
    for f in feats:
        p = f["properties"]
        for d in (p["district"], "KELANTAN (all)"):
            a = agg[d]
            a["total"] += 1; a[p["group"]] += 1
            a["in_flood"] += p["in_flood"]; a["within_500m"] += p["within_500m"]
            a["not_observed"] += not p["observed"]
    cols = ["district", "total"] + groups + ["in_flood", "pct_in_flood", "within_500m", "pct_within_500m",
                                             "not_observed"]
    with open(os.path.join(DATA, "district_summary.csv"), "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(cols)
        for d in sorted(agg, key=lambda d: (d.startswith("KELANTAN"), -agg[d]["within_500m"] / agg[d]["total"])):
            a = agg[d]
            wr.writerow([d, a["total"]] + [a[g] for g in groups] +
                        [a["in_flood"], round(100 * a["in_flood"] / a["total"], 1),
                         a["within_500m"], round(100 * a["within_500m"] / a["total"], 1), a["not_observed"]])

    # --- web overlay: flood pixels as RGBA PNG in Web Mercator ---
    src_t = T
    dst_t, dw, dh = calculate_default_transform("EPSG:4326", "EPSG:3857", flood.shape[1], flood.shape[0],
                                                *bounds, resolution=120)  # coarse so thin river flooding stays visible at state zoom
    m = np.zeros((dh, dw), "uint8")
    reproject(flood, m, src_transform=src_t, src_crs="EPSG:4326", dst_transform=dst_t, dst_crs="EPSG:3857",
              resampling=Resampling.max)
    rgba = np.zeros((4, dh, dw), "uint8")
    rgba[0], rgba[1], rgba[2], rgba[3] = 31, 111, 200, m * 255   # #1f6fc8
    with rasterio.open(os.path.join(DATA, "flood_overlay.png"), "w", driver="PNG", width=dw, height=dh,
                       count=4, dtype="uint8") as d:
        d.write(rgba)
    inv = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    x0, y1 = dst_t.c, dst_t.f
    x1, y0 = x0 + dw * dst_t.a, y1 + dh * dst_t.e
    (lo0, lo1), (la0, la1) = inv.transform([x0, x1], [y0, y1])
    summary = {"facilities_source_rows": len(rows), "analysed": len(feats), "dropped": len(dropped),
               "in_flood": agg["KELANTAN (all)"]["in_flood"], "within_500m": agg["KELANTAN (all)"]["within_500m"],
               "not_observed": agg["KELANTAN (all)"]["not_observed"], "event_window": EVENT,
               "gfm_items": sum(1 for _ in open(os.path.join(DATA, "gfm_scenes.csv"))) - 1,
               "overlay_bounds": [[la0, lo0], [la1, lo1]], "moh_commit": MOH_COMMIT}
    json.dump(summary, open(os.path.join(DATA, "summary.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
