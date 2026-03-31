; Include any necessary libraries
extensions [gis nw  csv]
__includes ["akl_vehicles.nls" "akl_nodes.nls" "akl_buildings.nls" "akl_boundary.nls"]

; monitors
globals [
  all-periods
  all-delays
  n-trips-list
]


; Set up the simulation
to setup
  if control-seed? [random-seed current-seed]
  clear-all  ; Clear any existing data
  set all-periods (list)
  set all-delays (list)
  set n-trips-list (list)
  ask patches[ set pcolor white ]
  load-network
  load-buildings
  vehicles-init number_of_vehicles ; Initialize vehicles
  ask vehicles [if b-destinations != 0 [set n-trips-list lput (length b-destinations) (n-trips-list)] ]
  reset-ticks ; Reset the tick counter
  reset-timer
;  go
end


; Advance the simulation by one tick
to go
  let flag true
  ask roads [
    set current_speeds (list)
  ]
  ask vehicles [
    let pre-period periods
    let pre-delay delays
    vehicles-move ; Move the vehicles
    let post-period periods
    let post-delay delays
    if pre-period != post-period [
      set all-periods lput (last post-period) (all-periods)
      set all-delays lput (last post-delay) (all-delays)
    ]
    if active? = true[
      set flag false
    ]
  ]
  if flag = true [
;    if ticks > 0 [type timer type "\n"]
    stop
  ]
  tick ; Advance the tick counter
end

to go-infinite
  let flag true
  ask vehicles [
    let pre-period periods
    let pre-delay delays
    vehicles-move ; Move the vehicles
    let post-period periods
    let post-delay delays
    if pre-period != post-period [
      set all-periods lput (last post-period) (all-periods)
      set all-delays lput (last post-delay) (all-delays)
    ]
    if active? = true[
      set flag false
    ]
  ]
  tick ; Advance the tick counter
  if flag = true [
;    if ticks > 0 [type timer type "\n"]
    if control-seed? [set current-seed current-seed + 1]
    setup
  ]

end


; Public Domain:
; adapted from code by Uri Wilensky
; To the extent possible under law, ric colasanti has waived all
; copyright and related or neighboring rights to this model.
@#$#@#$#@
GRAPHICS-WINDOW
210
25
778
594
-1
-1
5.545
1
10
1
1
1
0
0
0
1
0
100
0
100
1
1
1
ticks
30.0

BUTTON
25
570
195
603
NIL
setup
NIL
1
T
OBSERVER
NIL
NIL
NIL
NIL
1

BUTTON
25
640
195
673
go
go
T
1
T
OBSERVER
NIL
NIL
NIL
NIL
0

BUTTON
25
605
195
638
go once
go
NIL
1
T
OBSERVER
NIL
NIL
NIL
NIL
0

SLIDER
25
25
195
58
number_of_vehicles
number_of_vehicles
0
500
500.0
20
1
NIL
HORIZONTAL

SLIDER
25
60
195
93
slowest-vehicle
slowest-vehicle
0.1
1.0
0.4
0.1
1
NIL
HORIZONTAL

SLIDER
25
95
195
128
max-n-activities
max-n-activities
1
4
4.0
1
1
NIL
HORIZONTAL

BUTTON
25
675
195
708
go-infinite
go-infinite
T
1
T
OBSERVER
NIL
NIL
NIL
NIL
1

PLOT
785
25
1070
175
Average time per trip
Time step
Trip time
0.0
10.0
0.0
10.0
true
false
"" ""
PENS
"default" 1.0 0 -16777216 true "" "ifelse all-periods != (list) [plot mean all-periods] [plot 0]"

PLOT
785
175
1070
335
Trip time histogram
Time step
Vehicle
0.0
1000.0
0.0
10.0
true
false
"" ""
PENS
"default" 1.0 1 -16777216 true "" "histogram all-periods\nset-histogram-num-bars 100"

PLOT
785
595
1070
715
Number of planned trips histogram
NIL
NIL
0.0
5.0
0.0
10.0
true
false
"" ""
PENS
"default" 1.0 1 -16777216 true "" "histogram n-trips-list\n"

SWITCH
25
255
195
288
return-home?
return-home?
0
1
-1000

