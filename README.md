# Kelantan Flood Exposure of Health Facilities

**Live map:** https://ruhaifimd.github.io/kelantan-flood-health-facilities/

> Exploratory analysis using public data. Not an official Ministry of Health Malaysia risk assessment.

![Screenshot](screenshot.png)

Which public health facilities in Kelantan sat inside, or within 500 m of, the flood extent observed by satellite during the Nov–Dec 2024 floods?

| | Count |
|---|---|
| Kelantan facilities in source | 429 |
| Dropped (coordinates outside Kelantan) | 3 |
| Analysed | 426 |
| Inside observed flood extent | 1 |
| Within 500 m of observed flooding | 59 (13.8%) |

Highest share within 500 m: Pasir Puteh (28.6%), Pasir Mas (26.7%), Tumpat (25.0%). Full table: [`data/district_summary.csv`](data/district_summary.csv).

## Files
- `data/facilities.geojson` – per facility: name, type, district, lat/lon, `in_flood`, `dist_m`, `within_500m`
- `data/district_summary.csv`, `data/dropped.csv`, `data/gfm_scenes.csv`, `data/flood_extent_gfm_2024.tif` (1 flooded, 0 dry, 255 no data)
- `scripts/pipeline.py` – rebuilds `data/` (`python scripts/pipeline.py`); `scripts/check.py` – assert spot-check of 5 facilities
- `methods.html` – method, dropped records, limitations

## Limitations
Observed extent is not hazard probability; SAR under-detects urban and vegetated flooding; source coordinate precision varies (2–7 dp). See [methods](methods.html).

## Sources & attribution
- Facilities: [MoH-Malaysia/data-resources-public](https://github.com/MoH-Malaysia/data-resources-public) `facilities_master.csv`, snapshot 31 Dec 2025 (no LICENSE file in source repo; only a derived subset is republished).
- Flood: Contains modified Copernicus Emergency Management Service information 2024 – GloFAS Global Flood Monitoring (GFM) ensemble flood extent. Terms: https://global-flood.emergency.copernicus.eu/terms-of-use/
- Boundaries: [geoBoundaries](https://www.geoboundaries.org/) MYS ADM2, CC BY 4.0.
- Basemap: © OpenStreetMap contributors.
