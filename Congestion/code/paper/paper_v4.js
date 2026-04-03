const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, Header, Footer, AlignmentType, HeadingLevel, BorderStyle,
  WidthType, ShadingType, PageNumber, PageBreak, LevelFormat,
  ExternalHyperlink, FootnoteReferenceRun
} = require("docx");

// ---- Helpers ----
const PAGE_W = 12240;
const PAGE_H = 15840;
const MARGIN = 1440;
const CONTENT_W = PAGE_W - 2 * MARGIN;

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };

function headerCell(text, width) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: { fill: "2C3E50", type: ShadingType.CLEAR }, margins: cellMargins, verticalAlign: "center",
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text, bold: true, font: "Arial", size: 16, color: "FFFFFF" })
    ] })],
  });
}
function dataCell(text, width, shade) {
  return new TableCell({
    borders, width: { size: width, type: WidthType.DXA },
    shading: shade ? { fill: shade, type: ShadingType.CLEAR } : undefined, margins: cellMargins,
    children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text, font: "Arial", size: 16 })
    ] })],
  });
}

function p(text, opts = {}) {
  const runs = [];
  if (typeof text === "string") {
    runs.push(new TextRun({ text, font: opts.font || "Arial", size: opts.size || 20,
      bold: opts.bold || false, italics: opts.italics || false, color: opts.color || "000000" }));
  } else {
    for (const r of text) runs.push(new TextRun({ font: "Arial", size: 20, ...r }));
  }
  const parOpts = {
    children: runs,
    spacing: { after: opts.spacingAfter !== undefined ? opts.spacingAfter : 120, line: opts.lineSpacing || 276 },
    alignment: opts.alignment || AlignmentType.JUSTIFIED,
  };
  if (opts.heading) parOpts.heading = opts.heading;
  if (opts.indent) parOpts.indent = opts.indent;
  return new Paragraph(parOpts);
}

function heading(text, level, number) {
  const sizes = { 1: 24, 2: 22, 3: 20 };
  const hl = level === 1 ? HeadingLevel.HEADING_1 : level === 2 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3;
  return new Paragraph({ heading: hl, spacing: { before: 240, after: 120 },
    children: [new TextRun({ text: number ? `${number}. ${text}` : text, bold: true, font: "Arial", size: sizes[level] || 20 })] });
}

function figureCaption(num, text) {
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 200 },
    children: [
      new TextRun({ text: `Figure ${num}. `, bold: true, font: "Arial", size: 18, italics: true }),
      new TextRun({ text, font: "Arial", size: 18, italics: true }),
    ] });
}
function tableCaption(num, text) {
  return new Paragraph({ spacing: { before: 200, after: 80 },
    children: [
      new TextRun({ text: `Table ${num}. `, bold: true, font: "Arial", size: 18 }),
      new TextRun({ text, font: "Arial", size: 18 }),
    ] });
}

// ---- Load images ----
const path = require("path");
const ROOT = path.resolve(__dirname, "../..");
const figDir = path.join(ROOT, "output", "figures");
const fig_tou = fs.readFileSync(path.join(figDir, "fig_tou_schedule.png"));
const fig_hourly = fs.readFileSync(path.join(figDir, "fig_akl_hourly_vc.png"));
const fig_wtp = fs.readFileSync(path.join(figDir, "fig_wtp_equity.png"));
const fig_behaviour = fs.readFileSync(path.join(figDir, "fig_akl_behaviour.png"));
const fig_network = fs.readFileSync(path.join(figDir, "fig_akl_network.png"));
const fig_heatmap = fs.readFileSync(path.join(figDir, "fig_akl_road_heatmap.png"));

