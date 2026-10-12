# NZTA motorway traffic counts, Auckland CBD approaches

Written by `prep/fetch_nzta.py` from data retrieved on 2026-10-08. Do not edit by hand;
rerun the script (last section).

## Source and licence

New Zealand Transport Agency (NZTA Waka Kotahi), Traffic Monitoring System (TMS), published on the
NZTA Open Data portal (https://opendata-nzta.opendata.arcgis.com) under CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). Attribution to show with any use:

> Traffic counts sourced from the New Zealand Transport Agency (NZTA Waka Kotahi) Traffic Monitoring System via the NZTA Open Data portal, licensed for re-use under CC BY 4.0.

1. Daily counts: ArcGIS feature service `TMS_Telemetry_Sites`, layer 0,
   https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/TMS_Telemetry_Sites/FeatureServer/0, REST `query` with `returnDistinctValues=true`.
2. Quarter-hourly counts February 2022 to January 2025: ArcGIS item `39cdaa422dbd45c4b41e0e59b49e79e2`,
   https://www.arcgis.com/sharing/rest/content/items/39cdaa422dbd45c4b41e0e59b49e79e2/data: a 1,736,060,086-byte zip with one CSV per month (38
   members). Only the three members below were read, with HTTP Range requests (plus a 70 kB read of
   the zip directory at the end of the file); the zip itself was never downloaded.

| member | compressed bytes | uncompressed bytes | lines | lines kept (36 sites) | CRC-32 (checked) |
|---|---|---|---|---|---|
| tms_2024_05.csv | 52,414,376 | 678,765,546 | 6,801,665 | 310,228 | 0xfd523fa8 |
| tms_2024_08.csv | 54,011,685 | 697,972,691 | 7,014,293 | 305,558 | 0xd53fd50e |
| tms_2024_11.csv | 58,161,371 | 742,446,739 | 7,509,792 | 326,468 | 0x30e021fa |

Site coordinates (WGS84) are from the NZTA TMS site catalogue; x_nztm, y_nztm (NZTM2000,
EPSG:2193) are projected from them with pyproj.

## Files (8,695 kB in total)

| file | rows | bytes | content |
|---|---|---|---|
| tms_sites.csv | 36 | 5,963 | one row per site: site_ref, NZTA description, corridor, direction (NB/SB/EB/WB counted), flow_direction (its code in the count files), kind (mainline, link, ramp), cbd_bound (1 = the counted direction heads towards the CBD in the AM peak), cbd_role, lanes (lanes of the counted direction in the 2025-26 daily data, else in 2024), lat, lon, x_nztm, y_nztm, note |
| tms_daily_weekday.csv | 32,451 | 1,170,530 | site_ref, local_date, flow_direction, lane, class (light/heavy), count = vehicles per day; Mon-Fri 2025-10-01 to 2026-09-30 |
| tms_15min_am_2024.csv | 179,863 | 7,224,220 | site_ref, local_date, time (HH:MM, NZ local start of the quarter hour), flow_direction, lane, class, count = vehicles per quarter hour; Mon-Fri of May, Aug and Nov 2024, quarter hours 05:00 to 11:00 |
| tms_15min_daily_2024.csv | 7,526 | 294,213 | site_ref, local_date, flow_direction, lane, class, count, n_qh: full-day totals of the same quarter-hourly records (Mon-Fri, all 96 quarter hours), n_qh = quarter hours present; for day validity checks and peak-hour shares |

Counts are vehicles; x.5 values are part of the source. flow_direction is the TMS code: through
lanes 1 = increasing route position (SH1 southbound, SH16 westbound, SH20 northbound) and 2 =
decreasing (SH1 northbound, SH16 eastbound); ramps and links carry the ramp codes 3 to 6 (see
tms_sites.csv). All flow directions found for a site are kept; sites with more than one:
none. A direction total is the sum over all its lanes and both classes.

## Filters

* Sites: the 36 SiteRefs in `SITES` (prep/fetch_nzta.py): SH1 through lanes on both CBD
  approaches including the Harbour Bridge classifier, SH16 eastbound, SH20 northbound, the two
  Waterview SH20 -> SH16 links and the CBD exit ramps of the Central Motorway Junction.
* Daily: local dates 2025-10-01 to 2026-09-30, Monday to Friday (261 weekdays; public and
  school holidays are included). One query per site and calendar quarter (144
  requests, outFields startDate, classWeight, laneNumber, flowDirection, trafficCount);
  45,351 distinct records received, 12,900 weekend records dropped,
  0 duplicates left after DISTINCT (0 with differing
  counts; the larger is kept). startDate values seen: 00:00 UTC x45,351.
