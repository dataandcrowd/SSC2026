# Cordon-Lite prep report

## Inputs and counts

- Roads: `../netlogo/Data/roads/tomtom_major_roads.gpkg` layer `tomtom`, 46965 segments.
- Graph: endpoints rounded to 1 m; 28520 nodes, 30846 edges, 3 components; giant component 28507 nodes, 30835 edges. Self-loops dropped: 0; parallel segments collapsed to the fastest: 16119.
- Cordon: SA3 ['Auckland City Centre'] from `../netlogo/Data/roads/akl_CBD_SA3.gpkg`, area 4.42 km2, perimeter 22.00 km; graph nodes inside: 1106.
- Destination node (inside cordon, nearest centroid): (1757409, 5920504), 89 m from the centroid.
- Candidate origins: 23772 nodes outside the cordon, not motorway-only, with positive weight (local road length proxy, frc [3, 4], 500 m).
- Sampled origins: 3000 (distinct nodes 3000), seed 11, stream ('prep',), replacement False.
- Gates used: 27 distinct segments; corridors: 5.

## Corridors

| id | name | gates | raw capacity veh/h | bearing | origins | share | median fftt total (min) |
|---|---|---|---|---|---|---|---|
| 0 | East (The Strand, Gladstone Road) | 4 | 7100 | 89 | 68 | 2.3% | 14.0 |
| 1 | South-east (Alten Road, Parnell Rise) | 4 | 3600 | 125 | 901 | 30.0% | 14.1 |
| 2 | South (Wellesley Street ramp) | 1 | 1500 | 186 | 723 | 24.1% | 15.4 |
| 3 | South-west (Northern Motorway ramp, Helensville ramp) | 11 | 19500 | 219 | 701 | 23.4% | 12.0 |
| 4 | West (Fanshawe Street ramp, Westhaven Drive) | 7 | 9800 | 289 | 607 | 20.2% | 12.2 |

Gates (most used first, top 15):

| gate | corridor | street | frc | speed | origins |
|---|---|---|---|---|---|
| 2 | 1 | Alten Road | 4 | 30 | 834 |
| 26 | 2 | Exit 429B Wellesley Street | 2 | 80 | 723 |
| 25 | 3 | Exit 4A Northern Motorway | 0 | 80 | 582 |
| 17 | 4 | Entry 424 Fanshawe Street | 1 | 40 | 419 |
| 19 | 4 | Exit 424A Fanshawe Street | 1 | 80 | 178 |
| 18 | 3 | Exit 424D Helensville | 0 | 80 | 81 |
| 16 | 0 | The Strand | 2 | 50 | 61 |
| 12 | 1 | Alten Road | 4 | 50 | 43 |
| 15 | 1 | Parnell Rise | 2 | 50 | 23 |
| 21 | 3 | Wellington Street | 4 | 30 | 12 |
| 20 | 3 | Hopetoun Street | 3 | 40 | 10 |
| 0 | 0 | Gladstone Road | 4 | 50 | 5 |
| 6 | 3 | Karangahape Road | 2 | 50 | 4 |
| 9 | 4 | Westhaven Drive | 4 | 30 | 4 |
| 1 | 3 | Union Street | 4 | 30 | 3 |

## Free-flow time and distance distribution

| quantity | min | p5 | p25 | median | p75 | p95 | max | mean |
|---|---|---|---|---|---|---|---|---|
| fftt to gate (min) | 0.0 | 1.6 | 6.6 | 10.3 | 13.4 | 16.6 | 22.2 | 9.9 |
| fftt gate to destination (min) | 2.2 | 2.2 | 2.2 | 3.1 | 3.6 | 3.9 | 4.4 | 3.0 |
| fftt total (min) | 2.3 | 4.4 | 9.9 | 13.2 | 16.3 | 19.3 | 24.4 | 12.9 |
| path length (km) | 1.1 | 3.2 | 10.1 | 14.9 | 19.8 | 25.5 | 31.3 | 14.8 |
| crow-fly origin to destination (km) | 0.8 | 2.0 | 7.3 | 11.4 | 14.8 | 21.1 | 27.6 | 11.3 |

## Checks

- Origins inside the cordon: 0 (must be 0).
- Gate crossing points: max distance to the cordon boundary 0.000 m; gate segments whose geometry stops short of the boundary (rounded node inside, segment end outside): 1, max gap 0.27 m (gate point snapped to the boundary).
- Gate inside-end node distance to the boundary: median 1 m, max 31 m.
- Paths entering the cordon more than once (leave and re-enter after the first gate): 834 origins (27.8%). Gate rule `first_entry`; origins whose first-entry and last-entry gates differ: 834.
- Origins less than 1 min (free flow) from their gate: 96 (inner suburbs next to the cordon; kept, persona rounds fftt_to_gate_min up to at least 1).
- Gates on motorway (frc 0): 3 gates serving 666 origins.
- Ratio path km / crow-fly km: median 1.32.

## Assumptions

- [SPEC] Undirected graph: TomTom major roads carry no one-way or lane information, so every segment is usable in both directions (paths may use ramps the wrong way).
- [A] Free-flow minutes = distance / speed limit x ff_factor (1); no junction delay.
- [SPEC] Graph nodes are segment endpoints rounded to the grid above; segments whose rounded endpoints coincide are dropped; parallel segments between the same two nodes keep the fastest.
- [A] Origins are graph nodes (TomTom extent = Auckland urban extent), outside the cordon, excluding nodes whose incident segments are all motorway (frc 0).
- [A] Residential-density proxy: length of frc [3, 4] road whose segment midpoint lies within 500 m of the node. With `prep.od_csv` set, SA2 commuter counts snapped to the nearest candidate node replace the proxy.
- [SPEC] Destination = the graph node inside the cordon nearest to the cordon centroid; every commuter drives to this one node, so fftt gate-to-destination is a city-centre internal leg.
- [SPEC] Gate rule `first_entry`. `first_entry`: the first edge on the origin-to-destination path whose far end is inside the cordon. `last_entry` [A]: the final outside-to-inside crossing, after which the path stays inside. They differ only for paths that touch the SA3 boundary and leave again (the SH1 Wellesley Street off-ramp, which the undirected graph then follows back out via the Port ramp and Alten Road, and the zig-zag boundary along The Strand). With `first_entry` these multi-entry paths keep their first touch (mostly the Wellesley Street ramp gate, also The Strand and Parnell Rise), spend under about 1.2 min outside and re-enter at Alten Road; the origins assigned to the Alten Road gate itself are single-entry paths from the south-east. Gate coordinates are where the gate segment crosses the cordon boundary (nearest boundary point if node rounding leaves it short).
- [A] Corridors = weighted k-means (weights = origins served, k = 5) on unit bearing vectors from the cordon centroid to the gate points, deterministic multi-start; corridor ids run clockwise from north; corridor bearing is the weighted circular mean; name = 8-point compass sector plus the two most-used street names.
- [A] Raw corridor capacity = sum over its gates of per-frc capacity [4000.0, 2500.0, 1500.0, 900.0, 600.0] veh/h (frc 0..4). The engine uses `engine.capacity_mode` to turn this into agents/min.
- [A] Corridor x, y = unweighted mean of its gate crossing points.
