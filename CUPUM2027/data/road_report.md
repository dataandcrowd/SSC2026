# Cordon-Lite road congestion inputs (prep.build_roads)

## Summary

- Sections: 5903 on the pre-gate parts of 3000 origin paths (19517 graph edges, 849.4 km, 879.3 free-flow minutes); 142470 origin-section rows, 47.5 sections per origin on average (max 124).
- The rebuilt prep paths reproduce `data/origins.csv` exactly (gate_id, corridor_id, free-flow minutes); per-origin sum of section ff_min minus fftt_to_gate_min: max abs 2.66e-14 min.
- Capacity factor k = 0.076904 (cap_vph = k x adt_dir), bisected in [0.02, 0.3] so that the origin-weighted travel time index of departures 08:00-08:59 under usual traffic is 1.714 (achieved 1.7140).
- Usual-traffic V/C is 2 x 0.6 x peak_ratio x r(m) / k on every section; with the default peak ratio 0.096 that is 1.50 x r(m).

## Travel time index under usual traffic

Probe car on each origin's pre-gate route (adds no load), one departure per minute, origin-weighted mean of (time to the gate) / (free-flow time to the gate).

| departures | TTI |
|---|---|
| 06:00-06:59 | 1.044 |
| 07:00-07:59 | 1.424 |
| 08:00-08:59 | 1.714 |
| 09:00-09:59 | 1.203 |
| 07:30 only | 1.421 |

By corridor (departures in the calibration window):

| corridor | name | origins | TTI |
|---|---|---|---|
| 0 | East (The Strand, Gladstone Road) | 68 | 1.872 |
| 1 | South-east (Alten Road, Parnell Rise) | 901 | 1.719 |
| 2 | South (Wellesley Street ramp) | 723 | 1.678 |
| 3 | South-west (Northern Motorway ramp, Helensville ramp) | 701 | 1.722 |
| 4 | West (Fanshawe Street ramp, Westhaven Drive) | 607 | 1.730 |

## Count matching

- Count points: 13835 in `../../SSC2026/netlogo/Data/Average_Daily_Traffic_Counts.geojson`, 13717 with adt > 0 (local 13165, SH carriageway 276, SH ramp 257, SH without direction 11, not used; 8 SH ramp records of bus-only ramps or busways (named so, or under 50% cars) are not used).
- Matched to a same-name graph edge within 30 m and used: 3179 (local 2741, SH carriageway 230, SH ramp 208). Not used: 66 matched AT counts below 0.25 of a more recent count of the same street within 1000 m (stale or misplaced counts). Graph edges holding a count: 3110; propagated within 1000 m: 25954; default: 1771 (of 30835 graph edges).
- Sections take adt_source 'count' when one of their edges holds a count, 'propagated' when their values come from a count on the same street, else 'default' (median two-way ADT of count edges with the same frc and speed band, else frc).

Coverage by frc (share of sections | share of origin-weighted pre-gate free-flow minutes):

| frc | sections | count | propagated | default | minutes share of all | count | propagated | default |
|---|---|---|---|---|---|---|---|---|
| 0 | 296 | 51.4% | 42.6% | 6.1% | 55.4% | 80.0% | 17.5% | 2.5% |
| 1 | 181 | 29.8% | 56.4% | 13.8% | 1.2% | 49.0% | 47.6% | 3.3% |
| 2 | 1189 | 35.5% | 59.4% | 5.1% | 20.2% | 61.7% | 23.7% | 14.7% |
| 3 | 2076 | 31.9% | 65.3% | 2.8% | 14.8% | 52.7% | 45.4% | 2.0% |
| 4 | 2161 | 36.7% | 58.4% | 4.8% | 8.3% | 66.4% | 31.9% | 1.7% |
| all | 5903 | 35.3% | 60.2% | 4.5% | 100.0% | 70.8% | 24.5% | 4.8% |

- AM peak ratio from a count with an AM peak hour (06:00-09:45): 1446 sections (8.5% of origin-weighted pre-gate minutes); the others use 0.096. Peak ratio over sections (min | p10 | median | p90 | max): 0.070 | 0.096 | 0.096 | 0.106 | 0.200.