PLOT
785
465
1070
595
Number of activity modification requests
Time step
Vehicle
0.0
10.0
0.0
10.0
true
false
"" ""
PENS
"default" 1.0 0 -16777216 true "" "plot count vehicles with [modify? = true]"

SLIDER
210
675
380
708
current-seed
current-seed
0
1000
11.0
1
1
NIL
HORIZONTAL

SWITCH
210
640
380
673
control-seed?
control-seed?
0
1
-1000

SLIDER
25
295
197
328
w1
w1
0
1
0.4
0.05
1
NIL
HORIZONTAL

SLIDER
25
330
197
363
w2
w2
0
1
0.3
0.05
1
NIL
HORIZONTAL

SLIDER
25
365
197
398
w3
w3
0
1
0.2
0.05
1
NIL
HORIZONTAL

SLIDER
25
400
197
433
w4
w4
0
1
0.1
0.05
1
NIL
HORIZONTAL

SLIDER
25
435
197
468
w-std
w-std
0
0.2
0.02
0.01
1
NIL
HORIZONTAL

SLIDER
24
528
196
561
mean-tolerance
mean-tolerance
0
1
0.1
0.05
1
NIL
HORIZONTAL

SLIDER
25
150
195
183
max-activity-duration
max-activity-duration
0
500
100.0
10
1
ticks
HORIZONTAL

SLIDER
25
220
195
253
max-buffer-period
max-buffer-period
0
100
40.0
5
1
NIL
HORIZONTAL

SLIDER
24
493
196
526
min-delay-threshold
min-delay-threshold
0
20
20.0
1
1
NIL
HORIZONTAL

PLOT
785
335
1070
465
Delays histogram
NIL
NIL
-200.0
300.0
0.0
10.0
true
false
"" ""
PENS
"default" 1.0 1 -16777216 true "" "histogram all-delays\nset-histogram-num-bars 100"

TEXTBOX
25
470
205
490
Minimum delay threshold at which an activity modification is requested is only reached if w = 1
8
0.0
1

TEXTBOX
25
130
190
150
Maximum number of ticks a vehicle spends at an activity (i.e., at a building)
8
0.0
1

TEXTBOX
30
185
190
220
Maximum number of ticks that the vehicle moves earlier than it should to reach its next building destination
8
0.0
1

TEXTBOX
215
610
385
630
Control the seed value (Note that go-infinite increments the current-seed value every tick)
8
0.0
1

SWITCH
450
645
612
678
show-boundary?
show-boundary?
1
1
-1000

@#$#@#$#@
Overview
--------

This is a NetLogo model that simulates the movement of vehicles on a road network. The model includes three types of agents: nodes, buildings, and vehicles. Nodes represent intersections in the road network, buildings represent buildings in the environment, and vehicles move along the links between nodes. The model includes features such as speed limits, random maximum speeds for vehicles, and collision avoidance.

Design Concepts
--------------

* **Spatial Extent:** The model is defined on a two-dimensional grid, with nodes, links, and buildings representing intersections, roads, and buildings, respectively.
* **Temporal Extent:** The model operates in discrete time steps, or ticks. At each tick, vehicles move along the links between nodes and update their speed based on local conditions.
* **Stochasticity:** The model includes randomness in the form of random maximum speeds for vehicles and the selection of destinations.
* **Collectives:** The model simulates the collective behavior of vehicles moving on a road network.
* **Observation:** The model includes a visualization of the road network, buildings, and the movement of vehicles.

Details
-------

### Entities, States, and Variables

* **Nodes:** Nodes represent intersections in the road network. They have a position on the grid, a list of links connected to them, and a unique ID.
* **Links:** Links represent roads between intersections. They have a distance to the destination, a speed limit, a color, a thickness, and a unique ID.
* **Buildings:** Buildings represent physical structures in the environment. They have a position on the grid, a unique ID, and a type (e.g. residential, commercial, etc.).
* **Vehicles:** Vehicles represent individual agents moving on the road network. They have a position on the grid, a destination, a maximum speed, a current speed, a local speed restriction, a journey distance to their destination, a remaining journey distance, a path to the ultimate destination, and a flag indicating whether they are moving.

### Process Overview and Scheduling

The model operates in two main procedures: `setup` and `go`. `Setup` initializes the nodes, buildings, and vehicles, and `go` advances the simulation by one tick.

### Initialization

