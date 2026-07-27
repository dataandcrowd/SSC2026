# Simulation — revised text

Replaces the paragraphs under *Study area and model* and adds a *Calibration*
subsection before *Time-of-use fee schedule*. Changes of substance are listed
at the end of this file.

---

## Study area and model

We built the simulation in NetLogo 6.4, using the `gis`, `nw`, `csv` and
`table` extensions to construct the road network, compute vehicle routes and
read the observed traffic counts. The model logic was adapted, with
permission, from the NetLogo model originally developed by the AI4CI Hub at
the Urban Big Data Centre, University of Glasgow.

The road network was derived from Stats NZ. The input dataset holds 1,542
nodes and 2,691 road segments; segments sharing the same pair of nodes are
collapsed, giving 1,634 undirected links in the modelled network, with speed
limits from 10 km/h on laneways to 80 km/h on motorway segments. The CBD
cordon boundary polygon was obtained from Stats NZ at the Statistical Area 3
(SA3) level and filtered to the Auckland City Centre unit to represent the
charged zone. Links are tagged by their position relative to that boundary as
inner, boundary or peripheral, and separately as motorway or arterial. Fig. 1
shows the network with the CBD cordon and the broader eleven SA3 study areas.

Road capacity is taken from the observed annual daily traffic (ADT) counts
published by Auckland Transport, converted to an hourly design capacity with a
design-hour factor of k = 0.10, the midpoint of the standard urban range of
0.08 to 0.12. Congestion is reported as Level of Service (LoS), graded from
the ratio of hourly flow to that hourly capacity following the Highway
Capacity Manual thresholds reproduced in the Congestion Question working
paper. The thresholds are class specific, so the same volume-to-capacity (V/C)
ratio grades more severely on an arterial (LoS E from 0.82) than on a motorway
(LoS E from 0.90). Because a single agent represents many vehicles, the
instantaneous count on a link is too coarse to grade, so flow is measured as
an exponentially weighted moving average of link entries with a one-hour time
constant. Travel speed responds to congestion through the standard BPR
function with a = 0.15 and b = 4. A sensitivity test across k = 0.08, 0.10 and
0.12 confirms that the direction and ordering of the pricing results do not
depend on this capacity assumption.

In total, 2,500 heterogeneous agents decide each day whether to enter the
priced cordon. Each agent represents 160 vehicles after calibration, so the
population corresponds to roughly 400,000 vehicle trips per day. Each agent
has an individual value of time, an arbitrary monetary value placed on travel
time savings, that varies across the population. Consequently, the same fee
deters agents with a lower value of time, typically those on a lower income,
more strongly [16]. About 70 % of agents enter from the network boundary, by
region (North Shore, West, Central, East and South), while the remainder are
local residents. Some of the boundary inflow comprises pass-through traffic
that does not stop in the cordon and is not charged. The full distributions
and parameters are given in the ODD protocol (see link).

Routing uses congestion-aware shortest paths, which are cached per
origin-destination pair and remain fixed. This means that agents adjust their
entry and departure timing, but do not change their route to avoid the charge.
The choice of route is left for future work. Travel demand combines two
sources. TomTom Move data for August 2024 determines the time-of-day profile,
which exhibits the characteristic weekday double peak [9]. The NZTA Traffic
Monitoring System screenline counts (Harbour Bridge, Southern and
Northwestern motorways) determine the inflow volume on each corridor. In
effect, each corridor releases vehicles in line with the TomTom peak shape,
scaled so that the total daily volume matches the corresponding count. The
origin-destination matrix is assumed to be fixed and mode shift is not
modelled.

## Calibration

Modelled link volumes were calibrated against the observed ADT counts along
two axes, total volume and spatial distribution, leaving temporal peaking as a
measured residual.

Volume was matched by the number of vehicles each agent represents. Because
routes are cached and every scheduled trip completes, modelled link volumes
scale linearly in that factor, so the fit is a single division. At a factor of
160 the flow-weighted ratio of modelled to observed daily volume across all
1,634 links is 1.013, with a median per-link ratio of 1.010.

