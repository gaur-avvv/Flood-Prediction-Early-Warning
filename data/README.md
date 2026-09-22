# Ward reference dataset

`india_wards.csv` — municipal ward names/codes used by `services/predictor.py::_generate_ward_grid`
to replace synthetic `Ward N` labels with real ward identities when the reverse-geocoded
town matches a `town` value in this file.

## Schema

| column | meaning |
|--------|---------|
| `town` | City/town name as returned by Nominatim (`city`/`town`/`village`), matched case-insensitively |
| `name` | Human-readable ward name |
| `code` | Stable ward identifier |

## Coverage

- **Delhi / New Delhi** — 289 wards each (MCD wards incl. Delhi Cantonment), duplicated under both town spellings
- **Mumbai** — 24 BMC wards (A–T zones, e.g. `Ward F/N`)
- **All-India districts** — 726 district rows (2019 set, Registrar General names) as a
  nationwide fallback: whenever the reverse-geocoded town has no ward rows, a district
  name match labels the grid (e.g. `Lucknow District (Uttar Pradesh)`). Districts whose
  town key already has ward rows (Delhi/New Delhi/Mumbai) are skipped so wards keep
  priority; 5 intra-dataset duplicate district names are de-duplicated (first wins).

## Source & attribution

Ward rows derived from [DataMeet Municipal_Spatial_Data](https://github.com/datameet/Municipal_Spatial_Data)
(**CC BY 4.0**):

- `Delhi/Delhi_Wards.geojson` → `Ward_Name`, `Ward_No`
- `Mumbai/BMC_Wards.geojson` → `name`, `gid`

> Municipal Spatial Data by DataMeet India community (CC BY 4.0)

District rows derived from [DataMeet indian-district-boundaries](https://github.com/datameet/indian-district-boundaries)
(**MIT**, © 2020 Guneet Narula):

- `topojson/india-districts-2019-734.json` → `district`, `dt_code`, `st_nm`, `st_code`
- `code` = `D<st_code>-<dt_code>`; `name` = `<district> District (<state>)`
- District names follow the Registrar General of India and may differ from common/local spellings (noted upstream).

To regenerate: download the two ward GeoJSON files and the district TopoJSON above,
map their properties to `town,name,code` (wards first, districts appended), and rewrite
this CSV. To add a city, repeat with any ward GeoJSON from Municipal_Spatial_Data
(Ahmedabad, Bangalore, Chennai, Kolkata, …).