At the beginning of the simulation, the setup procedure initializes the nodes, buildings, and vehicles. The load-network procedure generates a network of nodes and links using the network extension and the links CSV file. It then sets the links. The load-buildings procedure creates a specified number of buildings and assigns them random starting points and destinations. It also calculates the shortest path between the starting point and destination and sets the initial speed and remaining journey distance. A journey is between a home (blue) and a building (red).
   
When the vehicles start their journey, they can only move to the nearest road node if it is unoccupied by other vehicles. This ensures that the vehicles do not collide with each other as they begin their travels, promoting a more realistic simulation of traffic flow.

### Input

The user can specify the number of vehicles in the model by setting the number_of_vehicles sliders in the interface. Additionally, you can set the speed of the slowest vehicle and the overall run speed, which is the maximum speed of any vehicle. This helps to speed up the simulation for experimental purposes only.

### Submodels

The `go` procedure advances the simulation by one tick. It first checks whether any vehicles have reached their destinations and stops them if they have. It then moves the remaining vehicles along the links between nodes and updates their speed based on local conditions.

The `check-ahead` procedure checks whether there are any vehicles ahead of the calling vehicle and adjusts its speed accordingly. The `move-at-correct-speed` procedure checks whether the speed of the vehicle is greater than the speed limit for the road and adjusts it if necessary.

### Output

The model includes a visualization of the road network, buildings, and the movement of vehicles. The user can observe the behavior of the vehicles and the impact of different parameters on their movement.

Versions history
----------------

### 1.0.0
Version described above. Cloned from the GitHub repository on 05 March 2025

### 1.0.1
1. Added more than one destination
	- Added the following parameters to vehicles:
		- `b-destinations`
		- `i-destination`
		- `activity`
	- Added the following parameter in the interface
		- `max-n-activities`
2. Added a measure of the time taken to each b-destination
	- Added `time` paramter to vehicles
	- Added a monitor for the time taken per trip
3. Added a `go-infinite` button which reapplies `setup` once all the vehicles have reached all their destinations

### 1.0.2
1. Vehicles move back home before the end of the run
	- Added the following parameter in the interface
		- `return-home?`
2. Vehicles request modifications to their activities
	- Added the following parameters to vehicles:
		- `intolerance`
		- `activity-weight`
	- Added the following function to calculate the time threshold for modification
		- `time-threshold`
	- Added a monitor for the number of vehicles requesting an activity modification

### 1.0.3 (29/05/2025)
1. Addressed a bug leading to the destination not being set at the beginning of the trips if the vehicle's first 2 (or more) destinations in `b-destinations` happen to have the same closest node as that of the vehicles home. 
	- Vehicles now keep on checking their `b-destinations` in order until they find one whose closest node is not the same as the closest node to their home.
	- If all the destinations in `b-destinations` are not sufficient (meaning, all the destinations are very close to home), the vehicle does not move and stays home.
2. Added the capability to control the seed of the run
	- Added the following parameters in the interface
		- `control-seed?`
		- `current-seed`
	- `go-infinite` now increments the `current-seed` by 1 after the completion of each run (if `control-seed?` is on)
3. Renamed the `intolerance` parameter to `tolerance` to reflect its mathematical impact on the time thresholds at which vehicles request a change in activities.
4. Added the capability to control the weights of the activities and tolerance per vehicle (maximum number of activities is capped at 4).
	- The weights and tolerance are drawn for normal distributions.
	- Added the following parameters in the interface
		- `w1`
		- `w2`
		- `w3`
		- `w4`
		- `w-std`
		- `mean-tolerance`
5. Added monitoring parameters for the activities and their respective times and weights at which a vehicle request a change in activity
	- Added the following global parameters in the vehicles.nls file
		- `activity-record`
		- `time-record`
		- `threshold-record`
		- `weight-record`

### 1.0.4 (16/06/2025)

1. Vehicles allocate the time they took to finish a road network to that road network
	- Added `current_period` parameter to the roads
2. Vehicles identify the expected period to reach the next b-destination as the sum of all the `current-period` values across the road links to be used
	- Added `expected-periods` parameter to the vehicles
3. Vehicles consider a target time step to reach the next b-destination
	- Added `target-times` parameter to the vehicles
4. Vehicles move early to reach their next b-destination (in case of unexpected congestions)
	- Added `buffer-period` parameter to the vehicles
	- Added `max-buffer-period` to the UI to control the `buffer-period` paramter
