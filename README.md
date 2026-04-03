# SSC2026

Open repository for the Social Simulation Conference 2026.

This project contains an agent-based model (ABM) of congestion pricing in Auckland CBD. The central question is how congestion shifts -- both spatially across road types and temporally across hours of the day -- when a cordon charge is introduced, and how different agent decision rules shape that redistribution. Three decision models (Baseline exponential decay, El Farol bar problem, and Q-Learning) are compared under three fee regimes (no charge, flat $2, and time-of-use pricing) using the real Auckland road network (1542 nodes, 2691 links). The model tracks V/C ratios separately for inner CBD, boundary, and peripheral roads to reveal whether pricing merely displaces congestion to the cordon fringe or achieves a genuine network-wide reduction.


## Repository structure

```
SSC2026/
├── code/                    Python scripts and notebooks
├── netlogo/                 NetLogo model and source data
│   ├── akl_traffic.nlogo    Main NetLogo model
│   ├── *.nls                NetLogo sub-modules (boundary, buildings, nodes, vehicles)
│   └── Data/                Road network CSVs, shapefiles, and building data
├── output/
│   ├── figures/             Generated PNG figures
│   └── tables/              Generated CSV summary tables
├── paper/                   Conference paper (docx and pdf)
└── run_all.sh               One-command pipeline
```


## Model overview

The project developed in three stages. First, a proof-of-concept NetLogo model on a 5x5 traffic grid established baseline congestion dynamics and revealed that cordon charging shifts congestion spatially from inner to boundary roads rather than simply eliminating it. Second, a time-of-use (ToU) fee schedule was introduced to test whether graduated pricing could smooth peak-hour demand without merely displacing congestion to shoulder periods. Third, heterogeneous willingness-to-pay (WTP) and agent learning models (El Farol and Q-Learning) were added to investigate how the redistribution pattern changes when drivers adapt their behaviour over time. The Python scripts scale this logic to the real Auckland road network.

### NetLogo proof-of-concept (`netlogo/`)

The NetLogo model (`akl_traffic.nlogo`) simulates day-long traffic on a 5x5 traffic grid (10 road segments: 5 horizontal, 5 vertical). It was in this model that the congestion redistribution effect was first observed: when a flat CBD charge was applied, inner-road V/C fell but boundary-road V/C rose, showing that pricing displaced rather than removed congestion. This finding motivated the subsequent addition of ToU pricing and heterogeneous learning agents. Key design choices:

**Time representation.** Each hour is 600 ticks, so a full 24-hour day runs for 14,400 ticks. One tick represents 6 seconds. All measurements (flow, V/C, density, speed) are computed over a rolling window of 100 ticks (10 minutes).

**Demand profile.** Vehicle counts vary by hour to reflect realistic daily patterns: low overnight (20 vehicles at 1--4 AM), ramping through the morning peak (200 at 8 AM), a daytime plateau (150 at 10 AM -- 4 PM), an evening peak (200 at 6 PM), and tapering off at night. A +/-10% stochastic fluctuation and 30% vehicle churn per hour ensure variability across runs.

**Capacity estimation.** Road capacity is estimated empirically by running 20 independent simulations and taking the maximum observed flow-per-tick for each road segment: C(road) = max(flow per tick across 20 runs). Flow per tick is defined as the number of vehicles passing a fixed camera point in 100 ticks, divided by 100.

**Congestion definition.** Congestion is evaluated using two indicators jointly. The volume-to-capacity (V/C) ratio measures flow pressure, while road density (vehicles per 36-patch road segment) captures spatial saturation. Congestion is flagged when V/C > 0.85, corresponding approximately to Level of Service E (unstable flow, increased delays, reduced speed, risk of flow breakdown). Severe congestion is flagged when density exceeds the density observed at the V/C peak point, even if V/C itself has dropped below 0.85, because this indicates gridlock where high density coexists with reduced throughput.

**CBD charging.** A central rectangular area is designated as the CBD, covering roads (0,1), (0,2), (1,1), and (1,2). Vehicles are charged once per charge window when they transition from outside to inside the CBD. Charging intensity is defined in dollars per hour. The probability of a vehicle entering the CBD under charging is calculated as: p_enter = to-cbd-rate * e^(-charge-intensity / charge-hour), clamped between minimum and maximum entry bounds so that CBD entry is never impossible and never guaranteed. Revenue is accumulated per V/C window, per hour, and per day.

### Python ABM (`code/`)

