# Cordon-Lite prep report

## Inputs and counts

- Roads: `../netlogo/Data/roads/tomtom_major_roads.gpkg` layer `tomtom`, 46965 segments.
- Graph: endpoints rounded to 1 m; 28520 nodes, 30846 edges, 3 components; giant component 28507 nodes, 30835 edges. Self-loops dropped: 0; parallel segments collapsed to the fastest: 16119.
- Cordon: SA3 ['Auckland City Centre'] from `../netlogo/Data/roads/akl_CBD_SA3.gpkg`, area 4.42 km2, perimeter 22.00 km; graph nodes inside: 1106.
- Destination node (inside cordon, nearest centroid): (1757409, 5920504), 89 m from the centroid.
- Candidate origins: 21047 nodes outside the cordon, not motorway-only, with positive weight (2023 Census car drivers into the cordon by home SA2, data/od_sa2.csv, within SA2: proxy).
- Census OD: 561 home SA2s, 27101 drivers; 116 SA2s (2355 drivers, 8.7%) have no candidate node inside and go to the node nearest their representative point; of these, 92 lie more than 2 km from it (1614 drivers, 6.0%, beyond the TomTom extent: their trip starts at the network edge).
  Largest: Kumeu-Huapai North 110 drivers, 5.6 km, Riverhead 72 drivers, 3.4 km, Laingholm 58 drivers, 3.1 km, Kumeu-Huapai South 54 drivers, 4.1 km, Millwater Central 45 drivers, 9.3 km, Millwater South 42 drivers, 8.1 km, Karaka Lakes 38 drivers, 3.2 km, Orewa North 34 drivers, 11.4 km.
- Sampled origins: 2361 distinct nodes from 3000 independent draws in proportion to the weight (`prep.origin_draw = "iid"`; weight = draws per node, max 57), seed 11, stream ('prep',).
- Gates used: 23 distinct segments; corridors: 5.

## Corridors

| id | name | gates | raw capacity veh/h | bearing | origins | draws | share of draws | median fftt total (min) |
|---|---|---|---|---|---|---|---|---|
| 0 | East (The Strand, Gladstone Road) | 5 | 7700 | 89 | 155 | 198 | 6.6% | 12.4 |
| 1 | South-east (Alten Road, Parnell Rise) | 3 | 2700 | 124 | 506 | 596 | 19.9% | 11.1 |
| 2 | South (Wellesley Street ramp) | 1 | 1500 | 186 | 313 | 396 | 13.2% | 14.0 |
| 3 | South-west (Northern Motorway ramp, Helensville ramp) | 9 | 17700 | 219 | 843 | 1072 | 35.7% | 11.5 |
| 4 | West (Fanshawe Street ramp, Beaumont Street) | 5 | 7700 | 288 | 544 | 738 | 24.6% | 11.6 |

Gates (most used first, top 15):

| gate | corridor | street | frc | speed | origins |
|---|---|---|---|---|---|
| 20 | 3 | Exit 4A Northern Motorway | 0 | 80 | 713 |
| 3 | 1 | Alten Road | 4 | 30 | 451 |
| 13 | 4 | Entry 424 Fanshawe Street | 1 | 40 | 388 |
| 21 | 2 | Exit 429B Wellesley Street | 2 | 80 | 313 |
| 12 | 0 | The Strand | 2 | 50 | 150 |
| 16 | 4 | Exit 424A Fanshawe Street | 1 | 80 | 145 |
| 15 | 3 | Exit 424D Helensville | 0 | 80 | 93 |
| 11 | 1 | Parnell Rise | 2 | 50 | 43 |
| 17 | 3 | Hopetoun Street | 3 | 40 | 22 |
| 8 | 1 | Alten Road | 4 | 50 | 12 |
| 7 | 4 | Beaumont Street | 4 | 30 | 9 |
| 5 | 3 | Karangahape Road | 2 | 50 | 5 |
| 18 | 3 | Wellington Street | 4 | 30 | 5 |
| 0 | 0 | Gladstone Road | 4 | 50 | 2 |
| 2 | 3 | Union Street | 4 | 30 | 2 |

## Free-flow time and distance distribution