4. Vehicles monitor their achieved times, periods and delays
	- Added the following parameters to the vehicles
		- `times`
		- `periods`
		- `delays`
5. Modified the threshold function for generating activities to consider the delay per activity
	- Added the function `delay-threshold` to vehicles.nls
6. Rehauled the structure of the fucntions used to initialise and run the vehicles in vehicles.nls
	- `vehicles-init` has been updated to fully initialise all the parameters of the vehicle
	- `start-journey` is no longer used in the model run, and its role has been moved to the `vehicles-move` function
	- `vehicles-move` has been updated to
		- Move the vehicles from their homes after their initialisation when they meet the required conditions (a function of `ticks`, `buffer-period` and `target-times`) -- previously applied in `start-journey`
		- Move the vehicles across their respective trips while allocating the periods they take to the `current_period` of each respective road network
	
@#$#@#$#@
default
true
0
Polygon -7500403 true true 150 5 40 250 150 205 260 250

airplane
true
0
Polygon -7500403 true true 150 0 135 15 120 60 120 105 15 165 15 195 120 180 135 240 105 270 120 285 150 270 180 285 210 270 165 240 180 180 285 195 285 165 180 105 180 60 165 15

arrow
true
0
Polygon -7500403 true true 150 0 0 150 105 150 105 293 195 293 195 150 300 150

box
false
0
Polygon -7500403 true true 150 285 285 225 285 75 150 135
Polygon -7500403 true true 150 135 15 75 150 15 285 75
Polygon -7500403 true true 15 75 15 225 150 285 150 135
Line -16777216 false 150 285 150 135
Line -16777216 false 150 135 15 75
Line -16777216 false 150 135 285 75

bug
true
0
Circle -7500403 true true 96 182 108
Circle -7500403 true true 110 127 80
Circle -7500403 true true 110 75 80
Line -7500403 true 150 100 80 30
Line -7500403 true 150 100 220 30

butterfly
true
0
Polygon -7500403 true true 150 165 209 199 225 225 225 255 195 270 165 255 150 240
Polygon -7500403 true true 150 165 89 198 75 225 75 255 105 270 135 255 150 240
Polygon -7500403 true true 139 148 100 105 55 90 25 90 10 105 10 135 25 180 40 195 85 194 139 163
Polygon -7500403 true true 162 150 200 105 245 90 275 90 290 105 290 135 275 180 260 195 215 195 162 165
Polygon -16777216 true false 150 255 135 225 120 150 135 120 150 105 165 120 180 150 165 225
Circle -16777216 true false 135 90 30
Line -16777216 false 150 105 195 60
Line -16777216 false 150 105 105 60

car
false
0
Polygon -7500403 true true 300 180 279 164 261 144 240 135 226 132 213 106 203 84 185 63 159 50 135 50 75 60 0 150 0 165 0 225 300 225 300 180
Circle -16777216 true false 180 180 90
Circle -16777216 true false 30 180 90
Polygon -16777216 true false 162 80 132 78 134 135 209 135 194 105 189 96 180 89
Circle -7500403 true true 47 195 58
Circle -7500403 true true 195 195 58

circle
false
0
Circle -7500403 true true 0 0 300

circle 2
false
0
Circle -7500403 true true 0 0 300
Circle -16777216 true false 30 30 240

cow
false
0
Polygon -7500403 true true 200 193 197 249 179 249 177 196 166 187 140 189 93 191 78 179 72 211 49 209 48 181 37 149 25 120 25 89 45 72 103 84 179 75 198 76 252 64 272 81 293 103 285 121 255 121 242 118 224 167
Polygon -7500403 true true 73 210 86 251 62 249 48 208
Polygon -7500403 true true 25 114 16 195 9 204 23 213 25 200 39 123

cylinder
false
0
Circle -7500403 true true 0 0 300

dot
false
0
Circle -7500403 true true 90 90 120

face happy
false
0
Circle -7500403 true true 8 8 285
Circle -16777216 true false 60 75 60
Circle -16777216 true false 180 75 60
Polygon -16777216 true false 150 255 90 239 62 213 47 191 67 179 90 203 109 218 150 225 192 218 210 203 227 181 251 194 236 217 212 240