The Python scripts extend the NetLogo proof-of-concept to the real Auckland road network (1542 nodes, 2691 links extracted from OpenStreetMap). They replace the 5x5 grid with actual road geometry and add three agent decision models: a baseline exponential decay model calibrated against the NetLogo outputs, an El Farol bar problem (minority game with bounded rationality and competing predictors), and a Q-learning reinforcement learner with time-of-day and congestion state bins. These three models are each tested under three fee regimes (no charge, flat $2 cordon fee, and time-of-use pricing from $2 to $6).

Driver heterogeneity is introduced through a lognormal distribution of value-of-time (median ~NZ$10/hr, mean ~NZ$12/hr), derived from the NZTA Monetised Benefits and Costs Manual. Income quintiles are assigned based on value-of-time, and price sensitivity is set inversely proportional to it, so that lower-income drivers are more responsive to charges.

A key output of the simulation is the comparison of V/C ratios by road type (inner, boundary, peripheral) across fee regimes. Under the baseline no-charge scenario, congestion concentrates on inner CBD roads. When a flat cordon fee is applied, inner V/C drops but boundary roads may absorb displaced traffic. The time-of-use schedule is designed to test whether graduated pricing can smooth peak-hour demand without simply shifting congestion to shoulder periods or to the cordon fringe. The heatmap figures (`fig_akl_road_heatmap.png`) and hourly V/C plots (`fig_akl_hourly_vc.png`) visualise these spatial and temporal redistribution patterns.


## How to run

### Quick start

```bash
cd SSC2026
bash run_all.sh
```

This runs `akl_sim_v2.py`, which is the main simulation. It reads the Auckland road network from `netlogo/Data/`, runs all 9 scenarios (3 models x 3 fee regimes, 20 days each), and saves figures to `output/figures/`.

### Running scripts individually

There are four Python simulation scripts in `code/`. You do not need to run all of them; they represent different stages of model development.

| Script | What it does | Needs network data? |
|---|---|---|
| `akl_sim_v2.py` | **Main simulation.** Real network with corrected SA3 boundary, calibrated against NetLogo outputs. This is the one `run_all.sh` calls. | Yes (`netlogo/Data/`) |
| `akl_real_network_sim.py` | Earlier version of the real-network simulation using a simpler CSV-based boundary polygon. | Yes (`netlogo/Data/`) |
| `congestion_sim_v2.py` | Statistical simulation calibrated from NetLogo output profiles. Does not load the road network at runtime. | No |
| `congestion_tou_v3.py` | Time-of-use fee schedule analysis with WTP equity breakdown. Does not load the road network at runtime. | No |

To run any script individually:

```bash
python3 code/akl_sim_v2.py           # main simulation
python3 code/congestion_tou_v3.py    # ToU equity analysis
```

### Jupyter notebooks

The three notebooks in `code/` are exploratory analyses and do not need to be run for the paper:

| Notebook | Purpose |
|---|---|
| `capacity.ipynb` | Capacity estimation from the NetLogo 20-run experiment |
| `day_count_capacity.ipynb` | Hourly vehicle count and capacity analysis |
| `day_model_traffic_grid.ipynb` | Traffic grid V/C and density exploration |

### NetLogo model

The NetLogo model (`netlogo/akl_traffic.nlogo`) requires NetLogo 6.x and the GIS extension. The Python scripts do not call NetLogo at runtime; they only read the CSV data files that were originally exported from it. If you want to re-run the NetLogo model yourself, open `akl_traffic.nlogo` in NetLogo and use the start-hour slider to control the simulation start time.


## Prerequisites

Python 3.8+ with the following packages:

```
numpy
networkx
pyshp
shapely
matplotlib
pandas
```

Install with:

```bash
pip install numpy networkx pyshp shapely matplotlib pandas
```


## Output

Figures are saved to `output/figures/` and summary tables to `output/tables/`. The main figures produced by the Python ABM are:

- `fig_akl_hourly_vc.png` -- hourly V/C ratio across 3 models and 3 fee regimes
- `fig_akl_behaviour.png` -- Q-learning convergence and El Farol oscillation
- `fig_akl_network.png` -- Auckland CBD road network map with cordon boundary
- `fig_akl_road_heatmap.png` -- V/C comparison heatmap by road type
- `fig_tou_schedule.png` -- time-of-use fee schedule
- `fig_wtp_equity.png` -- willingness-to-pay equity analysis by income quintile