* Quarter-hourly: Monday to Friday of May, August and November 2024 (66 weekdays; no public
  or school holiday falls on them); quarter hours starting 05:00 to 10:45 in the AM file, all 96 in
  the daily totals. START_DATE is NZ local time: the overnight minimum of the summed weekday counts
  is at 02:00.

## Coverage per site (counted direction)

days = weekdays with a daily record 2025-26 (of 261); lanes = lanes present on at least half of
those days; complete = days with every such lane; median = median daily volume (all lanes and
classes) over the complete days, holidays included, no check for low lanes; no heavy = days
without any heavy record; AM days = weekdays with quarter-hourly AM records in 2024 (of 66).

| site_ref | corridor | dir | flow_direction | lanes | days | complete | median | no heavy | AM days |
|---|---|---|---|---|---|---|---|---|---|
| 01N20440 | SH1_south | NB | 2 | 3 | 226 | 226 | 63718 | 0 | 21 |
| 01N20439 | SH1_south | NB | 2 | 2 | 258 | 258 | 41583 | 0 | 66 |
| 01N20433 | SH1_south | NB | 2 | 3 | 189 | 189 | 66512 | 0 | 40 |
| 01N20431 | SH1_south | NB | 2 | 4 | 240 | 240 | 78516 | 0 | 66 |
| 01N20429 | SH1_south | NB | 2 | 3 | 235 | 235 | 72471 | 0 | 66 |
| 01N10417 | SH1_north | SB | 1 | 2 | 240 | 240 | 45253 | 240 | 66 |
| 01N10419 | SH1_north | SB | 1 | 3 | 231 | 231 | 51218 | 231 | 66 |
| 01N10420 | SH1_north | SB | 1 | 3 | 187 | 187 | 55847 | 0 | 43 |
| 01N19424 | SH1_north | SB | 1 | 5 | 261 | 261 | 83892 | 123 | 66 |
| 01N10425 | SH1_north | SB | 1 | 5 | 261 | 261 | 78575 | 0 | 66 |
| 01620013 | SH16 | EB | 2 | 3 | 232 | 232 | 41804 | 139 | 0 |
| 01620011 | SH16 | EB | 2 | 4 | 240 | 240 | 66654 | 0 | 66 |
| 01620009 | SH16 | EB | 2 | 4 | 251 | 251 | 65270 | 39 | 64 |
| 01620008 | SH16 | EB | 2 | 3 | 257 | 257 | 37419 | 104 | 66 |
| 01620006 | SH16 | EB | 2 | 4 | 193 | 193 | 61998 | 129 | 66 |
| 01620002 | SH16 | EB | 2 | 2 | 100 | 100 | 14536 | 0 | 25 |
| 01659008 | SH20_to_SH16 | EB | 5 | 2 | 181 | 181 | 21082 | 4 | 43 |
| 01639008 | SH20_to_SH16 | WB | 3 | 2 | 237 | 237 | 25500 | 0 | 65 |
| 02010015 | SH20 | NB | 1 | 4 | 253 | 253 | 75056 | 100 | 66 |
| 02019015 | SH20 | NB | 1 | 3 | 240 | 240 | 63986 | 0 | 66 |
| 02010017 | SH20 | NB | 1 | 3 | 224 | 224 | 63680 | 0 | 66 |
| 02010018 | SH20 | NB | 1 | 3 | 236 | 236 | 54299 | 16 | 66 |
| 02010020 | SH20 | NB | 1 | 2 | 232 | 232 | 37162 | 0 | 66 |
| 02010021 | SH20 | NB | 1 | 3 | 261 | 261 | 47383 | 0 | 66 |
| 01N40430 | CBD_exit_SH1N | NB | 6 | 1 | 217 | 217 | 10954 | 0 | 0 |
| 01N45429 | CBD_exit_SH1N | NB | 6 |  | 0 | 0 |  | 0 | 0 |
| 01N47429 | CBD_exit_SH1N | NB | 6 | 1 | 20 | 20 | 4664 | 14 | 0 |
| 01N46429 | CBD_exit_SH1N | NB | 6 | 1 | 24 | 24 | 6124 | 0 | 0 |
| 01N40427 | CBD_exit_SH1N | NB | 6 |  | 0 | 0 |  | 0 | 0 |
| 01N60425 | CBD_exit_SH1S | SB | 4 | 1 | 40 | 40 | 7246 | 13 | 0 |
| 01N60426 | CBD_exit_SH1S | SB | 4 |  | 0 | 0 |  | 0 | 0 |
| 01N60427 | CBD_exit_SH1S | SB | 4 | 1 | 90 | 90 | 7178 | 58 | 0 |
| 01N69427 | CBD_exit_SH1S | SB | 4 | 2 | 106 | 106 | 26302 | 10 | 0 |
| 01640002 | CBD_exit_SH16 | EB | 6 | 1 | 30 | 30 | 11398 | 0 | 0 |
| 01646004 | CBD_exit_SH16 | EB | 6 | 2 | 66 | 66 | 27225 | 66 | 0 |
| 01649004 | CBD_exit_SH16 | EB | 6 | 1 | 47 | 47 | 10478 | 27 | 0 |