Spatial distribution was corrected by adding suburban trip ends. All 1,484
non-home destinations in the original building dataset lie inside the cordon,
so uniform sampling sent every non-home trip into the city centre. Adding
1,400 non-CBD commercial destinations across the suburbs and drawing
destinations from the combined pool brings the group-level ratios of modelled
to observed volume from a range of 0.75 to 1.80 down to 0.82 to 1.20, and the
CBD from 1.80 to 1.12. Closing the remaining gap would require observed
trip-end data, since link counts alone do not determine the
origin-destination matrix.

Temporal peaking remains the one unresolved residual. With volume and
distribution matched, the model's implied design-hour factor, that is the
flow-weighted peak clock-hour volume divided by the daily volume, is 0.157
against the 0.10 assumed in the capacity conversion. The departure profile
concentrates the morning peak more sharply than a real network does, so
peak-hour flow runs about 1.5 times the design-hour capacity even when daily
volumes match. Absolute LoS levels at the peak are therefore pessimistic, and
we report the difference between the charged and uncharged cases rather than
the absolute level.

Each scenario runs for 14 simulated days with learning carried across days.
The design crosses two fee schemes, no charge and ToU, with the three decision
rules, giving six scenario combinations. Runs use a fixed random seed, so the
day-to-day spread reported below is variation within one seed rather than
run-to-run uncertainty.

## Agent decision models — replacement for the Q-learning paragraph

> **Q-learning (individual learning and adaptation).** Each agent learns from
> its own experience whether entering the cordon is worth repeating [19]. Its
> state is the pair of departure time band and the congestion band it last
> observed, and its action is binary, to enter or not to enter on that day. The
> departure hour itself is drawn from the demand profile and is not chosen by
> the agent, so the rule cannot retime a trip, only forgo it. The reward pays
> the value of time saved by travelling, less the fee paid and less a penalty
> in the congestion encountered, with an additional penalty for agents whose
> fee exceeds their value of time and a bonus for essential trips. Crucially,
> the fee does not enter the decision itself, only the reward that follows it,
> so the response to a charge has to be learned over successive days rather
> than appearing at once. Agents have bounded rationality with learning: they
> do not optimise globally but refine a personal routine through experience
> [20]. The equations and parameter values of all three rules are provided in
> the ODD protocol.

---

## Substantive changes from the submitted draft

1. **Platform.** The draft says the simulation was developed in Python with
   NetworkX, Shapely and NumPy. The results reported here come from the
   NetLogo model in the repository, so the description has been changed to
   match. Please confirm this is the intended description.
2. **Network size.** "1,542 nodes and 2,691 links" describes the input file.
   The model collapses segments that share a node pair, so it simulates 1,634
   links. Both figures are now given.
3. **Congestion definition.** The draft defines congestion as V/C above 0.85
   on a single threshold. The model grades LoS on class-specific HCM
   thresholds against an hourly capacity derived from observed ADT and
   k = 0.10, so the definition has been rewritten and the k sensitivity test
   noted.
4. **Population.** The agent count is unchanged at 2,500, but the calibrated
   scale factor of 160 vehicles per agent is now stated, since every volume
   and capacity number depends on it.
5. **Calibration.** New subsection. The submitted draft reports no calibration
   against observed counts.
6. **Run length and design.** 20 days becomes 14 days, and the nine-cell
   design (three fee schemes) becomes six cells, because the flat NZ$2 charge
   was not re-run on the calibrated model. If the flat charge is to stay in
   the paper, that run is still outstanding.
7. **Q-learning action space.** The draft says the agent "decides whether to
   enter now, shift the time of entry earlier or later, or forgo the trip
   altogether", and later credits the rule with "systematic time-shifting away
   from priced peaks". The implemented rule (`decide-qlearning` and `q-update`
   in `akl_pricing.nls`) chooses between two actions only, enter or do not
   enter; the departure hour is drawn from the demand profile each day. The
   time band appears in the state, not in the action. The runs bear this out:
   the mean fee paid per entering agent is unchanged over the fortnight (2.83
   on day 1, 2.75 on day 14), so no retiming occurs. The description has been
   corrected, and the claim of systematic time-shifting removed. If
   time-shifting is wanted as a result, the action space has to be extended
   first.