face neutral
false
0
Circle -7500403 true true 8 7 285
Circle -16777216 true false 60 75 60
Circle -16777216 true false 180 75 60
Rectangle -16777216 true false 60 195 240 225

face sad
false
0
Circle -7500403 true true 8 8 285
Circle -16777216 true false 60 75 60
Circle -16777216 true false 180 75 60
Polygon -16777216 true false 150 168 90 184 62 210 47 232 67 244 90 220 109 205 150 198 192 205 210 220 227 242 251 229 236 206 212 183

fish
false
0
Polygon -1 true false 44 131 21 87 15 86 0 120 15 150 0 180 13 214 20 212 45 166
Polygon -1 true false 135 195 119 235 95 218 76 210 46 204 60 165
Polygon -1 true false 75 45 83 77 71 103 86 114 166 78 135 60
Polygon -7500403 true true 30 136 151 77 226 81 280 119 292 146 292 160 287 170 270 195 195 210 151 212 30 166
Circle -16777216 true false 215 106 30

flag
false
0
Rectangle -7500403 true true 60 15 75 300
Polygon -7500403 true true 90 150 270 90 90 30
Line -7500403 true 75 135 90 135
Line -7500403 true 75 45 90 45

flower
false
0
Polygon -10899396 true false 135 120 165 165 180 210 180 240 150 300 165 300 195 240 195 195 165 135
Circle -7500403 true true 85 132 38
Circle -7500403 true true 130 147 38
Circle -7500403 true true 192 85 38
Circle -7500403 true true 85 40 38
Circle -7500403 true true 177 40 38
Circle -7500403 true true 177 132 38
Circle -7500403 true true 70 85 38
Circle -7500403 true true 130 25 38
Circle -7500403 true true 96 51 108
Circle -16777216 true false 113 68 74
Polygon -10899396 true false 189 233 219 188 249 173 279 188 234 218
Polygon -10899396 true false 180 255 150 210 105 210 75 240 135 240

house
false
0
Rectangle -7500403 true true 45 120 255 285
Rectangle -16777216 true false 120 210 180 285
Polygon -7500403 true true 15 120 150 15 285 120
Line -16777216 false 30 120 270 120

leaf
false
0
Polygon -7500403 true true 150 210 135 195 120 210 60 210 30 195 60 180 60 165 15 135 30 120 15 105 40 104 45 90 60 90 90 105 105 120 120 120 105 60 120 60 135 30 150 15 165 30 180 60 195 60 180 120 195 120 210 105 240 90 255 90 263 104 285 105 270 120 285 135 240 165 240 180 270 195 240 210 180 210 165 195
Polygon -7500403 true true 135 195 135 240 120 255 105 255 105 285 135 285 165 240 165 195

line
true
0
Line -7500403 true 150 0 150 300

line half
true
0
Line -7500403 true 150 0 150 150

pentagon
false
0
Polygon -7500403 true true 150 15 15 120 60 285 240 285 285 120

person
false
0
Circle -7500403 true true 110 5 80
Polygon -7500403 true true 105 90 120 195 90 285 105 300 135 300 150 225 165 300 195 300 210 285 180 195 195 90
Rectangle -7500403 true true 127 79 172 94
Polygon -7500403 true true 195 90 240 150 225 180 165 105
Polygon -7500403 true true 105 90 60 150 75 180 135 105

plant
false
0
Rectangle -7500403 true true 135 90 165 300
Polygon -7500403 true true 135 255 90 210 45 195 75 255 135 285
Polygon -7500403 true true 165 255 210 210 255 195 225 255 165 285
Polygon -7500403 true true 135 180 90 135 45 120 75 180 135 210
Polygon -7500403 true true 165 180 165 210 225 180 255 120 210 135
Polygon -7500403 true true 135 105 90 60 45 45 75 105 135 135
Polygon -7500403 true true 165 105 165 135 225 105 255 45 210 60
Polygon -7500403 true true 135 90 120 45 150 15 180 45 165 90

square
false
0
Rectangle -7500403 true true 30 30 270 270

square 2
false
0
Rectangle -7500403 true true 30 30 270 270
Rectangle -16777216 true false 60 60 240 240

star
false
0
Polygon -7500403 true true 151 1 185 108 298 108 207 175 242 282 151 216 59 282 94 175 3 108 116 108