| quantity | min | p5 | p25 | median | p75 | p95 | max | mean |
|---|---|---|---|---|---|---|---|---|
| fftt to gate (min) | 0.0 | 1.8 | 5.3 | 8.7 | 12.1 | 16.2 | 22.2 | 8.8 |
| fftt gate to destination (min) | 2.2 | 2.2 | 2.8 | 3.1 | 3.9 | 3.9 | 4.3 | 3.2 |
| fftt total (min) | 2.3 | 5.0 | 8.3 | 11.8 | 15.4 | 19.0 | 24.4 | 12.0 |
| path length (km) | 1.1 | 3.9 | 7.8 | 12.0 | 17.5 | 23.2 | 31.3 | 12.8 |
| crow-fly origin to destination (km) | 0.9 | 2.5 | 5.5 | 8.5 | 12.8 | 18.6 | 28.0 | 9.4 |

## Checks

- Origins inside the cordon: 0 (must be 0).
- Gate crossing points: max distance to the cordon boundary 0.000 m; gate segments whose geometry stops short of the boundary (rounded node inside, segment end outside): 1, max gap 0.18 m (gate point snapped to the boundary).
- Gate inside-end node distance to the boundary: median 1 m, max 31 m.
- Paths entering the cordon more than once (leave and re-enter after the first gate): 542 origins (23.0%). Gate rule `first_entry`; origins whose first-entry and last-entry gates differ: 542.
- Origins less than 1 min (free flow) from their gate: 54 (inner suburbs next to the cordon; kept, persona rounds fftt_to_gate_min up to at least 1).
- Gates on motorway (frc 0): 3 gates serving 807 origins.
- Ratio path km / crow-fly km: median 1.35.

## Assumptions

- [SPEC] Undirected graph: TomTom major roads carry no one-way or lane information, so every segment is usable in both directions (paths may use ramps the wrong way).
- [A] Free-flow minutes = distance / speed limit x ff_factor (1); no junction delay.
- [SPEC] Graph nodes are segment endpoints rounded to the grid above; segments whose rounded endpoints coincide are dropped; parallel segments between the same two nodes keep the fastest.
- [A] Origins are graph nodes (TomTom extent = Auckland urban extent), outside the cordon, excluding nodes whose incident segments are all motorway (frc 0).
- [DATA] Origin weights: 2023 Census car drivers (`prep.od_modes`) who live outside the cordon and work in it, by home SA2 (`data/od_sa2.csv`, written by `prep.build_od`; see `od_report.md`). [A] Within an SA2 (proxy): its drivers are split over its candidate nodes in proportion to the length of frc [3, 4] road whose segment midpoint lies within 500 m of the node; an SA2 with no candidate node inside goes to the node nearest its representative point.
- [SPEC] Destination = the graph node inside the cordon nearest to the cordon centroid; every commuter drives to this one node, so fftt gate-to-destination is a city-centre internal leg.
- [SPEC] Gate rule `first_entry`. `first_entry`: the first edge on the origin-to-destination path whose far end is inside the cordon. `last_entry` [A]: the final outside-to-inside crossing, after which the path stays inside. They differ only for paths that touch the SA3 boundary and leave again (the SH1 Wellesley Street off-ramp, which the undirected graph then follows back out via the Port ramp and Alten Road, and the zig-zag boundary along The Strand). With `first_entry` these multi-entry paths keep their first touch (mostly the Wellesley Street ramp gate, also The Strand and Parnell Rise), spend under about 1.2 min outside and re-enter at Alten Road; the origins assigned to the Alten Road gate itself are single-entry paths from the south-east. Gate coordinates are where the gate segment crosses the cordon boundary (nearest boundary point if node rounding leaves it short).
- [A] Corridors = weighted k-means (weights = origins served, k = 5) on unit bearing vectors from the cordon centroid to the gate points, deterministic multi-start; corridor ids run clockwise from north; corridor bearing is the weighted circular mean; name = 8-point compass sector plus the two most-used street names.
- [A] Raw corridor capacity = sum over its gates of per-frc capacity [4000.0, 2500.0, 1500.0, 900.0, 600.0] veh/h (frc 0..4). The engine uses `engine.capacity_mode` to turn this into agents/min.
- [A] Corridor x, y = unweighted mean of its gate crossing points.
