# Cordon-Lite Census OD report

Source: Stats NZ, 2023 Census main means of travel to work by statistical area 2 (`../../gtfs-isochrone/data/census/2023-census-main-means-of-travel-to-work-by-statistical-area.csv`), SA2 polygons `../../gtfs-isochrone/data/sa2/auckland_sa2.gpkg` (codes `SA22026_V1_00`). Licensed CC BY 4.0 by Stats NZ.

## Definitions

- Workplace SA2s in the cordon (17): Anzac Avenue, Auckland-University, Hobson Ridge Central, Hobson Ridge North, Hobson Ridge South, Karangahape East, Karangahape West, Quay Street-Customs Street, Queen Street, Queen Street South West, Shortland Street, Symonds Street East, Symonds Street North West, Symonds Street West, The Strand, Victoria Park, Wynyard-Viaduct.
- Commuters: usual residence outside the cordon, workplace in the cordon.
- Drivers: `2023_Drive_a_private_car_truck_or_van` + `2023_Drive_a_company_car_truck_or_van`.
- Suppressed cells (-999, a count of 0 to 5): the pair's residual (Total_stated minus shown cells) split by the outside-to-cordon mode shares of the shown cells, at most 5 per cell; a pair whose total is suppressed is given 3 commuters [A].

## Totals

- Residence x workplace pairs: 4476; with the total suppressed: 1049.
- Driver cells: 8952, suppressed: 7104.
- Commuters, shown totals: 60018.
- Drivers, shown cells only (a lower bound): 19887.
- Drivers with suppressed cells filled: 27215 (7328 imputed, of which 1579 in pairs whose total is suppressed).
- Residence SA2s with drivers and a polygon: 561, drivers 27101.
- Residence SA2s with drivers but no polygon in `../../gtfs-isochrone/data/sa2/auckland_sa2.gpkg` (dropped): 14, drivers 113.8 (One Tree Point 3.0, Mangawhai Heads 12.0, Oneroa West 12.1, Oneroa East-Palm Beach 7.7, Surfdale 4.7, Ostend 8.0, Onetangi 7.7, Waiheke East 3.1, Aka Aka 3.0, Tuakau North 3.0, Onewhero 3.0, Pokeno North 21.0, Pokeno South 21.0, Marlborough Sounds West 4.5).
- For comparison, `engine.agents_represented` = 19000 cars entering in the charged morning hours (AT/AC option 1a): the Census table has no time of day, so it counts drivers to a cordon workplace whenever they travel.

## Commuters by mode (outside to cordon)

| mode | shown | with suppressed cells filled | share of shown |
|---|---|---|---|
| Work_at_home | 0 | 0 | 0.000 |
| Drive_a_private_car_truck_or_van | 19845 | 27106 | 0.501 |
| Drive_a_company_car_truck_or_van | 42 | 109 | 0.001 |
| Passenger_in_a_car_truck_van_or_company_bus | 21 | 54 | 0.001 |
| Public_bus | 13455 | 21077 | 0.340 |
| Train | 2478 | 5729 | 0.063 |
| Bicycle | 438 | 1080 | 0.011 |
| Walk_or_jog | 1611 | 3820 | 0.041 |
| Ferry | 1605 | 3947 | 0.041 |
| Other | 132 | 338 | 0.003 |

## Drivers by crow-fly distance from the cordon centroid

| km | drivers | share |
|---|---|---|
| 0-5 | 5122 | 18.9% |
| 5-10 | 10029 | 37.0% |
| 10-15 | 7062 | 26.1% |
| 15-20 | 2486 | 9.2% |
| 20-30 | 1978 | 7.3% |
| 30-50 | 351 | 1.3% |
| 50-1000 | 74 | 0.3% |

Top 15 residence SA2s by drivers:

| SA2 | name | drivers (shown) | drivers |
|---|---|---|---|
| 129700 | Herne Bay | 174 | 194.8 |
| 140000 | Remuera Waitaramoa | 159 | 172.4 |
| 131200 | Ponsonby East | 129 | 167.2 |
| 138400 | Mount Eden West | 144 | 165.9 |
| 143500 | Saint Heliers South | 150 | 163.8 |
| 132800 | Grey Lynn Central | 129 | 161.0 |
| 133600 | Morningside (Auckland) | 126 | 160.3 |
| 129902 | Point Chevalier East | 132 | 152.4 |
| 124800 | Te Atatu Peninsula West | 138 | 150.3 |
| 137400 | Parnell East | 126 | 149.9 |
| 140500 | Remuera North | 132 | 149.0 |
| 130300 | Westmere South-Western Springs | 132 | 149.0 |
| 144001 | Glendowie North | 141 | 148.9 |
| 131600 | Grey Lynn North | 108 | 143.5 |
| 142700 | Saint Heliers West | 138 | 142.8 |