target
false
0
Circle -7500403 true true 0 0 300
Circle -16777216 true false 30 30 240
Circle -7500403 true true 60 60 180
Circle -16777216 true false 90 90 120
Circle -7500403 true true 120 120 60

tree
false
0
Circle -7500403 true true 118 3 94
Rectangle -6459832 true false 120 195 180 300
Circle -7500403 true true 65 21 108
Circle -7500403 true true 116 41 127
Circle -7500403 true true 45 90 120
Circle -7500403 true true 104 74 152

triangle
false
0
Polygon -7500403 true true 150 30 15 255 285 255

triangle 2
false
0
Polygon -7500403 true true 150 30 15 255 285 255
Polygon -16777216 true false 151 99 225 223 75 224

truck
false
0
Rectangle -7500403 true true 4 45 195 187
Polygon -7500403 true true 296 193 296 150 259 134 244 104 208 104 207 194
Rectangle -1 true false 195 60 195 105
Polygon -16777216 true false 238 112 252 141 219 141 218 112
Circle -16777216 true false 234 174 42
Rectangle -7500403 true true 181 185 214 194
Circle -16777216 true false 144 174 42
Circle -16777216 true false 24 174 42
Circle -7500403 false true 24 174 42
Circle -7500403 false true 144 174 42
Circle -7500403 false true 234 174 42

turtle
true
0
Polygon -10899396 true false 215 204 240 233 246 254 228 266 215 252 193 210
Polygon -10899396 true false 195 90 225 75 245 75 260 89 269 108 261 124 240 105 225 105 210 105
Polygon -10899396 true false 105 90 75 75 55 75 40 89 31 108 39 124 60 105 75 105 90 105
Polygon -10899396 true false 132 85 134 64 107 51 108 17 150 2 192 18 192 52 169 65 172 87
Polygon -10899396 true false 85 204 60 233 54 254 72 266 85 252 107 210
Polygon -7500403 true true 119 75 179 75 209 101 224 135 220 225 175 261 128 261 81 224 74 135 88 99

wheel
false
0
Circle -7500403 true true 3 3 294
Circle -16777216 true false 30 30 240
Line -7500403 true 150 285 150 15
Line -7500403 true 15 150 285 150
Circle -7500403 true true 120 120 60
Line -7500403 true 216 40 79 269
Line -7500403 true 40 84 269 221
Line -7500403 true 40 216 269 79
Line -7500403 true 84 40 221 269