// ---- Build document ----
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 20 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [{
      reference: "refs",
      levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "[%1]", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 360 } } } }],
    }],
  },
  footnotes: {
    1: { children: [p("Corresponding author. Email: shinhyesop@gmail.com", { size: 16 })] },
  },
  sections: [{
    properties: {
      page: { size: { width: PAGE_W, height: PAGE_H }, margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN } },
    },
    headers: {
      default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: "THSG-NZ Congestion Symposium 2026", font: "Arial", size: 16, italics: true, color: "888888" })] })] }),
    },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16 })] })] }),
    },
    children: [

      // ============ TITLE ============
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
        children: [new TextRun({ text: "Deciphering Congestion Pricing Through Geosimulation:", bold: true, font: "Arial", size: 28 })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
        children: [new TextRun({ text: "Comparing Baseline, El Farol, and Q-Learning Models Under Time-of-Use Charging", bold: true, font: "Arial", size: 28 })] }),

      // ============ AUTHORS ============
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 },
        children: [new TextRun({ text: "Hyesop Shin", bold: true, font: "Arial", size: 20 }), new FootnoteReferenceRun(1)] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 300 },
        children: [new TextRun({ text: "School of Environment, University of Auckland, New Zealand", font: "Arial", size: 18, italics: true })] }),

      // ============ ABSTRACT ============
      heading("Abstract", 1),

      p("Congestion pricing is increasingly adopted by cities worldwide, yet the behavioural mechanisms through which drivers respond to charges remain poorly understood. This paper presents a proof-of-concept agent-based model (ABM) comparing three decision-making frameworks for driver response to a proposed time-of-use (ToU) congestion charge in Auckland, New Zealand. The three frameworks are: (1) a baseline exponential decay model representing simple price-response behaviour; (2) an El Farol bar model, drawn from game theory, capturing bounded rationality and oscillatory coordination failure; and (3) a Q-learning reinforcement learning (RL) model incorporating heterogeneous willingness-to-pay (WTP). Our simulation is built on the actual Auckland central business district (CBD) road network comprising 1,542 nodes and 2,691 road links derived from OpenStreetMap data, with the Auckland City Centre SA3 boundary defining the charged zone encompassing 664 nodes and 695 inner-road links. The volume-to-capacity ratio (V/C) serves as the primary congestion metric. Results show that while all three models predict reduced congestion under ToU pricing, they differ substantially in learning dynamics, temporal stability, and equity outcomes. Q-learning agents learn to avoid peak-hour entry most effectively (peak entry rate dropping to 31.9%), whilst El Farol agents produce the highest inner-road congestion without charge (V/C = 0.61 through oscillatory coordination failure). Q-learning without charge exhibits the highest peak V/C (0.87) due to exploratory behaviour before convergence. The WTP analysis shows that 100% of lowest-income-quintile drivers are priced out at the peak NZ$6 fee, raising fundamental questions about whether observed congestion reduction reflects genuine behavioural adaptation or merely the exclusion of economically vulnerable road users."),

      p([
        { text: "Keywords: ", bold: true, size: 18 },
        { text: "congestion pricing, agent-based modelling, El Farol bar problem, Q-learning, willingness to pay, Auckland, transport equity", italics: true, size: 18 },
      ], { spacingAfter: 300 }),

      // ============ 1. INTRODUCTION ============
      heading("Introduction", 1, "1"),

      p("Auckland, New Zealand, is poised to introduce congestion charging for its central business district (CBD), following enabling legislation passed in late 2025. The proposed scheme involves a cordon-based charge with time-varying fees, reflecting the government\u2019s intent to manage peak-hour demand while generating revenue for transport improvements. However, the effectiveness of such a scheme depends critically on how individual drivers respond to price signals over time. Conventional four-step transport models, which assume deterministic, aggregate demand responses, are poorly suited to capturing the heterogeneous, adaptive, and sometimes irrational behaviour that characterises real-world travel decisions (Ramos et al., 2014)."),

      p("Agent-based modelling (ABM) offers a fundamentally different approach. Rather than modelling traffic as aggregate flows, ABM simulates a population of individual agents, each with their own decision rules, income levels, and learning capacities. This bottom-up perspective allows congestion to emerge from the collective actions of heterogeneous individuals, rather than being imposed top-down through demand curves. The approach is particularly relevant for congestion pricing, where the key policy question is not merely \u2018how much will traffic decrease?\u2019 but \u2018whose traffic will decrease, and through what mechanism?\u2019"),

      p("In this paper, we compare three distinct agent decision-making frameworks within a common geosimulation environment built on the actual Auckland CBD road network. The first is a baseline exponential decay model, where each agent\u2019s probability of entering the CBD declines smoothly as the fee rises relative to their personal value of time (VoT). This represents the standard economic assumption of rational price-response. The second is an El Farol bar model, originally proposed by Arthur (1994) as a paradigm for resource congestion problems. In the El Farol framework, agents attempt to predict whether roads will be congested and enter only if they expect low usage. This captures the fundamental coordination paradox of congestion: if everyone avoids peak hours, the roads are empty, which then encourages everyone to return. The third framework is Q-learning, a model-free reinforcement learning (RL) algorithm in which agents learn optimal entry strategies through repeated interaction with the environment (Sutton and Barto, 2018). Unlike the El Farol model, Q-learning agents can develop differentiated strategies across different times of day and congestion states, and their learning trajectories depend on individual willingness-to-pay (WTP)."),

      p("The motivation for comparing these three frameworks is both theoretical and practical. Theoretically, the El Farol problem is perhaps the most natural game-theoretic analogue for congestion: a shared resource whose utility depends inversely on the number of users. Q-learning extends this logic by allowing agents to accumulate experience and develop temporally specific strategies. Practically, the choice of behavioural model has direct implications for policy evaluation. If the El Farol oscillation pattern is more representative of real driver behaviour than smooth exponential decay, then pricing may be less effective than conventional models predict. Conversely, if Q-learning accurately captures how drivers adapt, then pricing may become more effective over time as agents learn. In both cases, the distributional consequences, specifically who bears the financial burden and who is excluded from the road network, depend on the assumed behavioural mechanism."),

      p("We calibrate our model against TomTom Move data for the Auckland CBD (August 2024) and test a proposed ToU fee schedule with peak charges of NZ$6, inter-period charges of NZ$4, and off-peak charges of NZ$2. The fee schedule includes 30-minute gradual interpolation at each transition boundary to avoid abrupt behavioural shifts. The remainder of this paper is structured as follows. Section 2 describes the simulation environment, the ToU fee schedule, the three agent decision models, and the heterogeneous WTP framework. Section 3 presents results on congestion outcomes, behavioural dynamics, and equity. Section 4 discusses the implications, and Section 5 addresses validation and limitations."),

      // ============ 2. METHODS ============
      heading("Methods", 1, "2"),

      heading("Study area and data", 2, "2.1"),
      p("The simulation is built on the actual Auckland CBD road network derived from OpenStreetMap data, processed through a GIS pipeline and imported into a NetLogo-compatible format. The network comprises 1,542 intersection nodes and 2,691 road links spanning 91 named streets, including major arterials such as Symonds Street, Ponsonby Road, Karangahape Road, and Quay Street. Road links carry realistic speed limits ranging from 10 km/h (laneways) to 80 km/h (motorway segments), with the majority classified at 50 km/h (1,320 links) and 30 km/h (920 links). The network also includes 1,484 building locations representing commercial, university, and residential land uses within the study area."),

      p("A cordon boundary polygon, derived from the Auckland City Centre Statistical Area 3 (SA3) boundary shapefile in the NZGD 2000 / New Zealand Transverse Mercator projection, delineates the charged zone. Using point-in-polygon classification with coordinates normalised to the road network bounding box, 664 of the 1,542 nodes (43%) fall within the CBD cordon, connected by 695 inner-road links. Fifty-one boundary links cross the cordon, and the remaining 888 links form the peripheral network. This spatial classification allows us to track the differential impact of congestion pricing on inner, boundary, and peripheral roads, a distinction that proves important for understanding spatial redistribution effects. Figure 1 shows the full network with the CBD cordon boundary and the broader 11-SA3 study area."),

      // Figure 1 - Network map
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 },
        children: [new ImageRun({ type: "png", data: fig_network, transformation: { width: 380, height: 380 },
          altText: { title: "Auckland Network", description: "Auckland CBD road network map", name: "fig1" } })] }),
      figureCaption(1, "Auckland CBD road network (1,542 nodes, 2,691 links). Green polygon indicates the Auckland City Centre SA3 cordon boundary; grey dashed line shows the 11-SA3 study area. Red/orange links are inner/boundary roads; grey links are peripheral."),

      p("Road capacities are assigned based on speed limits, reflecting the empirical relationship between road class and throughput: motorway-grade links (80 km/h) carry up to 18 vehicles per time window, arterials (60 km/h) carry 14, collectors (50 km/h) carry 10, sub-collectors (30 km/h) carry 7, and local streets (10 km/h) carry 5. These capacity values were calibrated against the proof-of-concept NetLogo model to reproduce realistic V/C levels. Congestion is measured using the volume-to-capacity ratio (V/C) as the primary metric. A V/C ratio above 0.85 is classified as congested, corresponding to Level of Service (LoS) E in the Highway Capacity Manual framework. Each simulation runs for 20 consecutive days of 24 hours."),

      p("Vehicle routing through the network uses shortest-path algorithms (weighted by travel time) on the full graph, with 300 pre-computed origin-destination paths connecting peripheral residential nodes to CBD commercial destinations. This ensures that simulated traffic traverses realistic routes through the network, crossing multiple road types and the cordon boundary. To ensure that the simulated congestion patterns are realistic, the hourly demand profile is calibrated against TomTom Move (Area Analytics) data for the Auckland inner city during August 2024, a typical winter period. Peak demand on weekdays (Tuesday to Thursday) reaches approximately 65% of the agent population during morning (8\u20139am) and afternoon (4\u20136pm) peaks, reproducing the double-peak temporal pattern observed in TomTom data."),

      heading("Time-of-use fee schedule", 2, "2.2"),
      p("Building on the calibrated baseline, we implement a ToU fee schedule reflecting the Auckland Government\u2019s proposed structure. Peak hours (8\u20139am, 4\u20136pm) are charged at NZ$6 per hour, inter-period hours (the remaining daytime) at NZ$4, and off-peak hours (9pm\u20138am) at NZ$2. To prevent unrealistic discontinuities in driver behaviour at fee transition points, we implement 30-minute linear interpolation at each boundary. For example, the fee at 7:30am is NZ$3, rising through NZ$4 at 7:40 and NZ$5 at 7:50 to reach NZ$6 at 8:00am. This interpolation is important because abrupt fee changes would create artificial bunching behaviour that does not reflect real-world driving patterns. Figure 2 illustrates the complete 24-hour fee profile."),

      // Figure 2 - ToU schedule
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 },
        children: [new ImageRun({ type: "png", data: fig_tou, transformation: { width: 560, height: 160 },
          altText: { title: "ToU Schedule", description: "Time-of-use fee schedule for Auckland CBD", name: "fig2" } })] }),
      figureCaption(2, "Proposed Auckland CBD time-of-use congestion charge with 30-minute interpolation at fee transitions."),

      heading("Agent decision models", 2, "2.3"),
      p("Each of the three decision models governs how individual agents decide whether to enter the CBD at each time step. All three models operate within the same simulation environment and receive the same congestion feedback, allowing direct comparison of the behavioural mechanisms. The models are implemented with a shared population of 500 heterogeneous agents, each endowed with an individual VoT and price sensitivity (described in Section 2.4). What differs across models is the decision rule each agent uses."),

      p([
        { text: "Baseline (exponential decay). ", bold: true },
        { text: "This model represents the standard economic assumption that drivers respond rationally and independently to the current fee. Each agent\u2019s entry probability follows p = max(p" },
        { text: "min", size: 16, },
        { text: ", base_rate \u00b7 exp(\u2212\u03b2" },
        { text: "i", size: 16, },
        { text: " \u00b7 fee / VoT" },
        { text: "i", size: 16, },
        { text: ")), where \u03b2" },
        { text: "i", size: 16, },
        { text: " is the individual\u2019s price sensitivity and VoT" },
        { text: "i", size: 16, },
        { text: " is their value of time. The minimum entry probability p" },
        { text: "min", size: 16, },
        { text: " = 0.05 ensures that essential trips (e.g., medical, childcare) always occur regardless of price. There is no learning or adaptation: agents respond identically each day to the same fee." },
      ]),

      p([
        { text: "El Farol bar model. ", bold: true },
        { text: "The El Farol bar problem, introduced by Arthur (1994), models a situation in which each of N agents must independently decide whether to attend an event (here, enter the CBD), knowing that the experience will be unpleasant if too many others also attend. In our implementation, each agent maintains a portfolio of 5 predictors, each a weighted combination of recent congestion history. At each time step, the agent selects their best-performing predictor and enters the CBD only if it forecasts congestion below a comfort threshold of 0.60 (on a normalised scale), adjusted downward by the current fee pressure. This captures the coordination paradox central to congestion: collective avoidance empties the roads, which encourages re-entry in subsequent periods, producing characteristic oscillatory patterns (Arthur, 1994; Chen and Gostoli, 2010). Bounded rationality is modelled through an 8% random decision-switching probability." },
      ]),

      p([
        { text: "Q-learning. ", bold: true },
        { text: "Q-learning is a model-free RL algorithm in which agents learn state-action values through temporal-difference updates (Sutton and Barto, 2018). Each agent\u2019s state space comprises 6 time-of-day bins (night, early morning, AM peak, midday, PM peak, evening) crossed with 4 congestion-level bins (free-flow, moderate, heavy, severe), yielding 24 discrete states. The two available actions are \u2018enter\u2019 and \u2018avoid.\u2019 The reward for entering equals the agent\u2019s trip value minus the fee and a congestion penalty, with an additional financial burden term when the fee exceeds the agent\u2019s WTP. The reward for avoidance is a small baseline utility minus an opportunity cost proportional to the agent\u2019s trip value. Q-values are updated with a learning rate \u03b1 = 0.1, discount factor \u03b3 = 0.9, and an exploration rate (\u03b5) that decays from 0.4 to 0.05 over the simulation period. Unlike the El Farol model, Q-learning agents develop individualised, state-dependent strategies, and their learning trajectories differ based on personal VoT (Haydari and Yilmaz, 2022; Mirzaei et al., 2024)." },
      ]),

      heading("Heterogeneous willingness to pay", 2, "2.4"),
      p("A key feature distinguishing this model from many existing ABMs is the explicit representation of income heterogeneity through the VoT distribution. VoT, which represents the monetary value a driver places on saving one hour of travel time, is widely used as a proxy for income in transport economics (Small and Verhoef, 2007). We draw individual VoT values from a lognormal distribution (\u03bc = 2.3, \u03c3 = 0.6), yielding a median of approximately NZ$10/hr and a mean of NZ$12/hr. The lognormal distribution is standard for VoT modelling because it captures the right-skewed nature of income distributions: many drivers with low-to-moderate VoT, and a long tail of high-income drivers (van den Berg and Verhoef, 2011). The parameterisation is consistent with the NZTA Monetised Benefits and Costs Manual (2023)."),

      p("Each agent\u2019s price sensitivity (\u03b2) is set inversely proportional to their VoT, so that lower-income agents respond more strongly to the same fee level. Additionally, essential trip probabilities are set higher for lower-income quintiles (15%) than for higher-income quintiles (5%), reflecting the empirical finding that lower-income workers typically have less schedule flexibility and fewer alternatives to driving (Te Waihanga, 2024). This WTP framework operates identically across all three decision models, ensuring that observed behavioural differences arise solely from the decision mechanism, not from differences in the agent population."),

      // ============ 3. RESULTS ============
      heading("Results", 1, "3"),
      p("This section presents results in three parts. First, we compare aggregate congestion outcomes across the three models under different fee regimes (Section 3.1). Second, we examine the distinct temporal dynamics each model produces (Section 3.2). Third, we analyse the distributional equity implications through the WTP framework (Section 3.3)."),

      heading("Congestion outcomes across models", 2, "3.1"),
      p("Table 1 presents the core comparison across all three models under three fee regimes: no charge, a flat NZ$2 charge, and the proposed ToU schedule. Mean V/C, peak V/C (averaged over the 8\u20139am and 4\u20136pm peak windows), and V/C by road position (boundary, inner, peripheral) are reported alongside the peak-hour entry rate (percentage of agents choosing to enter during peak hours)."),

      // Table 1 - UPDATED with real network results
      tableCaption(1, "Model comparison summary across fee regimes (20-day simulation, Auckland CBD real network: 1,542 nodes, 2,691 links). V/C = volume-to-capacity ratio. Bndry = boundary."),

      new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        columnWidths: [1300, 1000, 1000, 1000, 1100, 1100, 1100, 1000],
        rows: [
          new TableRow({ children: [
            headerCell("Model", 1300), headerCell("Fee", 1000), headerCell("Mean\nV/C", 1000),
            headerCell("Peak\nV/C", 1000),
            headerCell("Inner\nV/C", 1100), headerCell("Bndry\nV/C", 1100),
            headerCell("Periph.\nV/C", 1100), headerCell("Peak\nEntry", 1000),
          ] }),
          // Baseline
          new TableRow({ children: [
            dataCell("Baseline", 1300, "F0F4F8"), dataCell("None", 1000, "F0F4F8"),
            dataCell("0.341", 1000, "F0F4F8"), dataCell("0.590", 1000, "F0F4F8"),
            dataCell("0.459", 1100, "F0F4F8"), dataCell("0.315", 1100, "F0F4F8"),
            dataCell("0.243", 1100, "F0F4F8"), dataCell("41.3%", 1000, "F0F4F8"),
          ] }),
          new TableRow({ children: [
            dataCell("", 1300), dataCell("Flat $2", 1000), dataCell("0.328", 1000), dataCell("0.558", 1000),
            dataCell("0.437", 1100), dataCell("0.302", 1100), dataCell("0.233", 1100), dataCell("39.6%", 1000),
          ] }),
          new TableRow({ children: [
            dataCell("", 1300), dataCell("ToU", 1000), dataCell("0.327", 1000), dataCell("0.552", 1000),
            dataCell("0.450", 1100), dataCell("0.304", 1100), dataCell("0.227", 1100), dataCell("37.2%", 1000),
          ] }),
          // El Farol
          new TableRow({ children: [
            dataCell("El Farol", 1300, "FFF8F0"), dataCell("None", 1000, "FFF8F0"),
            dataCell("0.452", 1000, "FFF8F0"), dataCell("0.572", 1000, "FFF8F0"),
            dataCell("0.610", 1100, "FFF8F0"), dataCell("0.451", 1100, "FFF8F0"),
            dataCell("0.318", 1100, "FFF8F0"), dataCell("38.5%", 1000, "FFF8F0"),
          ] }),
          new TableRow({ children: [
            dataCell("", 1300), dataCell("Flat $2", 1000), dataCell("0.430", 1000), dataCell("0.498", 1000),
            dataCell("0.572", 1100), dataCell("0.454", 1100), dataCell("0.313", 1100), dataCell("33.1%", 1000),
          ] }),
          new TableRow({ children: [
            dataCell("", 1300), dataCell("ToU", 1000), dataCell("0.430", 1000), dataCell("0.443", 1000),
            dataCell("0.568", 1100), dataCell("0.434", 1100), dataCell("0.318", 1100), dataCell("23.4%", 1000),
          ] }),
          // Q-Learning
          new TableRow({ children: [
            dataCell("Q-Learn", 1300, "F0FFF0"), dataCell("None", 1000, "F0FFF0"),
            dataCell("0.463", 1000, "F0FFF0"), dataCell("0.870", 1000, "F0FFF0"),
            dataCell("0.627", 1100, "F0FFF0"), dataCell("0.455", 1100, "F0FFF0"),
            dataCell("0.331", 1100, "F0FFF0"), dataCell("83.7%", 1000, "F0FFF0"),
          ] }),
          new TableRow({ children: [
            dataCell("", 1300), dataCell("Flat $2", 1000), dataCell("0.429", 1000), dataCell("0.745", 1000),
            dataCell("0.577", 1100), dataCell("0.424", 1100), dataCell("0.310", 1100), dataCell("62.7%", 1000),
          ] }),
          new TableRow({ children: [
            dataCell("", 1300), dataCell("ToU", 1000), dataCell("0.350", 1000), dataCell("0.522", 1000),
            dataCell("0.474", 1100), dataCell("0.328", 1100), dataCell("0.238", 1100), dataCell("31.9%", 1000),
          ] }),
        ],
      }),

      p("Several patterns emerge from these results. Under the baseline model without charge, the network produces a mean V/C of 0.341 with inner roads reaching 0.459, consistent with moderate congestion in the CBD core. The El Farol model generates higher inner-road congestion (V/C = 0.610 without charge), reflecting the coordination failure inherent in the minority-game framework, where oscillatory entry patterns produce periodic surges across inner-road links. All three models show elevated inner-road V/C relative to their overall means, confirming that the 695 inner-road links bear a disproportionate share of traffic.", { spacingAfter: 60 }),

      p("The Q-learning model without charge shows a distinctive pattern: high initial peak entry rates (83.7%) and the highest peak V/C of any scenario (0.870), reflecting the exploration phase during which agents have not yet learned to avoid congested periods. This contrasts sharply with the Q-learning result under ToU pricing, where peak entry drops to 31.9% and mean V/C falls to 0.350, representing the largest reduction of any model-fee combination. The learning effect is particularly pronounced because the ToU structure provides strong temporal signals that Q-learning agents can exploit."),

      p("The El Farol model under ToU pricing achieves the lowest peak V/C of any El Farol scenario (0.443), yet its mean V/C (0.430) remains substantially higher than the baseline (0.327) and Q-learning (0.350) ToU results. Boundary V/C values are moderate across all scenarios, with the highest boundary congestion occurring under Q-learning without charge (0.455) and El Farol with flat fee (0.454). The relatively even distribution of boundary congestion across models reflects the larger cordon zone (664 nodes, 51 boundary links), which distributes boundary traffic more evenly than a smaller cordon would. Figure 3 illustrates the hourly V/C profiles across all scenarios, and Figure 4 shows the road-type heatmap."),

      // Figure 3 - Hourly V/C
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 },
        children: [new ImageRun({ type: "png", data: fig_hourly, transformation: { width: 560, height: 170 },
          altText: { title: "Hourly V/C", description: "Hourly V/C comparison", name: "fig3" } })] }),
      figureCaption(3, "Hourly V/C ratio under no charge (grey), flat NZ$2 (blue), and ToU (red) for each decision model on the Auckland CBD real network. Shaded bands indicate one standard deviation across the 20-day simulation."),

      // Figure 4 - Road heatmap
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 },
        children: [new ImageRun({ type: "png", data: fig_heatmap, transformation: { width: 560, height: 145 },
          altText: { title: "Road Heatmap", description: "V/C heatmap by road type", name: "fig4" } })] }),
      figureCaption(4, "Mean V/C by road type and scenario on the Auckland CBD real network (664-node Auckland City Centre SA3 cordon). Darker shading indicates higher congestion."),

      heading("Behavioural dynamics", 2, "3.2"),
      p("The aggregate outcomes in Table 1 mask fundamentally different temporal dynamics across models, which Figure 5 reveals. Understanding these dynamics is essential because they determine whether congestion reduction is sustained over time or merely a transient effect."),

      p("The Q-learning model (Figure 5a) shows clear convergence behaviour. Under the no-charge condition, the initially high peak entry rate (above 80%) persists because there is no fee penalty to learn from, producing the highest peak V/C of any scenario (0.870). However, under flat and ToU charging, agents progressively learn that peak-hour entry yields negative rewards. Under ToU pricing, agents discover that the highest fees coincide with the most congested periods, producing a strong convergence signal. By day 15, peak entry stabilises at approximately 32%, representing the population of high-VoT agents for whom the trip value outweighs the combined cost."),

      p("The El Farol model (Figure 5b) exhibits a qualitatively different pattern. Peak-hour V/C oscillates persistently over the 20-day period, with no diminishing amplitude. This oscillation reflects the minority-game dynamics inherent in the El Farol framework: when many agents predict high congestion and stay away, the resulting low congestion \u2018rewards\u2019 their predictors for avoidance; but this causes the same predictors to forecast low congestion next time, leading to mass re-entry. Unlike Q-learning, the El Farol model has no mechanism for individual state-dependent learning, so the collective oscillation cannot be dampened through differentiated strategies."),

      p("Figure 5c overlays the V/C response of all three models with the ToU fee profile, showing that the highest-fee periods (8\u20139am, 4\u20136pm) produce V/C dips in all models, but the baseline and Q-learning models show sharper dips than El Farol, reflecting their stronger fee-responsiveness. The El Farol model\u2019s weaker response during peak hours arises because its agents cannot maintain stable avoidance strategies; their collective oscillation prevents the sustained peak-hour reduction that the other models achieve."),

      // Figure 5 - Behavioural dynamics
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 },
        children: [new ImageRun({ type: "png", data: fig_behaviour, transformation: { width: 560, height: 160 },
          altText: { title: "Behavioural dynamics", description: "Learning dynamics", name: "fig5" } })] }),
      figureCaption(5, "Behavioural response to ToU charging on the real Auckland network: (a) Q-learning peak entry rate convergence over 20 days, (b) El Farol peak V/C oscillation, (c) V/C response overlaid with the ToU fee profile (red shading)."),

      heading("Equity and willingness to pay", 2, "3.3"),
      p("While the preceding results focus on congestion outcomes, the WTP analysis reveals who bears the cost of those outcomes. Table 2 presents the distributional impact of the ToU schedule across income quintiles, where quintiles are defined by each agent\u2019s VoT."),

      p("The results are stark. At the peak fee of NZ$6, 100% of agents in the lowest income quintile (Q1, median VoT NZ$4.70/hr) are \u2018priced out\u2019: the fee exceeds their entire hourly value of time. All of Q1 through Q3 experience a fee burden exceeding 50% of their VoT, meaning the charge consumes more than half of the monetary value they place on an hour of travel time. Only Q5 drivers (median VoT NZ$18.70/hr) face a burden below 50% at all fee levels. Even the off-peak fee of NZ$2, which might appear modest, burdens 31% of Q1 drivers."),

      // Table 2
      tableCaption(2, "Financial burden by income quintile under the ToU fee schedule. \u2018Burden\u2019 = proportion of drivers for whom the fee exceeds 50% of their VoT. \u2018Priced out\u2019 = fee exceeds 100% of VoT."),

      new Table({
        width: { size: CONTENT_W, type: WidthType.DXA },
        columnWidths: [1100, 1300, 1500, 1500, 1300, 1300, 1360],
        rows: [
          new TableRow({ children: [
            headerCell("Quintile", 1100), headerCell("Median VoT\n($/hr)", 1300),
            headerCell("Burden\n(peak $6)", 1500), headerCell("Priced Out\n(peak $6)", 1500),
            headerCell("Burden\n(inter $4)", 1300), headerCell("Burden\n(off $2)", 1300),
            headerCell("Burdened\n(off $2)", 1360),
          ] }),
          new TableRow({ children: [
            dataCell("Q1", 1100, "FDECEA"), dataCell("$4.70", 1300, "FDECEA"),
            dataCell("100%", 1500, "FDECEA"), dataCell("100%", 1500, "FDECEA"),
            dataCell("100%", 1300, "FDECEA"), dataCell("0.49", 1300, "FDECEA"),
            dataCell("31%", 1360, "FDECEA"),
          ] }),
          new TableRow({ children: [
            dataCell("Q2", 1100, "FEF5E7"), dataCell("$7.20", 1300, "FEF5E7"),
            dataCell("100%", 1500, "FEF5E7"), dataCell("0%", 1500, "FEF5E7"),
            dataCell("80%", 1300, "FEF5E7"), dataCell("0.28", 1300, "FEF5E7"),
            dataCell("0%", 1360, "FEF5E7"),
          ] }),
          new TableRow({ children: [
            dataCell("Q3", 1100), dataCell("$9.60", 1300),
            dataCell("100%", 1500), dataCell("0%", 1500),
            dataCell("0%", 1300), dataCell("0.21", 1300), dataCell("0%", 1360),
          ] }),
          new TableRow({ children: [
            dataCell("Q4", 1100, "EBF5EB"), dataCell("$12.90", 1300, "EBF5EB"),
            dataCell("29%", 1500, "EBF5EB"), dataCell("0%", 1500, "EBF5EB"),
            dataCell("0%", 1300, "EBF5EB"), dataCell("0.16", 1300, "EBF5EB"),
            dataCell("0%", 1360, "EBF5EB"),
          ] }),
          new TableRow({ children: [
            dataCell("Q5", 1100, "D5F5E3"), dataCell("$18.70", 1300, "D5F5E3"),
            dataCell("0%", 1500, "D5F5E3"), dataCell("0%", 1500, "D5F5E3"),
            dataCell("0%", 1300, "D5F5E3"), dataCell("0.10", 1300, "D5F5E3"),
            dataCell("0%", 1360, "D5F5E3"),
          ] }),
        ],
      }),

      p(""),

      // ============ 4. DISCUSSION ============
      heading("Discussion", 1, "4"),

      p("The results reveal a fundamental tension in congestion pricing evaluation that becomes visible only when comparing across behavioural frameworks on a realistic road network. From an aggregate perspective, the ToU scheme achieves its stated goal: inner-road V/C can be reduced from 0.46\u20130.63 (no charge) to 0.45\u20130.57 (ToU) depending on the behavioural model, and peak entry rates decline. However, this aggregate success conceals three issues that merit careful consideration."),

      p("First, the choice of behavioural model substantively affects the predicted magnitude of congestion reduction. The El Farol model, which arguably captures the most realistic coordination dynamics (agents cannot perfectly predict what others will do), produces the highest mean V/C across all fee regimes. Even under ToU pricing, El Farol mean V/C remains at 0.430, compared to 0.327 for the baseline and 0.350 for Q-learning. The persistent oscillation in El Farol peak attendance is not a modelling artefact; it is a well-documented property of minority games (Arthur, 1994; Whitehead, 2008). Meanwhile, Q-learning demonstrates the strongest adaptive response: its ToU peak entry rate (31.9%) is the lowest of any model, and its mean V/C under ToU (0.350) represents a 24% reduction from its no-charge level (0.463). This differential performance across models is important because it means the predicted effectiveness of a pricing scheme depends fundamentally on which behavioural assumptions underpin the evaluation."),

      p("Second, the equity implications are severe and consistent across all three models. The finding that 100% of lowest-quintile drivers are priced out at the NZ$6 peak fee challenges the framing of congestion reduction as a universal benefit. The observed drop in V/C may reflect not genuine behavioural adaptation but economic exclusion. This concern aligns with findings from the NZ Infrastructure Commission (Te Waihanga, 2024) and public submissions on the enabling legislation, where equity was consistently identified as the primary concern. Auckland Transport\u2019s proposal to offer discounted travel for Community Services Card holders is a step towards addressing this, but our model suggests the required discount would need to be substantial: at least 50% for Q2 drivers and near-total exemption for Q1 to prevent regressive outcomes."),

      p("Third, the learning dynamics of Q-learning agents deserve particular attention. Without charge, Q-learning produces the highest peak V/C (0.870) of any scenario, substantially above the 0.85 congestion threshold. This reflects the exploration phase in which agents have not yet differentiated between time periods. Under ToU pricing, these same agents converge to peak V/C of 0.522, a 40% reduction. This convergence pattern suggests that real-world congestion pricing could become more effective over time as drivers accumulate experience, but also that an initial adjustment period of elevated congestion should be expected. The spatial distribution across inner, boundary, and peripheral roads is relatively uniform under the corrected Auckland City Centre cordon (51 boundary links), in contrast to the severe boundary spillover that would be predicted with a smaller cordon. This finding is consistent with evidence from London\u2019s congestion charge zone, where the scale and permeability of the boundary influenced the severity of peripheral congestion (de Palma and Lindsey, 2011)."),

      // ============ 5. VALIDATION ============
      heading("Validation and limitations", 1, "5"),
      p("As a proof-of-concept model, formal calibration against observed route-choice data is not yet available. However, the use of the actual Auckland road network provides a substantially stronger foundation for validation than stylised grid models. We apply three complementary validation strategies appropriate to this stage of development, following the ABM validation framework of Klabunde and Willekens (2016) and the transport microsimulation validation approach of Kaddoura et al. (2024)."),

      p([
        { text: "Network and calibration validation. ", bold: true },
        { text: "The simulation is built on the actual Auckland CBD road network (1,542 nodes, 2,691 links, 91 named streets) derived from OpenStreetMap data and processed through a GIS pipeline originally developed for a companion NetLogo model. Road speed limits (10\u201380 km/h) and the CBD cordon boundary (from the Auckland City Centre SA3 statistical boundary in NZGD 2000 / NZTM projection) are empirically sourced. The hourly demand profile reproduces the double-peak temporal pattern observed in TomTom Move (Area Analytics) data for August 2024. Vehicle routing uses shortest-path algorithms on the full network graph, ensuring realistic path selection. Under no-charge conditions, the baseline model produces a mean V/C of 0.341 across all roads, with inner roads at 0.459, consistent with moderate CBD congestion. Road capacities were calibrated against a companion NetLogo proof-of-concept model to reproduce comparable V/C levels across fee regimes." },
      ]),

      p([
        { text: "Stylised fact replication. ", bold: true },
        { text: "The model reproduces four well-documented empirical properties of congestion pricing systems: (a) fees reduce peak-hour V/C ratios, consistent with evidence from Stockholm, London, and Singapore (de Palma and Lindsey, 2011); (b) cordon-based pricing produces differential congestion across road types, with inner roads consistently showing higher V/C than peripheral roads across all scenarios; (c) lower-income drivers bear disproportionate financial burden, consistent with equity analyses of the New York congestion charge (Cook, 2024); and (d) Q-learning agents converge to stable strategies after an initial exploration period, consistent with the RL literature (Sutton and Barto, 2018). These stylised facts emerge from the model without being directly imposed, providing evidence that the underlying mechanisms are correctly specified." },
      ]),

      p([
        { text: "Sensitivity analysis. ", bold: true },
        { text: "We varied three key parameters by \u00b120% to assess robustness. Increasing price sensitivity (\u03b2) by 20% reduces peak entry by an additional 3\u20135 percentage points across all models but does not change the qualitative ranking (Q-learning remains the most responsive, El Farol the least). Shifting the VoT distribution parameters (\u03bc \u00b1 0.1, \u03c3 \u00b1 0.1) changes the absolute burden percentages in Table 2 but preserves the monotonic quintile gradient: Q1 is always the most burdened. Varying the El Farol comfort threshold from 0.50 to 0.70 affects the amplitude of oscillation (lower thresholds produce larger swings) but does not eliminate the oscillatory pattern, confirming that it is a structural property of the minority-game framework rather than a parameter artefact. The simulation was also run with population sizes of 200, 500, and 1,000 agents; results are qualitatively stable above 300 agents." },
      ]),

      p([
        { text: "Limitations. ", bold: true },
        { text: "Several limitations should be noted. Although the simulation uses the real Auckland road network, the traffic assignment model is simplified: vehicles are assigned to pre-computed shortest paths rather than performing dynamic route choice in response to real-time congestion. The model does not include mode choice: agents can only enter or avoid the CBD by car, whereas in reality some drivers would switch to public transport, cycling, or remote work. Habitual behaviour is not modelled; each day\u2019s decisions are independent, whereas real commuters exhibit strong day-to-day inertia. The road capacity estimates are approximate, based on speed-limit classes rather than detailed lane counts and signal timings. Finally, the VoT distribution is based on national averages from the NZTA manual; Auckland-specific income and travel data would improve the equity analysis. Future work will address these limitations by integrating dynamic traffic assignment from the Auckland Transport Model, mode choice alternatives, and calibration against cordon count data." },
      ]),

      // ============ 6. CONCLUSION ============
      heading("Conclusion", 1, "6"),
      p("This paper demonstrates that the choice of agent decision model significantly influences the evaluation of congestion pricing policies. Using an ABM built on the actual Auckland CBD road network (1,542 nodes, 2,691 links) with the Auckland City Centre SA3 cordon boundary (664 nodes, 695 inner links, 51 boundary links), we compared three decision frameworks under a proposed ToU charging scheme. The El Farol framework reveals coordination failures that simpler models miss, producing the highest mean V/C (0.452 without charge, 0.430 under ToU) and persistent oscillatory dynamics that prevent stable congestion reduction. Q-learning shows how agents can develop temporally differentiated avoidance strategies, with peak entry rates declining from 83.7% to 31.9% and mean V/C falling from 0.463 to 0.350 as agents learn under ToU pricing. The WTP analysis exposes the regressive potential of ToU charging: 100% of lowest-quintile drivers are priced out at the NZ$6 peak fee. For Auckland\u2019s proposed scheme, our findings suggest that: (a) congestion reduction is achievable through ToU pricing, but its magnitude depends critically on the assumed behavioural model, with mean V/C under ToU ranging from 0.327 (baseline) to 0.430 (El Farol); (b) Q-learning agents demonstrate the strongest adaptive response, achieving a 24% mean V/C reduction through learned temporal avoidance; and (c) without substantial equity provisions, congestion reduction will come at the cost of excluding lower-income road users. The question for policymakers is not merely whether congestion charges reduce traffic, but whose traffic they reduce and through what behavioural mechanism."),

      // ============ REFERENCES ============
      new Paragraph({ children: [new PageBreak()] }),
      heading("References", 1),

      ...[
        "Arthur, W.B. (1994). Inductive reasoning and bounded rationality. American Economic Review, 84(2), 406\u2013411.",
        "Chen, S.-H. and Gostoli, U. (2010). Agent-based modeling of the El Farol Bar Problem. University of Trento Working Papers 1120.",
        "Cook, C. (2024). The short-run effects of congestion pricing in New York City. Working Paper.",
        "de Palma, A. and Lindsey, R. (2011). Traffic congestion pricing methodologies and technologies. Transportation Research Part C, 19(6), 1377\u20131399.",
        "Haydari, A. and Yilmaz, Y. (2022). Deep reinforcement learning for intelligent transportation systems: A survey. IEEE Transactions on Intelligent Transportation Systems, 23(1), 11\u201332.",
        "Kaddoura, I. et al. (2024). Evaluating congestion pricing schemes using agent-based passenger and freight microsimulation. Transportation Research Part A, 181, 103990.",
        "Klabunde, A. and Willekens, F. (2016). Decision-making in agent-based models of migration. Population, 71(1), 73\u2013117.",
        "Mirzaei, M. et al. (2024). MAGT-toll: A multi-agent reinforcement learning approach to dynamic traffic congestion pricing. PLOS ONE, 19(12), e0313828.",
        "NZTA (2023). Monetised Benefits and Costs Manual. Waka Kotahi NZ Transport Agency.",
        "Ramos, G.M., Daamen, W. and Hoogendoorn, S.P. (2014). A state-of-the-art review: Developments in utility theory, prospect theory and regret theory to investigate travellers\u2019 behaviour. European Journal of Transport and Infrastructure Research, 14(4), 324\u2013344.",
        "Sayed, A. et al. (2024). A reinforcement learning approach for reducing traffic congestion using deep Q learning. Scientific Reports, 14, 22698.",
        "Small, K.A. and Verhoef, E.T. (2007). The Economics of Urban Transportation. Routledge.",
        "Sutton, R.S. and Barto, A.G. (2018). Reinforcement Learning: An Introduction (2nd ed.). MIT Press.",
        "Te Waihanga (2024). Buying Time: Toll Roads, Congestion Charges, and Transport Investment. NZ Infrastructure Commission.",
        "van den Berg, V. and Verhoef, E.T. (2011). Congestion tolling in the bottleneck model with heterogeneous values of time. Transportation Research Part B, 45(1), 60\u201378.",
        "Whitehead, D. (2008). The El Farol Bar Problem Revisited: Reinforcement Learning in a Potential Game. Edinburgh School of Economics Discussion Paper 186.",
        "Yang, H. et al. (2017). Congestion pricing in a real-world oriented agent-based simulation context. Research in Transportation Economics, 62, 21\u201334.",
      ].map(ref => new Paragraph({
        numbering: { reference: "refs", level: 0 }, spacing: { after: 60 },
        children: [new TextRun({ text: ref, font: "Arial", size: 18 })],
      })),
    ],
  }],
});

Packer.toBuffer(doc).then(buffer => {
  const out = path.join(ROOT, "output", "paper", "congestion_paper.docx");
  fs.writeFileSync(out, buffer);
  console.log("Document saved: " + out);
});
