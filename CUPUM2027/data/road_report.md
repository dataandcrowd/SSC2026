# Cordon-Lite road congestion inputs (prep.build_roads)

## Summary

- Sections: 5903 on the pre-gate parts of 3000 origin paths (19517 graph edges, 849.4 km, 879.3 free-flow minutes); 142470 origin-section rows, 47.5 sections per origin on average (max 124).
- The rebuilt prep paths reproduce `data/origins.csv` exactly (gate_id, corridor_id, free-flow minutes); per-origin sum of section ff_min minus fftt_to_gate_min: max abs 2.66e-14 min.
- Capacity factor k = 0.076999 (cap_vph = k x max(adt_dir, the ADT floor of the section's frc); see 'Capacity floor by road class'), bisected in [0.02, 0.3] so that the origin-weighted travel time index of departures 08:00-08:59 under usual traffic on the non-motorway part of each trip (time on its sections other than motorway mainline over their free-flow time; prep.road_tti_exclude_mwy) is 1.714 (achieved 1.7140).
- Usual-traffic V/C is 2 x 0.6 x peak_ratio x r(m) / k on every section except the 232 motorway sections from an NZTA count site (there it is the site's counted flow over its capacity, at most 1) and the 280 sections whose capacity the road-class floor raised (lower there); with the default peak ratio 0.096 that is 1.50 x r(m).

## Capacity floor by road class

cap_vph = k x max(adt_dir, adt_floor[frc]), adt_floor = the 5th percentile of adt_dir over all sections of that frc (unweighted, before k; prep.road_adt_floor_pct), so very small or stale counts do not give near-zero capacity. The floor is inside the k calibration; it sets capacity only (observed and background flows stay from the counts); NZTA motorway sections keep their measured capacity. 280 sections raised, 1.39% of origin-weighted pre-gate minutes.

| frc | sections | ADT floor (adt_dir) | capacity floor (veh/h) | sections raised | share of the class's minutes | share of all minutes | NZTA sections below the floor |
|---|---|---|---|---|---|---|---|
| 0 | 296 | 15989.8 | 1231.2 | 12 | 1.24% | 0.690% | 3 |
| 1 | 181 | 6432.0 | 495.3 | 8 | 0.30% | 0.004% | 0 |
| 2 | 1189 | 4627.5 | 356.3 | 60 | 1.87% | 0.378% | 0 |
| 3 | 2076 | 2566.5 | 197.6 | 92 | 1.02% | 0.151% | 0 |
| 4 | 2161 | 1851.0 | 142.5 | 108 | 2.00% | 0.166% | 0 |

## Travel time index under usual traffic

Probe car on each origin's pre-gate route (adds no load), one departure per minute, origin-weighted mean of (time to the gate) / (free-flow time to the gate). Motorway and non-motorway: the same over the trip's motorway mainline part (time on those sections over their free-flow time; origins whose route has such a part) and over the rest. With the motorway breakdown rule (road.mwy_breakdown); the last two columns show the plain BPR curve at the same k.

| departures | all | motorway | non-motorway | all, no breakdown | motorway, no breakdown |
|---|---|---|---|---|---|
| 06:00-06:59 | 1.239 | 1.410 | 1.042 | 1.078 | 1.107 |
| 07:00-07:59 | 1.747 | 1.997 | 1.410 | 1.242 | 1.098 |
| 08:00-08:59 | 1.927 | 2.032 | 1.714 | 1.399 | 1.090 |
| 09:00-09:59 | 1.529 | 1.774 | 1.205 | 1.140 | 1.075 |
| 07:30-08:29 | 1.917 | 2.036 | 1.701 | 1.388 | 1.098 |
| 07:30 only | 1.770 | 2.033 | 1.407 | 1.240 | 1.099 |

By corridor (departures in the calibration window):

| corridor | name | origins | TTI |
|---|---|---|---|
| 0 | East (The Strand, Gladstone Road) | 68 | 1.780 |
| 1 | South-east (Alten Road, Parnell Rise) | 901 | 1.875 |
| 2 | South (Wellesley Street ramp) | 723 | 1.946 |
| 3 | South-west (Northern Motorway ramp, Helensville ramp) | 701 | 1.868 |
| 4 | West (Fanshawe Street ramp, Westhaven Drive) | 607 | 2.073 |

## Count matching

- Count points: 13835 in `../../SSC2026/netlogo/Data/Average_Daily_Traffic_Counts.geojson`, 13717 with adt > 0 (local 13165, SH carriageway 276, SH ramp 257, SH without direction 11, not used; 8 SH ramp records of bus-only ramps or busways (named so, or under 50% cars) are not used).
- Matched to a same-name graph edge within 30 m and used: 3179 (local 2741, SH carriageway 230, SH ramp 208). Not used: 66 matched AT counts below 0.25 of a more recent count of the same street within 1000 m (stale or misplaced counts). Graph edges holding a count: 3110; propagated within 1000 m: 25954; default: 1771 (of 30835 graph edges).
- Sections take adt_source 'count' when one of their edges holds a count, 'propagated' when their values come from a count on the same street, else 'default' (median two-way ADT of count edges with the same frc and speed band, else frc); motorway sections of a corridor with NZTA count sites take 'nzta' (their capacity, flow and time profile come from the nearest site of their corridor; see 'NZTA motorway counts' below).

Coverage by frc (share of sections | share of origin-weighted pre-gate free-flow minutes):

| frc | sections | count | propagated | default | nzta | minutes share of all | count | propagated | default | nzta |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 296 | 7.4% | 12.8% | 3.4% | 76.4% | 55.4% | 1.7% | 1.2% | 0.5% | 96.7% |
| 1 | 181 | 29.8% | 55.8% | 13.8% | 0.6% | 1.2% | 49.0% | 45.0% | 3.3% | 2.6% |
| 2 | 1189 | 35.3% | 59.1% | 5.1% | 0.4% | 20.2% | 53.3% | 22.5% | 14.7% | 9.6% |
| 3 | 2076 | 31.9% | 65.3% | 2.8% | 0.0% | 14.8% | 52.7% | 45.4% | 2.0% | 0.0% |
| 4 | 2161 | 36.7% | 58.4% | 4.8% | 0.0% | 8.3% | 66.4% | 31.9% | 1.7% | 0.0% |
| all | 5903 | 33.1% | 58.6% | 4.4% | 3.9% | 100.0% | 25.6% | 15.1% | 3.7% | 55.6% |

- AM peak ratio from a count with an AM peak hour (06:00-09:45): 1446 sections (8.5% of origin-weighted pre-gate minutes); the others use 0.096 (not used on 'nzta' sections). Peak ratio over sections (min | p10 | median | p90 | max): 0.070 | 0.096 | 0.096 | 0.106 | 0.200.

## V/C under usual traffic

V/C = obs_peak_vph x r(m) / cap_vph (background plus usual commuters, what the counts say). Median over sections and origin-weighted mean over traversal minutes.

| frc | sections | median 07:30 | median 08:15 | weighted 07:30 | weighted 08:15 |
|---|---|---|---|---|---|
| 0 | 296 | 0.91 | 0.95 | 0.87 | 0.84 |
| 1 | 181 | 1.23 | 1.54 | 1.26 | 1.58 |
| 2 | 1189 | 1.23 | 1.54 | 1.19 | 1.48 |
| 3 | 2076 | 1.23 | 1.54 | 1.24 | 1.56 |
| 4 | 2161 | 1.23 | 1.54 | 1.24 | 1.56 |

Speed factor f = 1 / (1 + 0.15 (V/C)^4), at least 0.18; time on a section = ff_min / f.

## Motorway flow breakdown

- Motorway mainline sections (mwy = 1): frc 0 or a street name holding 'Motorway', not a ramp by name, signed at least 70 km/h: 285 sections, 147.1 km, 91.7 free-flow minutes, 56.2% of origin-weighted pre-gate minutes (sections by name: '20' 2, 'Airport Motorway' 2, 'George Bolt Memorial Drive' 5, 'Northern Motorway' 60, 'Northwestern Motorway' 40, 'Southern Motorway' 88, 'Southwestern Motorway' 42, 'Upper Harbour Motorway' 46).
- Motorway by name, not frc 0 (TomTom gives some mainline links a lower frc, e.g. the Auckland Harbour Bridge stretch of the Northern Motorway; these sections had mwy = 0 under the frc-0-only rule before 2026-10-08): section 189 'Northern Motorway' frc 2, 80 km/h, 0.08 km, 0.06 min, 394 origins, window 06:15-09:30; section 190 'Northern Motorway' frc 2, 80 km/h, 0.8949 km, 0.67 min, 394 origins, window 06:15-09:30; section 191 'Northern Motorway' frc 2, 80 km/h, 0.9556 km, 0.72 min, 394 origins, window 06:15-09:30; section 192 'Northern Motorway' frc 2, 80 km/h, 0.0724 km, 0.05 min, 395 origins, window 06:15-09:30; section 193 'Northern Motorway' frc 2, 80 km/h, 0.1135 km, 0.09 min, 396 origins, window 06:15-09:30; section 743 'Northern Motorway' frc 1, 80 km/h, 0.069 km, 0.05 min, 177 origins, window 06:15-09:30 (in all 1.64 free-flow minutes and 2150 origin passes). Sections with a motorway name left out (ramps or slower than 70 km/h, not frc 0): 'Entry 448 Southwestern Motorway (frc 3, 100 km/h)' 1, 'Exit 2 Southern Motorway (frc 2, 80 km/h)' 1.
- Numbered names (TomTom names a few state-highway links by number; they count as motorway by frc only): '19 (frc 1, 50 km/h, mwy 0)' 4, '19A (frc 3, 50 km/h, mwy 0)' 2, '20 (frc 0, 100 km/h, mwy 1)' 2, '32 (frc 2, 27 km/h, mwy 0)' 1, '32 (frc 2, 28 km/h, mwy 0)' 1. No section is named 'State Highway N'.
- frc-0 ramps left out (name starts with or holds Entry, Exit, 'Entry And Exit', Ramp, On-Ramp, Off-Ramp; sections): 'Entry 1 Southern Motorway' 2, 'Entry 449 Southwestern Motorway' 1, 'Exit 1 Southern Motorway' 2, 'Exit 424D Helensville' 2, 'Exit 449 Southwestern Motorway' 5, 'Exit 4A Northern Motorway' 1.
- frc-0 sections signed below 70 km/h left out (signalised streets, no motorway): 'George Bolt Memorial Drive (60 km/h)' 2, 'Stanley Street (50 km/h)' 2. Motorway sections that also hold a ramp edge (same normalised name and count values, so joined to the mainline; the section takes its first edge's name): section 1024: Entry 9 Airport Motorway.
- Breakdown window: a motorway section of a corridor with NZTA count sites (adt_source 'nzta', 232 sections) takes its site's window (the counts' breakdown onset and recovery, see 'NZTA motorway counts'); every other motorway section the window under usual traffic (V/C = obs_peak_vph x r(m) / cap_vph): from the first minute with V/C >= 1 until the first later minute with V/C < 0.95 (hysteresis). 230 of 285 sections have one; start (min | median | max) 06:15 | 07:08 | 07:26, end 09:19 | 09:45 | 11:00.
- Engine rule (road.mwy_breakdown = true): a motorway section is broken down at minute m inside its window or when today's V/C reaches 1; it then runs at f = 1 / (1 + 0.15 (V/C / (1 - cap_drop))^4) (capacity cap_drop lower: the site's measured drop on 'nzta' sections, 10% (road.mwy_capacity_drop, x / 0.9) elsewhere) and at most 0.45 of free-flow speed (stop-and-go flow), at least 0.18. The charge cannot shorten the usual window: commuters are a few percent of motorway flow.

Share of motorway mainline minutes broken down under usual traffic (by the sections' free-flow minutes | weighted by the origins using them):

| clock | 07:00 | 07:30 | 08:00 | 08:30 | 09:00 | 09:30 | 10:00 |
|---|---|---|---|---|---|---|---|
| network | 36% | 81% | 81% | 81% | 81% | 60% | 31% |
| weighted | 59% | 94% | 94% | 94% | 94% | 73% | 48% |

## NZTA motorway counts

Source: data/nzta (prep/fetch_nzta.py; NZTA Traffic Monitoring System, CC BY 4.0). Traffic counts sourced from the New Zealand Transport Agency (NZTA Waka Kotahi) Traffic Monitoring System via the NZTA Open Data portal, licensed for re-use under CC BY 4.0.

- Valid 2024 weekday (May, Aug, Nov; counted CBD-bound direction): no lane outage (a core lane missing or below 0.3 x its median day, full day or 05:00-11:00), all 24 quarter hours 05:00-10:45, the site-month's median day within 0.67-1.5 x the site's 2025-26 median (doubled counts), no holiday. A site is used when it counts CBD-bound through lanes (not a link, ramp or 'mixed' site) on at least 20 valid days.
- Per site: q(t) = mean weekday 15-min flow (veh/h, all lanes and classes); q_max its maximum at t_max; plateau = median of the quarter hours from t_max + 30 min to 09:30; delta = 1 - plateau / q_max. Breakdown when delta >= 0.05 (onset: first quarter hour after t_max at or below q_max (1 - delta / 2), cap_drop = delta) or when saturated (>= 0.95 q_max for >= 60 min; onset: start of that run; cap_drop = max(delta, road.mwy_capacity_drop), as the drop cannot be measured at the bottleneck itself). Recovery: first quarter hour from which q stays < 0.95 x plateau or > plateau + 0.5 x (q_max - plateau) for 2 quarter hours (each of them; below: demand fell; above: the downstream bottleneck cleared, the queue drained and throughput rose back towards its pre-breakdown level); 11:00 when that never happens by 10:45.
- Amendments to the SPEC3 rule (the literal rule's window is in the last column): a drop or a saturated run counts only when it starts by 07:00 (a plateau of two hours or more before 09:30; after a later maximum the counts cannot tell a capacity drop from the end of the demand peak), and recovery is looked for from 09:30 on (a dip inside the plateau is still congested flow).
- Capacity C = q_max x scale, observed flow = q(t) x scale (throughput as counted), scale = median weekday 2025-26 (no outage, no holiday) / median valid 2024 day of the same site. obs_peak_vph = the peak-hour mean of the scaled q; the site's time profile r(m) = scaled q / obs_peak_vph at the quarter-hour centres, linear between them, the default profile scaled to match before 05:07 and after 10:52.

| site | corridor | valid days | q_max (veh/h) at | plateau | delta | saturated | window | cap_drop | scale 2024 -> 2025-26 | capacity | obs_peak_vph | sections | k x ADT cap of those (min / median / max) | literal SPEC3 window |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 01N10417 | SH1_north | 66 | 3536 at 06:00 | 2604 | 0.263 | no | 06:45-09:30 | 0.263 | 44832 -> 45342 = 1.0114 (site) | 3576 | 3368 | 27 | 2046 / 2941 / 5033 | 06:45-07:15 |
| 01N10419 | SH1_north | 66 | 4465 at 06:15 | 3447 | 0.228 | no | 06:45-11:00 (no recovery by 10:45) | 0.228 | 50388 -> 51368 = 1.0194 (site) | 4551 | 4269 | 12 | 3942 / 4262 / 5836 | 06:45-11:00 |
| 01N10425 | SH1_north | 66 | 6551 at 06:30 | 6409 | 0.022 | 165 min from 06:15 | 06:15-09:30 | 0.100 | 77905 -> 78824 = 1.0118 (site) | 6629 | 6579 | 10 | 3284 / 4324 / 6043 | 06:15-09:15 |
| 01N19424 | SH1_north | 41 | 7008 at 08:00 | 6736 | 0.039 | 180 min from 06:15 | 06:15-09:30 | 0.100 | 84265 -> 84490 = 1.0027 (site) | 7026 | 7005 | 11 | 3462 / 6473 / 6680 | 06:15-09:30 |
| 01N20431 | SH1_south | 66 | 5289 at 06:30 | 4980 | 0.058 | no | 06:45-11:00 (no recovery by 10:45) | 0.058 | 78530 -> 78859 = 1.0042 (site) | 5311 | 5162 | 17 | 5054 / 7086 / 8421 | 06:45-11:00 |
| 01N20433 | SH1_south | 40 | 5002 at 06:15 | 4200 | 0.160 | no | 07:00-11:00 (no recovery by 10:45) | 0.160 | 67234 -> 66858 = 0.9944 (site) | 4974 | 4724 | 13 | 4815 / 5727 / 6664 | 07:00-11:00 |
| 01N20439 | SH1_south | 66 | 3374 at 06:15 | 2492 | 0.261 | no | 07:15-11:00 (no recovery by 10:45) | 0.261 | 42401 -> 41696 = 0.9834 (site) | 3317 | 3236 | 11 | 3012 / 4343 / 5743 | 07:15-08:00 |
| 01N20440 | SH1_south | 21 | 5093 at 06:00 | 4155 | 0.184 | no | 07:15-09:45 | 0.184 | 65003 -> 63781 = 0.9812 (site) | 4997 | 4843 | 47 | 2594 / 4085 / 5169 | 07:15-08:00 |
| 01620002 | SH16 | 25 | 1484 at 07:45 | 1277 | 0.139 | no | none | 0.100 | 15838 -> 14339 = 0.9054 (site) | 1343 | 1314 | 11 | 1231 / 1359 / 1702 | 07:30-09:30 |
| 01620006 | SH16 | 66 | 5689 at 06:15 | 4868 | 0.144 | no | 06:30-09:30 | 0.144 | 62734 -> 62351 = 0.9939 (site) | 5654 | 5191 | 9 | 3498 / 3567 / 4930 | 06:30-09:30 |
| 01620008 | SH16 | 66 | 3996 at 06:15 | 2952 | 0.261 | no | 06:45-09:45 | 0.261 | 37950 -> 37676 = 0.9928 (site) | 3967 | 3709 | 3 | 2822 / 3968 / 4167 | 06:45-08:00 |
| 01620009 | SH16 | 64 | 6532 at 06:15 | 4805 | 0.264 | no | 07:15-09:45 | 0.264 | 65362 -> 65606 = 1.0037 (site) | 6557 | 6277 | 3 | 3279 / 6731 / 6731 | 07:15-09:45 |
| 01620011 | SH16 | 66 | 6446 at 06:15 | 4741 | 0.264 | no | 07:15-09:45 | 0.264 | 66856 -> 66765 = 0.9986 (site) | 6437 | 6194 | 14 | 1710 / 2829 / 3867 | 07:15-08:30 |
| 02010015 | SH20 | 66 | 5160 at 08:00 | 4482 | 0.132 | no | none | 0.100 | 76260 -> 75210 = 0.9862 (site) | 5089 | 5007 | 37 | 1347 / 2767 / 4871 | 07:30-09:15 |
| 02010017 | SH20 | 66 | 4082 at 08:00 | 3688 | 0.096 | no | none | 0.100 | 64447 -> 64222 = 0.9965 (site) | 4068 | 3994 | 2 | 2459 / 2623 / 2787 | 07:30-09:15 |
| 02010018 | SH20 | 66 | 3498 at 08:00 | 3182 | 0.090 | no | none | 0.100 | 55176 -> 54532 = 0.9883 (site) | 3457 | 3413 | 0 | - | 07:30-09:15 |
| 02010020 | SH20 | 66 | 2762 at 08:00 | 2353 | 0.148 | no | none | 0.100 | 37812 -> 37546 = 0.9930 (site) | 2742 | 2647 | 0 | - | 08:30-09:15 |
| 02010021 | SH20 | 66 | 3941 at 08:00 | 3165 | 0.197 | no | none | 0.100 | 48159 -> 47516 = 0.9866 (site) | 3889 | 3760 | 5 | 2852 / 2852 / 2852 | 08:30-09:15 |
| 02019015 | SH20 | 66 | 4078 at 08:00 | 3618 | 0.113 | no | none | 0.100 | 64512 -> 64395 = 0.9982 (site) | 4071 | 3995 | 0 | - | 07:30-09:15 |

Windows that end because the flow rose back above plateau + 0.5 x (q_max - plateau): 01N10417 06:45-09:30 (by a fall in flow alone 06:45-11:00).

Sites not used: 01N10420 (SH1_north): 19 valid 2024 weekdays (< 20); 01N20429 (SH1_south): not CBD-bound (mixed); 01620013 (SH16): 0 valid 2024 weekdays (< 20); 01639008 (SH20_to_SH16): not a through-lane site (link); 01659008 (SH20_to_SH16): not a through-lane site (link); 01N40427 (CBD_exit_SH1N): not a through-lane site (ramp); 01N40430 (CBD_exit_SH1N): not a through-lane site (ramp); 01N45429 (CBD_exit_SH1N): not a through-lane site (ramp); 01N46429 (CBD_exit_SH1N): not a through-lane site (ramp); 01N47429 (CBD_exit_SH1N): not a through-lane site (ramp); 01N60425 (CBD_exit_SH1S): not a through-lane site (ramp); 01N60426 (CBD_exit_SH1S): not a through-lane site (ramp); 01N60427 (CBD_exit_SH1S): not a through-lane site (ramp); 01N69427 (CBD_exit_SH1S): not a through-lane site (ramp); 01640002 (CBD_exit_SH16): not a through-lane site (ramp); 01646004 (CBD_exit_SH16): not a through-lane site (ramp); 01649004 (CBD_exit_SH16): not a through-lane site (ramp).
Doubled-count site-months left out: 01N10420 2024-05 (x1.95); 2024-08 (x1.90); 01N19424 2024-05 (x1.94).

Motorway sections mapped to the nearest used site of their corridor at any distance (midpoint to site): 232 sections, 98.9% of the origin-weighted motorway minutes. Motorway sections of a route without a used site keep k x max(ADT, the road-class floor), the default profile, the usual-traffic window and road.mwy_capacity_drop.

| street name | corridor | sections | mapped | free-flow min (mapped) | sites | farthest (m) |
|---|---|---|---|---|---|---|
| 20 | SH20 | 2 | 2 | 0.45 (0.45) | 02010021 2 | 3312 |
| Airport Motorway | none (no site) | 2 | 0 | 0.98 (0.00) | - | - |
| George Bolt Memorial Drive | none (no site) | 5 | 0 | 1.35 (0.00) | - | - |
| Northern Motorway | SH1_north | 60 | 60 | 18.76 (18.76) | 01N10417 27, 01N10419 12, 01N10425 10, 01N19424 11 | 6070 |
| Northwestern Motorway | SH16 | 40 | 40 | 15.17 (15.17) | 01620002 11, 01620006 9, 01620008 3, 01620009 3, 01620011 14 | 5375 |
| Southern Motorway | SH1_south | 88 | 88 | 29.23 (29.23) | 01N20431 17, 01N20433 13, 01N20439 11, 01N20440 47 | 12572 |
| Southwestern Motorway | SH20 | 42 | 42 | 15.16 (15.16) | 02010015 37, 02010017 2, 02010021 3 | 12141 |
| Upper Harbour Motorway | none (no site) | 46 | 0 | 10.56 (0.00) | - | - |

Distance from a mapped section's midpoint to its site (m), and the mapped sections beyond the 6 km limit of SPEC3 (count, and their share of the corridor's origin-weighted mapped motorway minutes):

| corridor | sections | min | p10 | median | p90 | max | beyond 6 km | minutes share beyond 6 km |
|---|---|---|---|---|---|---|---|---|
| all | 232 | 19 | 241 | 1485 | 8823 | 12572 | 40 | 3.7% |
| SH16 | 40 | 23 | 164 | 670 | 3442 | 5375 | 0 | 0.0% |
| SH1_north | 60 | 19 | 210 | 1047 | 4881 | 6070 | 1 | 0.0% |
| SH1_south | 88 | 36 | 252 | 1866 | 10039 | 12572 | 26 | 5.7% |
| SH20 | 44 | 31 | 484 | 3654 | 10945 | 12141 | 13 | 8.7% |

Farthest mapped sections:

| section | street name | site | distance (m) | km | free-flow min | origins | window |
|---|---|---|---|---|---|---|---|
| 4736 | Southern Motorway | 01N20440 | 12572 | 0.1856 | 0.11 | 1 | 07:15-09:45 |
| 2250 | Southwestern Motorway | 02010015 | 12141 | 0.4178 | 0.25 | 21 | none |
| 636 | Southwestern Motorway | 02010015 | 11999 | 0.4126 | 0.25 | 44 | none |
| 2187 | Southern Motorway | 01N20440 | 11927 | 1.2043 | 0.72 | 44 | 07:15-09:45 |
| 4737 | Southern Motorway | 01N20440 | 11802 | 1.5256 | 0.92 | 1 | 07:15-09:45 |
| 635 | Southwestern Motorway | 02010015 | 11796 | 0.1686 | 0.10 | 44 | none |
| 634 | Southwestern Motorway | 02010015 | 11560 | 0.5768 | 0.35 | 32 | none |
| 2061 | Southern Motorway | 01N20440 | 11061 | 0.6282 | 0.38 | 102 | 07:15-09:45 |
| 633 | Southwestern Motorway | 02010015 | 11054 | 1.0523 | 0.63 | 32 | none |
| 4738 | Southern Motorway | 01N20440 | 10760 | 0.6303 | 0.38 | 1 | 07:15-09:45 |

Motorway TTI by motorway corridor under usual traffic (time on that corridor's motorway sections over their free-flow time, origin-weighted, origins using them), by departure:

| corridor | 06-07 | 07-08 | 08-09 | 09-10 | 07:30-08:29 | 07:30 |
|---|---|---|---|---|---|---|
| SH1_north | 1.810 | 2.222 | 2.222 | 1.652 | 2.222 | 2.222 |
| SH1_south | 1.355 | 2.169 | 2.222 | 2.151 | 2.222 | 2.222 |
| SH16 | 1.236 | 1.498 | 1.490 | 1.243 | 1.509 | 1.519 |
| SH20 | 1.041 | 1.108 | 1.117 | 1.056 | 1.134 | 1.113 |
| other | 1.042 | 2.122 | 2.252 | 2.156 | 2.252 | 2.222 |

## Commuter share of the counted volume

expected_commuter_veh = 19000 x 0.8 x (origin weight using the section) / (all origin weight); phi = min(1, expected / observed 06:00-10:00 volume); bg_peak_vph = obs_peak_vph x (1 - phi); w_factor = min(1, observed / expected).

| quantity | min | p10 | median | p90 | max |
|---|---|---|---|---|---|
| phi | 0.000 | 0.001 | 0.010 | 0.065 | 1.000 |
| w_factor | 0.422 | 1.000 | 1.000 | 1.000 | 1.000 |
| expected_commuter_veh | 1 | 4 | 22 | 216 | 4487 |
| am_volume_veh | 15 | 1207 | 2728 | 5901 | 26999 |

- Sections where the commuters reach the whole counted volume (phi = 1, w_factor < 1): 4 (0.1% of sections, 1.4% of origin-weighted pre-gate minutes).
- Origin-weighted mean phi over pre-gate minutes: 0.158.
- Data check: 0 sections have cap_vph below 50 veh/h (very small counts, e.g. none); 0.00% of origin-weighted pre-gate minutes.

## Sections used by the most origins

| section | street | frc | speed | ff_min | origins | adt_twoway | source | peak_ratio | phi | w_factor | V/C 08:15 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 162 | Alten Road | 4 | 30 | 0.06 | 834 | 13611 | propagated | 0.079 | 1.000 | 0.422 | 1.26 |
| 160 | Stanley Street | 1 | 50 | 0.09 | 833 | 55866 | count | 0.096 | 0.472 | 1.000 | 1.54 |
| 161 | Stanley Street | 1 | 50 | 0.04 | 833 | 22621 | propagated | 0.128 | 0.875 | 1.000 | 2.05 |
| 158 | Northwestern Motorway | 0 | 80 | 0.22 | 832 | 44198 | nzta | 0.096 | 1.000 | 1.000 | 0.97 |
| 159 | Stanley Street | 0 | 50 | 0.14 | 832 | 55866 | propagated | 0.096 | 0.471 | 1.000 | 1.54 |
| 157 | Northwestern Motorway | 0 | 80 | 0.08 | 810 | 44198 | nzta | 0.096 | 0.973 | 1.000 | 0.97 |
| 155 | Entry 429 Wellesley Street | 2 | 80 | 0.33 | 808 | 28121 | default | 0.096 | 0.907 | 1.000 | 1.54 |
| 156 | Exit 2 Southern Motorway | 2 | 80 | 0.17 | 808 | 18216 | count | 0.096 | 1.000 | 0.714 | 1.54 |
| 154 | Entry 429 Wellesley Street | 2 | 80 | 0.10 | 807 | 28121 | default | 0.096 | 0.905 | 1.000 | 1.54 |
| 153 | Entry 429 Wellesley Street | 2 | 80 | 0.04 | 806 | 28121 | default | 0.096 | 0.903 | 1.000 | 1.54 |

## Assumptions

- [SPEC] Routes are the prep shortest free-flow paths on the undirected graph (no rerouting); only the pre-gate part is congested; the gate-to-destination leg stays free flow.
- [DATA] Two-way ADT from the AT/NZTA count points (`../../SSC2026/netlogo/Data/Average_Daily_Traffic_Counts.geojson`): 7-day averages of mixed vintage (motorway counts mostly 2016); AT counts are two-way totals unless the record's name carries a direction (EASTBOUND, EAST BOUND, ...); state-highway records count one carriageway or ramp.
- [A] A count matches the nearest graph edge with the same normalised street name within 30 m (state-highway carriageway records by route to the motorway names, ramp records to ramp or unnamed edges); several counts on one edge keep the most recent; SH records without a direction suffix and SH ramp records of bus-only ramps or busways (named so, or under 50% cars) are not used; an AT count below 0.25 of a more recent count of the same street within 1000 m (straight line) is not used.
- [A] A count holds along the same street up to 1000 m through the network (motorway, frc 1 and ramp edges need the identical TomTom name; SH carriageway counts only on edges within 60 deg of their bearing); nearest source wins. Other edges take the median two-way ADT of count edges with the same frc and speed band (at least 5 edges), else frc.
- [SPEC, A] Direction: a count of one carriageway or direction (SH -I/-D, SH ramp, AT count whose name carries a direction) is directional (adt_dir = adt, two-way equivalent 2 x adt); any other AT count is a two-way total (adt_dir = adt / 2), also on TomTom edges without a reversed twin, which are mostly carriageways of divided roads rather than one-way streets.
- [A] Inbound share of the two-way AM peak-hour flow 0.6; AM peak ratio peaktraffic / adt where the count's peak hour starts 06:00-09:45, else 0.096 [DATA]; clipped to [0.05, 0.2].
- [A] Time profile r(m): 15-min bins from 06:00 [0.32, 0.38, 0.46, 0.56, 0.67, 0.77, 0.87, 0.93, 1.01, 1.05, 1.0, 0.93, 0.81, 0.73, 0.69, 0.65, 0.62, 0.6] (peak timing from the counts [DATA], shape assumed), linear between bin centres, ramp to 0.15 x the first value at 05:00.
- [A] Capacity = k x directional ADT (SSC2026 rule) with k calibrated to the TomTom Traffic Index [DATA]: Auckland 2025 morning rush-hour congestion level 71.4% => TTI 1.714 (https://www.tomtom.com/traffic-index/auckland-traffic/). The ADT in the capacity is at least the 5th percentile of the directional ADT of the section's road class (frc), so a very small or stale count does not give a near-zero capacity; the flows stay from the counts.
- [A] BPR alpha 0.15, beta 4, speed floor 0.18 (SSC2026); commuter flow counts the cars that entered in the last 15 min.
- [A, L] Motorway flow breakdown (road.mwy_*): breakdown at V/C 1, recovery below 0.95 under usual traffic, 10% capacity drop (Cassidy and Bertini 1999; 3-18% in the literature), at most 0.45 of free-flow speed (bottleneck speeds of 25-35 km/h at SH20 in 2005, Brown et al.). The window is the usual traffic's (the counts), so a charge that removes commuter cars cannot shorten it; today's commuters can only start a breakdown earlier (V/C threshold). A motorway mainline section is frc 0 or carries a motorway name (TomTom's frc is lower on a few mainline links, such as the Harbour Bridge). Motorway sections of a corridor with NZTA count sites (99% of the origin-weighted motorway minutes) take capacity, flow, time profile, window and capacity drop from the 2024 quarter-hourly counts (scaled to 2025-26 volumes) of the nearest site of their corridor, at any distance; the others (motorways without a site, 53 sections) keep the default peak ratio 0.096 and capacity k x max(ADT, the road-class floor): the 47 at k x ADT break down together (07:08-10:01); the 6 whose capacity the floor raised have a lower V/C and their own, shorter windows: 07:16-09:40 (1), 07:23-09:22 (2), 07:26-09:19 (3). k is matched on the non-motorway part of the trips, so the TomTom index sets the arterial level and the motorway level follows from the breakdown rule.
- [A] Commuters are netted out of the counts with car share 0.8 of 19000 represented vehicles; where all-or-nothing routing puts more commuter cars on a section than counted, their weight w_factor is reduced instead.
- [A] Routing is undirected: many motorway traversals follow the opposite carriageway's geometry; congestion uses the inbound flow at the location, so the values do not depend on which carriageway is drawn.