x
false
0
Polygon -7500403 true true 270 75 225 30 30 225 75 270
Polygon -7500403 true true 30 75 75 30 270 225 225 270
@#$#@#$#@
NetLogo 6.4.0
@#$#@#$#@
random-seed 2
setup
@#$#@#$#@
@#$#@#$#@
<experiments>
  <experiment name="250327 OAT SA" repetitions="100" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <metric>times</metric>
    <metric>count vehicles with [modify? = true]</metric>
    <metric>count vehicles with [modify? = true] / count vehicles</metric>
    <enumeratedValueSet variable="return-home?">
      <value value="true"/>
    </enumeratedValueSet>
    <steppedValueSet variable="number_of_vehicles" first="100" step="100" last="500"/>
    <enumeratedValueSet variable="max-n-activities">
      <value value="4"/>
    </enumeratedValueSet>
    <steppedValueSet variable="slowest-vehicle" first="0.1" step="0.1" last="0.5"/>
  </experiment>
  <experiment name="250327 OAT SA (dummy data)" repetitions="4" runMetricsEveryStep="false">
    <setup>setup</setup>
    <go>go</go>
    <metric>times</metric>
    <metric>count vehicles with [modify? = true]</metric>
    <metric>(count vehicles with [modify? = true] / count vehicles) * 100</metric>
    <enumeratedValueSet variable="return-home?">
      <value value="true"/>
    </enumeratedValueSet>
    <steppedValueSet variable="number_of_vehicles" first="100" step="100" last="500"/>
    <enumeratedValueSet variable="max-n-activities">
      <value value="4"/>
    </enumeratedValueSet>
    <steppedValueSet variable="slowest-vehicle" first="0.1" step="0.1" last="0.5"/>
  </experiment>
  <experiment name="250327 baseline" repetitions="100" runMetricsEveryStep="false">
    <setup>setup</setup>
    <go>go</go>
    <metric>times</metric>
    <metric>count vehicles with [modify? = true]</metric>
    <metric>(count vehicles with [modify? = true] / count vehicles) * 100</metric>
    <enumeratedValueSet variable="return-home?">
      <value value="true"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="number_of_vehicles">
      <value value="300"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-n-activities">
      <value value="4"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="slowest-vehicle">
      <value value="0.2"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="250604 Sensitivity" repetitions="100" runMetricsEveryStep="false">
    <setup>setup</setup>
    <go>go</go>
    <metric>times</metric>
    <metric>count vehicles with [modify? = true]</metric>
    <metric>(count vehicles with [modify? = true] / count vehicles) * 100</metric>
    <metric>activity-record</metric>
    <metric>weight-record</metric>
    <metric>time-record</metric>
    <metric>threshold-record</metric>
    <enumeratedValueSet variable="control-seed?">
      <value value="false"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="current-seed">
      <value value="0"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-n-activities">
      <value value="4"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="mean-tolerance">
      <value value="10"/>
      <value value="20"/>
      <value value="30"/>
      <value value="40"/>
      <value value="50"/>
      <value value="60"/>
      <value value="70"/>
      <value value="80"/>
      <value value="90"/>
      <value value="100"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="number_of_vehicles">
      <value value="300"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="return-home?">
      <value value="true"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="slowest-vehicle">
      <value value="0.4"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w1">
      <value value="0.4"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w2">
      <value value="0.3"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w3">
      <value value="0.2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w4">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w-std">
      <value value="0.02"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="250604 Baseline" repetitions="100" runMetricsEveryStep="false">
    <setup>setup</setup>
    <go>go</go>
    <metric>times</metric>
    <metric>count vehicles with [modify? = true]</metric>
    <metric>(count vehicles with [modify? = true] / count vehicles) * 100</metric>
    <metric>activity-record</metric>
    <metric>weight-record</metric>
    <metric>time-record</metric>
    <metric>threshold-record</metric>
    <enumeratedValueSet variable="control-seed?">
      <value value="false"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="current-seed">
      <value value="0"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-n-activities">
      <value value="4"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="mean-tolerance">
      <value value="10"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="number_of_vehicles">
      <value value="300"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="return-home?">
      <value value="true"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="slowest-vehicle">
      <value value="0.4"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w1">
      <value value="0.4"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w2">
      <value value="0.3"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w3">
      <value value="0.2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w4">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w-std">
      <value value="0.02"/>
    </enumeratedValueSet>
  </experiment>
  <experiment name="250616 Sensitivty" repetitions="100" runMetricsEveryStep="false">
    <setup>setup</setup>
    <go>go</go>
    <metric>all-delays</metric>
    <metric>all-periods</metric>
    <metric>count vehicles with [modify? = true]</metric>
    <metric>(count vehicles with [modify? = true] / count vehicles) * 100</metric>
    <metric>activity-record</metric>
    <metric>weight-record</metric>
    <metric>delay-record</metric>
    <metric>threshold-record</metric>
    <metric>period-record</metric>
    <enumeratedValueSet variable="control-seed?">
      <value value="false"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="current-seed">
      <value value="0"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-activity-duration">
      <value value="100"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-buffer-period">
      <value value="40"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="max-n-activities">
      <value value="4"/>
    </enumeratedValueSet>
    <steppedValueSet variable="mean-tolerance" first="0.1" step="0.1" last="1"/>
    <enumeratedValueSet variable="min-delay-threshold">
      <value value="25"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="number_of_vehicles">
      <value value="100"/>
      <value value="300"/>
      <value value="500"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="return-home?">
      <value value="true"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="slowest-vehicle">
      <value value="0.4"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w1">
      <value value="0.4"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w2">
      <value value="0.3"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w3">
      <value value="0.2"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w4">
      <value value="0.1"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="w-std">
      <value value="0.02"/>
    </enumeratedValueSet>
  </experiment>
</experiments>
@#$#@#$#@
@#$#@#$#@
default
0.0
-0.2 0 0.0 1.0
0.0 1 1.0 0.0
0.2 0 0.0 1.0
link direction
true
0
Line -7500403 true 150 150 90 180
Line -7500403 true 150 150 210 180
@#$#@#$#@
1
@#$#@#$#@