## Known gaps and caveats

* No daily record 2025-26: 01N45429, 01N40427, 01N60426. Fewer than half of the weekdays:
  01620002 (100), 01N47429 (20), 01N46429 (24), 01N60425 (40), 01N60427 (90), 01N69427 (106), 01640002 (30), 01646004 (66), 01649004 (47).
* Months in which at least half of the sites report nothing: 2026-08 (20 of 33 sites).
* Quarter-hourly site-months whose median weekday total is outside 0.67 to 1.5 times the site's
  2025-26 daily median (do not use their volumes): 01N10420 2024-05 (x1.97, 52% of counts even); 01N10420 2024-08 (x1.92, 49% of counts even); 01N19424 2024-05 (x1.96, 100% of counts even). About a quarter to a half of the
  counts are even in a normal month; 100 % even means every count was doubled.
* No AM record in the three 2024 quarter-hourly members read: 01620013, 01N40430, 01N45429, 01N47429, 01N46429, 01N40427, 01N60425, 01N60426, 01N60427, 01N69427, 01640002, 01646004, 01649004.
  None of the CBD exit ramps appears in these months, so the 2024 AM profiles cover through lanes
  and links only.
* Unclassified days: in both daily files every site-direction-day has a heavy record on all its lanes or on none. Without one, the light count holds all vehicles (median
  totals of such days match those of classified days at the same site), so use light + heavy as
  the volume and do not read a class split from those days. Sites with no heavy record on 10 % or
  more of their days: 01N10417 (240 days), 01N10419 (231 days), 01N19424 (123 days), 01620013 (139 days), 01620009 (39 days), 01620008 (104 days), 01620006 (129 days), 02010015 (100 days), 01N47429 (14 days), 01N60425 (13 days), 01N60427 (58 days), 01646004 (66 days), 01649004 (27 days).
* 01N20440 (Panama Rd national telemetry site) has been gappy since its September 2022 handover;
  the Nelson St, Cook St, Shelly Beach Rd and Newton Rd off ramps are non-continuous sites.
* Since January 2026 the daily table holds most records up to ~40 times; the server-side DISTINCT
  removes the copies. Daily startDate is 12:00 UTC of the previous day before 2024 and 00:00 UTC of
  the day since; local date = (UTC + 12 h).date().
* Quarter hours with zero vehicles are absent from the quarter-hourly source, so a missing quarter
  hour means zero or no data. Lane outages show as low or missing lanes: check the lane totals in
  tms_15min_daily_2024.csv (and n_qh) or tms_daily_weekday.csv before using a day.
* Harbour Bridge (01N19424): the moveable barrier moves lanes between the directions during the
  day; always sum all lanes of a direction.
* 01N47429 (Wellesley St off ramp NB) has the Symonds St off ramp coordinates in the catalogue.
* The quarter-hourly zip also holds a stray member `tms_2025_01.csv.csv` (10 kB) and a metadata
  text file; neither was read.

## Re-run

    cd cordon_lite
    .venv\Scripts\python.exe -m prep.fetch_nzta --out data/nzta --cache <folder>

The download is 144 daily queries (382,353 bytes of gzip-encoded
JSON, 5,496,926 bytes decompressed) and 7 Range requests on the
quarter-hourly zip (164,657,522 bytes). With `--cache` the downloaded pieces are kept, and a
rerun with the same folder (add `--offline` to forbid network access) rebuilds identical files
without downloading. The daily service is live, so a fresh download later may return revised
counts.