## V/C under usual traffic

V/C = obs_peak_vph x r(m) / cap_vph (background plus usual commuters, what the counts say). Median over sections and origin-weighted mean over traversal minutes.

| frc | sections | median 07:30 | median 08:15 | weighted 07:30 | weighted 08:15 |
|---|---|---|---|---|---|
| 0 | 296 | 1.23 | 1.54 | 1.23 | 1.54 |
| 1 | 181 | 1.23 | 1.54 | 1.27 | 1.60 |
| 2 | 1189 | 1.23 | 1.54 | 1.22 | 1.54 |
| 3 | 2076 | 1.23 | 1.54 | 1.25 | 1.57 |
| 4 | 2161 | 1.23 | 1.54 | 1.25 | 1.57 |

Speed factor f = 1 / (1 + 0.15 (V/C)^4), at least 0.18; time on a section = ff_min / f.

## Commuter share of the counted volume

expected_commuter_veh = 19000 x 0.8 x (origin weight using the section) / (all origin weight); phi = min(1, expected / observed 06:00-10:00 volume); bg_peak_vph = obs_peak_vph x (1 - phi); w_factor = min(1, observed / expected).

| quantity | min | p10 | median | p90 | max |
|---|---|---|---|---|---|
| phi | 0.000 | 0.001 | 0.010 | 0.064 | 1.000 |
| w_factor | 0.422 | 1.000 | 1.000 | 1.000 | 1.000 |
| expected_commuter_veh | 1 | 4 | 22 | 216 | 4487 |
| am_volume_veh | 15 | 1207 | 2728 | 5909 | 37189 |

- Sections where the commuters reach the whole counted volume (phi = 1, w_factor < 1): 3 (0.1% of sections, 0.8% of origin-weighted pre-gate minutes).
- Origin-weighted mean phi over pre-gate minutes: 0.137.
- Data check: 15 sections have cap_vph below 50 veh/h (very small counts, e.g. Albany Heights Road, O'Brien Road, Ridge Road, Sturges Road, Williams Road); 0.04% of origin-weighted pre-gate minutes.

## Sections used by the most origins

| section | street | frc | speed | ff_min | origins | adt_twoway | source | peak_ratio | phi | w_factor | V/C 08:15 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 162 | Alten Road | 4 | 30 | 0.06 | 834 | 13611 | propagated | 0.079 | 1.000 | 0.422 | 1.26 |
| 160 | Stanley Street | 1 | 50 | 0.09 | 833 | 55866 | count | 0.096 | 0.472 | 1.000 | 1.54 |
| 161 | Stanley Street | 1 | 50 | 0.04 | 833 | 22621 | propagated | 0.128 | 0.875 | 1.000 | 2.05 |
| 158 | Northwestern Motorway | 0 | 80 | 0.22 | 832 | 44198 | count | 0.096 | 0.596 | 1.000 | 1.54 |
| 159 | Stanley Street | 0 | 50 | 0.14 | 832 | 55866 | propagated | 0.096 | 0.471 | 1.000 | 1.54 |
| 157 | Northwestern Motorway | 0 | 80 | 0.08 | 810 | 44198 | propagated | 0.096 | 0.579 | 1.000 | 1.54 |
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
- [A] Capacity = k x directional ADT (SSC2026 rule) with k calibrated to the TomTom Traffic Index [DATA]: Auckland 2025 morning rush-hour congestion level 71.4% => TTI 1.714 (https://www.tomtom.com/traffic-index/auckland-traffic/).
- [A] BPR alpha 0.15, beta 4, speed floor 0.18 (SSC2026); commuter flow counts the cars that entered in the last 15 min.
- [A] Commuters are netted out of the counts with car share 0.8 of 19000 represented vehicles; where all-or-nothing routing puts more commuter cars on a section than counted, their weight w_factor is reduced instead.
- [A] Routing is undirected: many motorway traversals follow the opposite carriageway's geometry; congestion uses the inbound flow at the location, so the values do not depend on which carriageway is drawn.

