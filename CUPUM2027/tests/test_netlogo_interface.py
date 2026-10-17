"""Static checks of the NetLogo Interface tab layout (netlogo7/cordon_lite.nlogox; no JVM): the choosers
(experiment: the four arms at the $6 and $18 peak charges; no widget for which days go plays), the monitors,
notes and plots (LoS E/F with the mean V/C beside it), the text (no SKIP: commuters drive, take PT or
work from home), and of the Info tab's motorway jam times against the prep data (data/road_meta.json,
data/road_sections.csv).

NetLogo 7 notes have no scrollbar: text past the bottom edge is not shown. The on-screen note must
therefore be tall enough for its wrapped text. Measured with export-interface (NetLogo 7.0.4,
fontSize 12, width 310): about 52 characters per line and 16 px per line; the estimate below uses
fewer characters per line, so it errs on the side of a taller box.
"""

from __future__ import annotations

import json
import re
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

MODEL = Path(__file__).resolve().parents[1] / "netlogo7" / "cordon_lite.nlogox"
DATA = Path(__file__).resolve().parents[1] / "data"
# the experiment chooser, in this order: for each arm (who decides, when) the peak charges NZ$6 (the canonical
# run, no peak suffix) and NZ$18 (fees.peak_fee, --peak-fee 18, folder suffix _peak18), seed 1, 10 days charged
# from day 6 (the config.toml defaults since 2026-10-15, so no folder suffix; _d10_fs6 before); its label is
# "<who decides, when>: $<peak> charge" and its run folder is relative to netlogo7/. The PT disruption chooser
# adds none or two disruption days, 3 (before the charge) and 8 (with it): --set events.pt_disruption_day=[3,8],
# folder suffix _pt3_pt8 (the default, 0, is no disruption)
ARM_LABELS = (("Rule, reacts to events", "R-clock"), ("Rule, decides every day", "R-daily"),
              ("LLM, reacts to events", "L-clock"), ("LLM, decides every day", "L-daily"))
BASE_PEAK = 6        # NZ$ peak of the usual charge (no peak suffix in the folder name)
PEAKS = (6, 18)


def _run_folder(arm: str, peak: int) -> str:
    return f"{arm}_mock_py_s1" + ("" if peak == BASE_PEAK else f"_peak{peak}")


EXPERIMENTS = [(f"{label}: ${peak} charge", f"../runs/{_run_folder(arm, peak)}")
               for label, arm in ARM_LABELS for peak in PEAKS]
DISRUPTIONS = (("none", "", None), ("day 3 and day 8", "_pt3_pt8", (3, 8)))
CHARGE_ON = ["all days", "off: before the charge", "on: with the charge"]
HOW_TO = "Pick an experiment"   # the start of the on-screen how-to note
# NZTA corridor -> the motorway's name in road_sections.csv
CORRIDOR_STREET = {"SH1_north": "Northern Motorway", "SH1_south": "Southern Motorway",
                   "SH16": "Northwestern Motorway", "SH20": "Southwestern Motorway"}
# The Info tab's motorway stretches with a usual window from the counts: label -> the NZTA count sites
# (data/road_meta.json nzta.sites site_ref) whose sections they are. The times the Info tab gives for each
# stretch come from the data (tests below); a new site with breakdown, or a site gone, fails the test, and a
# stretch whose sites end at different times (some at 11:00, some earlier) must be split.
STRETCHES = {
    "the Harbour Bridge": {"01N10425", "01N19424"},                                  # saturated sites
    "the Northern Motorway between Albany and Tristram Avenue": {"01N10417"},
    "the Northern Motorway around Northcote": {"01N10419"},
    "the Southern Motorway between the city and Mt Wellington": {"01N20431", "01N20433", "01N20439"},
    "the Southern Motorway south of Mt Wellington": {"01N20440"},
    "the Northwestern": {"01620006", "01620008", "01620009", "01620011"},
}
# NZTA corridor with a count site whose counts show no breakdown -> how the Info tab names its sections
# without a usual window: (only part of the motorway, the whole motorway)
NO_WINDOW_NAME = {"SH16": ("the Northwestern's city end", "the whole Northwestern"),
                  "SH20": ("the Southwestern near its count sites", "the whole Southwestern")}
# motorway (road_sections.csv street_name) without a count site of its own -> how the Info tab names it
NO_SITE_NAME = {"Upper Harbour Motorway": "the Upper Harbour Motorway", "Airport Motorway": "the roads to the airport",
                "George Bolt Memorial Drive": "the roads to the airport"}
NO_SITE_SHORT = {"Upper Harbour Motorway": "Upper Harbour"}
NO_SITE = "no count site of their own"   # the Info tab's sentence on the default-window motorways
NUMBER = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
          10: "ten"}
PX_PER_CHAR_12 = 6.5     # average glyph width at fontSize 12 (310 px hold about 48 characters)
PX_PER_LINE_12 = 16
# line height by fontSize, measured with export-interface (NetLogo 7.0.4, 2026-10-09): fontSize 10 takes
# 14 px a line, more than 16 x 10 / 12
PX_PER_LINE = {10: 14, 12: PX_PER_LINE_12}
PADDING_PX = 8
LOS_PLOT = "% traffic at LoS E/F"
VC_PLOT = "Mean V/C (1 = at capacity)"   # under the LoS plot, the same 5-minute marks (2026-10-09)
LOS_MONITORS = {"LoS E/F % motorways": 'los-ef-pct "motorway"', "LoS E/F % other roads": 'los-ef-pct "other"'}
# mean V/C and speed-based LoS E/F at the last 5-minute mark (2026-10-08): display -> (reporter, precision)
LOS_MONITORS_2 = {"mean V/C motorways": ('los-vc "motorway"', "2"), "mean V/C other roads": ('los-vc "other"', "2"),
                  "LoS E/F by speed % motorways": ('los-ef-speed-pct "motorway"', "1"),
                  "LoS E/F by speed % other roads": ('los-ef-speed-pct "other"', "1")}


def _widgets() -> list[ET.Element]:
    root = ET.parse(MODEL).getroot()
    return list(root.find("widgets"))


def _box(w: ET.Element) -> tuple[int, int, int, int]:
    x, y = int(w.attrib["x"]), int(w.attrib["y"])
    return x, y, x + int(w.attrib["width"]), y + int(w.attrib["height"])


def test_on_screen_note_shows_all_its_text() -> None:
    """The how-to note, including the road-colour sentence (SPEC 3), fits its box."""
    note = next(w for w in _widgets() if w.tag == "note" and HOW_TO in (w.text or ""))
    text = note.text or ""
    assert "Roads turn yellow, orange, then purple" in text
    assert int(note.attrib["fontSize"]) == 12
    per_line = int(int(note.attrib["width"]) / PX_PER_CHAR_12)
    lines = sum(max(1, len(textwrap.wrap(par, per_line))) for par in text.split("\n"))
    assert int(note.attrib["height"]) >= PX_PER_LINE_12 * lines + PADDING_PX, (lines, note.attrib["height"])


def test_note_and_info_tab_give_the_same_setup_time() -> None:
    """The on-screen note and the Info tab's HOW TO USE IT tell the user the same setup time."""
    note = next(w for w in _widgets() if w.tag == "note" and HOW_TO in (w.text or ""))
    info = ET.parse(MODEL).getroot().find("info").text or ""
    pattern = r"press setup \(about (\d+) s\)"
    in_note, in_info = re.findall(pattern, note.text or ""), re.findall(pattern, info)
    assert len(in_note) == 1 and len(in_info) == 1, (in_note, in_info)
    assert in_note == in_info, f"note says about {in_note[0]} s, Info tab says about {in_info[0]} s"


def _info_paragraph(start: str) -> str:
    info = ET.parse(MODEL).getroot().find("info").text or ""
    pars = [p for p in info.split("\n") if p.startswith(start)]
    assert len(pars) == 1, (start, len(pars))
    return pars[0]


def _sentences(par: str) -> list[str]:
    return re.split(r"(?<=\.) ", par)


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _nzta() -> tuple[dict, list[dict]]:
    """The NZTA rule and the valid count sites that have motorway sections (data/road_meta.json)."""
    nzta = json.loads((DATA / "road_meta.json").read_text(encoding="utf-8"))["nzta"]
    return nzta["rule"], [s for s in nzta["sites"] if s.get("valid") and s.get("n_sections", 0) > 0]


def _from(sites: list[dict]) -> str:
    """'from about HH:MM' for one onset, 'from between A and B' for several."""
    lo, hi = min(s["bd_on"] for s in sites), max(s["bd_on"] for s in sites)
    return f"from about {_hhmm(lo)}" if lo == hi else f"from between {_hhmm(lo)} and {_hhmm(hi)}"


def _until(sites: list[dict], no_recovery: int) -> str:
    """' until 11:00' when no site of the stretch recovers before then, else ' until about' its latest
    recovery. A stretch with both (some of its sites recover, some do not) must be split into two clauses."""
    late = [s["bd_off"] == no_recovery for s in sites]
    assert all(late) or not any(late), ("split this stretch: some sites recover, some do not",
                                        [(s["site_ref"], s["bd_off"]) for s in sites])
    return f" until {_hhmm(no_recovery)}" if all(late) else f" until about {_hhmm(max(s['bd_off'] for s in sites))}"


def _r5(m: int) -> int:
    """A minute to the nearest 5 minutes."""
    return 5 * ((int(m) + 2) // 5)


def _breakdown_sites() -> dict[str, dict]:
    """The valid NZTA sites with breakdown and motorway sections, by site_ref; every one is in STRETCHES."""
    bd = {s["site_ref"]: s for s in _nzta()[1] if s["breakdown"]}
    assert set().union(*STRETCHES.values()) == set(bd), \
        ("STRETCHES must hold exactly the sites with breakdown", sorted(bd), STRETCHES)
    return bd


def _default_window_sections() -> pd.DataFrame:
    """Motorway sections on a motorway without a count site of its own: profile 0 and a usual window."""
    sec = pd.read_csv(DATA / "road_sections.csv")
    return sec[(sec["mwy"] == 1) & (sec["profile_id"] == 0) & (sec["bd_on"] >= 0)]


def test_info_tab_motorway_windows_match_the_count_sites() -> None:
    """The usual breakdown windows the Info tab gives, stretch by stretch (STRETCHES), are those of the NZTA
    sites (data/road_meta.json): the Harbour Bridge (saturated sites, one window); for the other stretches the
    onset (a range when their sites differ) and the end (11:00 when their counts show no recovery, else the
    latest recovery). The mapping is to the nearest site of the same motorway, with the distance limit of
    the data (none: at any distance). The motorways without a count site of their own keep the default
    window of data/road_sections.csv (to the nearest 5 min); the Info tab names exactly those motorways,
    and the sections with another window (capacity raised by the road-class floor) with their clearing
    times."""
    par = _info_paragraph("Motorway breakdown.")
    rule, _ = _nzta()
    no_rec = int(rule["no_recovery_min"])
    bd = _breakdown_sites()
    for label, refs in STRETCHES.items():
        group = [bd[r] for r in sorted(refs)]
        if label == "the Harbour Bridge":
            assert all(s["saturated_min"] > 0 for s in group)
            assert len({(s["bd_on"], s["bd_off"]) for s in group}) == 1
            clause = f"{label} from about {_hhmm(group[0]['bd_on'])} to {_hhmm(group[0]['bd_off'])}"
        else:
            clause = f"{label} {_from(group)}{_until(group, no_rec)}"
        assert clause in par, clause
    assert "the nearest count site on the same motorway" in par
    if rule["map_m"] is None:
        assert not re.search(r"within \d+(\.\d+)? km", par), "the sections map to their site at any distance"
    else:
        assert f"within {rule['map_m'] / 1000:g} km" in par

    default = _default_window_sections()
    far = [s for s in _sentences(par) if NO_SITE in s]
    assert len(far) == 1, far
    lo, hi = int(default["bd_on"].min()), int(default["bd_off"].max())
    window = f"from about {_hhmm(_r5(lo))} to {_hhmm(_r5(hi))}"
    assert window in far[0], (window, far[0])
    for street in default["street_name"].unique():
        assert NO_SITE_NAME[street] in far[0], (street, far[0])
    for street in CORRIDOR_STREET.values():     # motorways with count sites keep no default window
        assert not (default["street_name"] == street).any(), street
        assert not re.search(rf"\b{street.split()[0]}\b", far[0]), (street, far[0])
    main = default.groupby(["bd_on", "bd_off"]).size().idxmax()
    other = default[(default["bd_on"] != main[0]) | (default["bd_off"] != main[1])]
    if len(other):
        streets = set(other["street_name"])
        where = f"{NO_SITE_SHORT[next(iter(streets))]} " if len(streets) == 1 else ""
        assert f"{NUMBER.get(len(other), str(len(other)))} {where}stretches" in far[0], far[0]
        assert (other["bd_on"] > main[0]).all() and "a little later" in far[0]
        clear = f"clear at about {_hhmm(_r5(other['bd_off'].min()))} to {_hhmm(_r5(other['bd_off'].max()))}"
        assert clear in far[0], (clear, far[0])


def test_info_tab_names_the_motorways_that_jam_only_with_todays_traffic() -> None:
    """Sections mapped to a count site whose counts show no breakdown have no usual window: both the
    Motorway breakdown paragraph and THINGS TO NOTICE must say they jam only with today's traffic, naming
    the whole motorway when none of its sections has a usual window (now the Southwestern) and only its
    part otherwise (the Northwestern's city end)."""
    _, sites = _nzta()
    calm = sorted({s["corridor"] for s in sites if not s["breakdown"]})
    assert calm, "no count site without breakdown: revise the Info tab's motorway sentences"
    sec = pd.read_csv(DATA / "road_sections.csv")
    for start in ("Motorway breakdown.", "There are two kinds of congestion"):
        only = [s for s in _sentences(_info_paragraph(start)) if "today's traffic fills them" in s]
        assert len(only) == 1, (start, only)
        for corridor in calm:
            part, whole = NO_WINDOW_NAME[corridor]
            street = sec[(sec["mwy"] == 1) & (sec["street_name"] == CORRIDOR_STREET[corridor])]
            name, wrong = (whole, part) if (street["bd_on"] < 0).all() else (part, whole)
            assert name.lower() in only[0].lower(), (start, corridor, name, only[0])
            assert wrong.lower() not in only[0].lower(), (start, corridor, wrong, only[0])


def test_things_to_notice_says_when_each_motorway_stretch_clears() -> None:
    """THINGS TO NOTICE: the stretches whose counts show no recovery before 11:00 stay purple after 10:00,
    and only they; every other stretch, and the motorways without a count site of their own, clear at the
    latest end of their usual window (to the nearest 5 min)."""
    par = _info_paragraph("There are two kinds of congestion")
    rule, _ = _nzta()
    no_rec = int(rule["no_recovery_min"])
    bd = _breakdown_sites()
    sent = [s for s in _sentences(par) if "stay purple after 10:00" in s]
    assert len(sent) == 1, sent
    head, tail = sent[0].split(" while ", 1)
    clauses = head.split(", ")
    for label, refs in STRETCHES.items():
        offs = {bd[r]["bd_off"] for r in refs}
        if offs == {no_rec}:
            assert label.lower() in tail.lower() and label.lower() not in head.lower(), (label, sent[0])
        else:
            assert no_rec not in offs, ("split this stretch", label, offs)
            hit = [c for c in clauses if label.lower() in c.lower()]
            assert len(hit) == 1 and f"at about {_hhmm(_r5(max(offs)))}" in hit[0], (label, hit)
            assert label.lower() not in tail.lower(), (label, tail)
    hit = [c for c in clauses if "without a count site of their own" in c]
    end = _hhmm(_r5(int(_default_window_sections()["bd_off"].max())))
    assert len(hit) == 1 and f"at about {end}" in hit[0], (end, hit)


def test_widgets_do_not_overlap() -> None:
    """No two widgets overlap anywhere on the Interface tab (the view included): growing the note must
    move the widgets below it, and the Level of Service monitors and plot (SPEC4 B) take free space."""
    boxes = [(w.tag, w.attrib.get("display") or w.attrib.get("variable") or (w.text or "")[:20], _box(w))
             for w in _widgets()]
    for i, (ta, na, a) in enumerate(boxes):
        for tb, nb, b in boxes[i + 1:]:
            overlap = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
            assert not overlap, f"{ta} {na!r} overlaps {tb} {nb!r}"


def test_level_of_service_monitors_note_and_plot() -> None:
    """SPEC4 B: two LoS E/F monitors (motorways, other roads), a short note saying what they show (the
    last 5-minute mark) that fits its box, and a plot "% traffic at LoS E/F" with the two pens that
    plot-los draws, over the hours of the day like the other plots."""
    ws = _widgets()
    mons = {w.attrib["display"]: (w.text or "").strip() for w in ws if w.tag == "monitor"}
    for disp, rep_ in LOS_MONITORS.items():
        assert mons.get(disp) == rep_, (disp, mons.get(disp))
    note = [w for w in ws if w.tag == "note" and (w.text or "").startswith("LoS E/F:")]
    assert len(note) == 1
    text = note[0].text or ""
    assert "5-minute mark" in text and "level of service E or F" in text
    size = int(note[0].attrib["fontSize"])
    px_char, px_line = PX_PER_CHAR_12 * size / 12, PX_PER_LINE[size]
    per_line = int(int(note[0].attrib["width"]) / px_char)
    lines = sum(max(1, len(textwrap.wrap(par, per_line))) for par in text.split("\n"))
    assert int(note[0].attrib["height"]) >= px_line * lines + PADDING_PX, (lines, note[0].attrib["height"])
    plot = [w for w in ws if w.tag == "plot" and w.attrib["display"] == LOS_PLOT]
    assert len(plot) == 1
    pens = [p.attrib["display"] for p in plot[0].findall("pen")]
    from cordonlite import roads as R
    assert pens == list(R.LOS_REGIONS)      # one pen per region (2026-10-10), plot-los draws them by name
    assert plot[0].attrib["yMin"] == "0.0" and plot[0].attrib["yMax"] == "100.0"
    code = ET.parse(MODEL).getroot().find("code").text or ""
    assert f'set-current-plot "{LOS_PLOT}"' in code
    assert "set-current-plot-pen item k los-region-names" in _procedure(code, "plot-los")
    # the bands are those of cordonlite/roads.py
    from cordonlite import roads as R
    for bands in (R.LOS_BANDS_MWY, R.LOS_BANDS_OTHER):
        assert "[ " + " ".join(f"{b:.2f}" if b < 1 else "1.0" for b in bands) + " ]" in code, bands


def test_mean_vc_and_speed_los_monitors() -> None:
    """Monitors for the mean V/C and the speed-based LoS E/F share of motorways and other roads (the
    GUI's los-vc-mwy/other and los-efs-mwy/other at the last 5-minute mark), under the LoS E/F
    monitors; the note says plainly what they show; the speed bands are those of cordonlite/roads.py."""
    ws = _widgets()
    mons = {w.attrib["display"]: w for w in ws if w.tag == "monitor"}
    for disp, (rep_, prec) in LOS_MONITORS_2.items():
        assert disp in mons, disp
        assert (mons[disp].text or "").strip() == rep_ and mons[disp].attrib["precision"] == prec, disp
    # laid out as two more rows of the LoS monitors: same columns and size
    los = [mons[d] for d in LOS_MONITORS]
    for disp in LOS_MONITORS_2:
        m = mons[disp]
        assert m.attrib["x"] in {w.attrib["x"] for w in los} and m.attrib["width"] == los[0].attrib["width"]
        assert int(m.attrib["y"]) > int(los[0].attrib["y"])
    note = next(w for w in ws if w.tag == "note" and (w.text or "").startswith("LoS E/F:"))
    text = note.text or ""
    assert "Mean V/C:" in text and "By speed:" in text and "40% of free-flow speed" in text
    assert "stop-and-go" in text
    code = ET.parse(MODEL).getroot().find("code").text or ""
    for rep_ in ("los-vc", "los-ef-speed-pct", "speed-los-grade-of"):
        assert f"to-report {rep_} [" in code, rep_
    from cordonlite import roads as R
    assert "[ " + " ".join(f"{b:.2f}" for b in R.SPEED_LOS_BANDS) + " ]" in code


def test_mean_vc_plot_under_the_los_plot() -> None:
    """LoS E/F is shown with the mean V/C (2026-10-09): a plot of the mean V/C of motorways and other roads
    by time, directly under the "% traffic at LoS E/F" plot (same column and hours), overlapping no widget.
    plot-los feeds both plots from the same 5-minute pass (los-at: item 3 and 4 are los-vc-mwy and
    los-vc-other; -1 = no traffic, not plotted) and setup-day-plots clears both for the day. The LoS note
    says to read the two together."""
    ws = _widgets()
    los = next(w for w in ws if w.tag == "plot" and w.attrib["display"] == LOS_PLOT)
    vc = [w for w in ws if w.tag == "plot" and w.attrib["display"] == VC_PLOT]
    assert len(vc) == 1
    vc = vc[0]
    from cordonlite import roads as R
    assert [p.attrib["display"] for p in vc.findall("pen")] == list(R.LOS_REGIONS)
    assert [p.attrib["color"] for p in vc.findall("pen")] == [p.attrib["color"] for p in los.findall("pen")]
    assert vc.attrib["yMin"] == "0.0" and vc.attrib["autoPlotY"] == "true"
    for key in ("x", "width", "xAxis", "xMin", "xMax"):
        assert vc.attrib[key] == los.attrib[key], key
    assert 0 <= int(vc.attrib["y"]) - _box(los)[3] <= 10, "directly under the LoS plot"
    a = _box(vc)
    for w in ws:
        if w is not vc:
            b = _box(w)
            assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), (w.tag, w.attrib)
    code = _code()
    body = _procedure(code, "plot-los")
    assert body.index(f'set-current-plot "{LOS_PLOT}"') < body.index(f'set-current-plot "{VC_PLOT}"')
    vc_part = body.split(f'set-current-plot "{VC_PLOT}"', 1)[1]
    assert "set-current-plot-pen item k los-region-names" in vc_part
    assert "if (item k item 9 res) >= 0 [ plotxy (m / 60) (item k item 9 res) ]" in vc_part
    assert "set los-region-vc item 9 res" in code and "set los-vc-mwy item 3 res" in code
    setup = _procedure(code, "setup-day-plots")
    for name in (LOS_PLOT, VC_PLOT):
        assert re.search(rf'set-current-plot "{re.escape(name)}".*\n\s*clear-plot\n\s*set-plot-x-range', setup), name
    note = next(w for w in ws if w.tag == "note" and (w.text or "").startswith("LoS E/F:"))
    assert "read LoS E/F together with the mean V/C" in (note.text or "")


def test_los_regions_of_the_model_are_those_of_cordonlite_roads() -> None:
    """The LoS plots have one pen per region (2026-10-10): the model's los-region-names and the rules of
    region-of (street names, the north-of-the-bridge corner, the two discs) are those of
    cordonlite/roads.py (los_region_of); scripts/check_network_model.py compares the regions of every
    section of a run."""
    from cordonlite import roads as R
    code = _code()
    assert re.findall(r'"([^"]+)"', _procedure(code, "los-region-names")) == list(R.LOS_REGIONS)
    body = _procedure(code, "region-of")
    k = 0
    for names in R.LOS_REGION_STREETS:
        line = next(ln for ln in body.splitlines() if f"report {k} ]" in ln)
        assert re.findall(r'"([^"]+)"', line) == list(names), (k, line)
        k += 1
    assert f"(mid-y > {int(R.LOS_NORTH_SHORE_MIN_Y)}) and (mid-x > {int(R.LOS_NORTH_SHORE_MIN_X)})" in body
    assert R.LOS_REGIONS.index("North Shore") == 3 and "report 3 ]" in body
    for name, cx, cy, radius in R.LOS_REGION_DISCS:
        j = R.LOS_REGIONS.index(name)
        line = next(ln for ln in body.splitlines() if f"report {j} ]" in ln)
        assert f"(mid-x - {int(cx)})" in line and f"(mid-y - {int(cy)})" in line, name
        assert f"<= {int(radius)} * {int(radius)}" in line, name
    assert R.LOS_REGIONS[-1] == "Other roads" and "report last-region-index" in body


def test_plot_legends_and_axes_stay_short() -> None:
    """The queue plot's legend names each corridor without its roads in brackets (with them, five
    corridors' legend took most of the plot's height), the pen being created and fed under the same name,
    and the plots' hour axis ends at a quarter hour (not 10.18333...)."""
    code = _code()
    pen = '(word item k corr-ids ": " corridor-entry-name item k corr-names)'
    assert f"create-temporary-plot-pen {pen}" in _procedure(code, "setup-day-plots")
    assert 'set-current-plot-pen (word cid ": " corridor-entry-name item k corr-names)' in _procedure(code, "plot-until")
    assert "substring roads-text 0 comma" in _procedure(code, "corridor-entry-name")
    assert "let x1 15 * ceiling (" in _procedure(code, "setup-day-plots")


def test_info_tab_says_why_los_ef_saturates() -> None:
    """Where LoS E/F is shown, so is why it saturates (2026-10-09): the Info tab's Level of service
    paragraph says the other roads' capacity is a scale fitted to the TomTom index (about 99% E/F from
    07:00) and that the motorways' usual breakdown windows are graded F whatever the flow, and that the
    mean V/C is shown beside the share."""
    par = _info_paragraph("Level of service.")
    for words in ("mean V/C", "TomTom congestion index", "about 99%", "usual breakdown windows",
                  "graded F whatever the flow", "Read the two together"):
        assert words in par, words


def _code() -> str:
    return ET.parse(MODEL).getroot().find("code").text or ""


def _procedure(code: str, name: str) -> str:
    """The body of procedure name (to or to-report) in the model's code."""
    m = re.search(rf"^to(?:-report)? {re.escape(name)}\b.*?^end$", code, re.M | re.S)
    assert m, name
    return m.group(0)


def _choosers() -> dict[str, ET.Element]:
    return {w.attrib["variable"]: w for w in _widgets() if w.tag == "chooser"}


def _choices(w: ET.Element) -> list[str]:
    assert all(c.attrib["type"] == "string" for c in w.findall("choice"))
    return [c.attrib["value"] for c in w.findall("choice")]


def test_input_widgets_show_their_variable_name() -> None:
    """Every chooser, switch, slider and input box shows its variable name (display = variable). The
    NetLogo 7 GUI defines the widget's global from its display name, while the headless workspace uses
    the variable attribute: the "PT disruption" display of the pt-disruption chooser (2026-10-10) loaded
    fine headless but left pt-disruption undefined in the GUI (2026-10-13)."""
    for w in _widgets():
        if w.tag in ("chooser", "switch", "slider", "inputBox"):
            assert w.attrib["display"] == w.attrib["variable"], (w.tag, w.attrib["variable"], w.attrib["display"])


def test_public_transport_riders_are_buses() -> None:
    """Each commuter on public transport today is drawn by one turtle of the breed bus-riders (2026-10-13),
    made in start-day with the shape "bus" of the model's shapes; the commuter keeps its data and is hidden
    (place-bus-rider), and drawn-agent says which turtle draws a commuter (check_network_model.py uses it)."""
    code = _code()
    assert "breed [ bus-riders bus-rider ]" in code and "bus-riders-own [ rider ]" in code
    assert code.index("breed [ commuters commuter ]") < code.index("breed [ bus-riders bus-rider ]") < code.index("breed [ tags tag ]")
    start = _procedure(code, "start-day")
    assert "ask bus-riders [ die ]" in start and 'hatch-bus-riders 1 [ set rider myself  set shape "bus"' in start
    assert "ask bus-riders [ place-bus-rider ]" in _procedure(code, "update-commuters")
    assert "ask c [ set hidden? true ]" in _procedure(code, "place-bus-rider")
    assert "one-of bus-riders with [ rider = myself ]" in _procedure(code, "drawn-agent")
    shapes = ET.parse(MODEL).getroot().find("turtleShapes")
    assert "bus" in [s.attrib["name"] for s in shapes.findall("shape")]
    note = next(w for w in _widgets() if w.tag == "note" and HOW_TO in (w.text or ""))
    assert "green buses are commuters on public transport" in (note.text or "")


def test_experiment_chooser_lists_the_experiments() -> None:
    """experiment is a chooser (no typing) of readable labels (who decides, when, the peak charge), the rule
    reacting to events at NZ$6 first. setup reads the run folder of the label through run-folder-of
    (experiment-labels and experiment-folders, in the same order as the chooser); each folder is a run
    folder (agents.csv) under runs/. A missing one must be made with python -m cordonlite.run (the $18 runs
    with --peak-fee 18). setup-run, which the scripts call with any folder, takes the folder itself."""
    ch = _choosers()
    assert "experiment" in ch and "scenario-dir" not in ch
    assert not [w for w in _widgets() if w.tag == "input"]
    choices = _choices(ch["experiment"])
    assert choices == [label for label, _ in EXPERIMENTS]
    assert ch["experiment"].attrib["current"] == "0"
    code = _code()
    assert re.findall(r'"([^"]+)"', _procedure(code, "experiment-labels")) == choices
    folders = re.findall(r'"([^"]+)"', _procedure(code, "experiment-folders"))
    assert folders == [folder for _, folder in EXPERIMENTS]
    missing = [c for c in folders if not (MODEL.parent / c / "agents.csv").is_file()]   # as NetLogo resolves it
    assert not missing, f"run folders without agents.csv (make them with python -m cordonlite.run): {missing}"
    # every experiment is 10 days, charged from day 6 (--days 10 --fee-start 6): five days without, five with
    for c in folders:
        scen = pd.read_csv(MODEL.parent / c / "scenario.csv").set_index("key")["value"]
        assert (scen["charge_from_day"], scen["n_days"]) == (6, 10), c
        assert sorted(pd.read_csv(MODEL.parent / c / "plans.csv")["day"].unique()) == list(range(1, 11)), c
    # the PT disruption chooser: none, or day 3 (before the charge starts on day 6) and day 8 (with it); the
    # run folder of an experiment and a disruption is the experiment's folder with the suffix
    dis = _choosers()["pt-disruption"]
    assert _choices(dis) == [label for label, _, _ in DISRUPTIONS] and dis.attrib["current"] == "0"
    assert re.findall(r'"([^"]+)"', _procedure(code, "pt-disruption-labels")) == _choices(dis)
    assert re.findall(r'"([^"]*)"', _procedure(code, "pt-disruption-suffixes")) == [s for _, s, _ in DISRUPTIONS]
    assert "setup-run run-folder-of experiment pt-disruption" in _procedure(code, "setup")
    for _label, suffix, days in DISRUPTIONS:
        for c in folders:
            run = MODEL.parent / (c + suffix)
            assert (run / "agents.csv").is_file(), f"make it with --set events.pt_disruption_day=[3,8]: {run}"
            meta = json.loads((run / "summary.json").read_text())["meta"]
            assert (run / "plans.csv").is_file() and meta["n_days"] == 10 and meta["fee_start_day"] == 6, run
            assert meta["pt_disruption_day"] == (list(days) if days else 0), run   # 0 = none (2026-10-15)
            if days:   # each disruption wakes the PT users of its corridor on the day (T4) and the day after
                dec = pd.read_csv(run / "decisions.csv")
                woken = sorted(dec[dec["triggers"].fillna("").str.contains("T4")]["day"].unique())
                assert woken == sorted(d + k for d in days for k in (0, 1)), (run, woken)
    assert "setup-run run-folder-of experiment" in _procedure(code, "setup")
    assert 'error (word "There is no run in "' in _procedure(code, "setup-run")

def test_info_tab_and_note_name_the_peak_charges() -> None:
    """The Info tab says what the experiments are (who decides, when, and the peak charges NZ$6 and NZ$18,
    compared on the same days; behaviour calibrated at NZ$6) and the how-to note says that $6 is the usual
    charge and $18 a higher one. A run folder's fees.csv peaks at its charge (NZ$6 without a suffix); folders
    not made yet are reported by test_experiment_chooser_lists_the_experiments. No _fx or _peak0 text is
    left: a run without a charge is not an experiment."""
    runs = _info_paragraph("The experiments in the experiment chooser:")
    assert f"usual peak charge of NZ${BASE_PEAK}" in runs and "NZ$18 instead" in runs
    assert "on the same days" in runs and f"calibrated with the NZ${BASE_PEAK} charge" in runs
    note = next(w for w in _widgets() if w.tag == "note" and HOW_TO in (w.text or ""))
    assert "$6 is the usual charge, $18 a higher one" in (note.text or "")
    text = MODEL.read_text(encoding="utf-8")
    assert "_fx" not in text and "_peak0" not in text
    for _, folder in EXPERIMENTS:
        f = MODEL.parent / folder / "fees.csv"
        peak = int(m.group(1)) if (m := re.search(r"_peak(\d+)$", folder)) else BASE_PEAK
        if f.is_file():
            assert float(pd.read_csv(f)["fee"].max()) == peak, (folder, peak)

def test_no_skip_choice_in_the_text() -> None:
    """SKIP is gone (2026-10-09): every commuter drives, takes PT or works from home. No SKIP mode or
    postponed trip is named anywhere in the model, the dots' grey means working from home, and the Info
    tab's background (not the how-to steps) gives the willingness to pay that falls exponentially with the
    charge. ("skip to end of day" is the finish-day button.)"""
    text = MODEL.read_text(encoding="utf-8")
    assert "SKIP" not in text
    for words in ("postpone", "stays home", "stay home"):
        assert words not in text.lower(), words
    note = next(w for w in _widgets() if w.tag == "note" and HOW_TO in (w.text or ""))
    assert "grey = works from home" in (note.text or "")
    info = ET.parse(MODEL).getroot().find("info").text or ""
    what = info.split("## WHAT IS IT?", 1)[1].split("\n## ", 1)[0]
    assert "takes public transport or works from home" in what
    wtp = [s for s in _sentences(what) if "willingness to pay" in s]
    assert len(wtp) == 1 and "falls exponentially as the charge rises" in wtp[0], wtp
    how = info.split("## HOW TO USE IT", 1)[1].split("\n## ", 1)[0]
    for where, t in (("note", note.text or ""), ("HOW TO USE IT", how)):
        assert "willingness" not in t and "exponential" not in t, where


def test_charge_on_is_not_a_widget_and_setup_plays_the_charged_days() -> None:
    """charge-on (which days go plays) has no widget: setup-run sets it to "all days" (the check
    scripts set the other two). The code compares charge-on with exactly these strings, go and finish-day
    start the day next-day-to-show gives (not simply the next day), and today's charge comes from
    charged-day? (the old charge-on? would read like the variable)."""
    assert "charge-on" not in _choosers()
    code = _code()
    assert 'set charge-on "all days"' in _procedure(code, "setup-run")
    assert set(re.findall(r'charge-on = "([^"]+)"', code)) == set(CHARGE_ON[1:])
    assert "[ " + " ".join(f'"{c}"' for c in CHARGE_ON) + " ]" in _procedure(code, "days-to-show")
    for proc in ("go", "finish-day"):
        body = _procedure(code, proc)
        assert "next-day-to-show" in body and "current-day + 1" not in body, proc
        assert "if is-string? d [ user-message d  stop ]" in body, proc
    assert "set fee-active-today? charged-day? d" in _procedure(code, "start-day")
    assert "charge-on?" not in code


def test_no_fee_start_day_or_demo_scenario() -> None:
    """The fee-start-day input is gone (a run's scenario.csv says when its charge starts; 11 without it, as
    config.toml) and so is the demo_scenario folder: no widget, code or Info tab text names them."""
    text = MODEL.read_text(encoding="utf-8")
    for word in ("fee-start-day", "demo_scenario"):
        assert word not in text, word
    assert "set charge-from-day 11" in _procedure(_code(), "read-scenario-meta")


def test_no_charged_today_monitor_and_unique_labels() -> None:
    """The "charged today" monitor is gone (2026-10-10: go plays only the charged days, so it was always
    true), and no two widgets share a label."""
    ws = _widgets()
    mons = {w.attrib["display"]: (w.text or "").strip() for w in ws if w.tag == "monitor"}
    assert "charged today" not in mons and "fee-active-today?" not in mons.values()
    labels = [w.attrib.get("display") for w in ws if w.tag not in ("view", "note")]
    assert None not in labels and len(labels) == len(set(labels)), labels


def test_how_to_steps_are_short_and_in_order() -> None:
    """The on-screen note and the Info tab's HOW TO USE IT are a few numbered steps in the order of use:
    setup, go, keep-going?, the views."""
    note = next(w for w in _widgets() if w.tag == "note" and HOW_TO in (w.text or ""))
    info = ET.parse(MODEL).getroot().find("info").text or ""
    how = info.split("## HOW TO USE IT", 1)[1].split("\n## ", 1)[0]
    order = ["setup", "go", "keep-going?", "view"]
    for where, text in (("note", note.text or ""), ("Info tab", how)):
        steps = [ln for ln in text.split("\n") if re.match(r"\d+\. ", ln)]
        assert [int(s.split(".")[0]) for s in steps] == list(range(1, len(order) + 1)), (where, steps)
        for s, word in zip(steps, order):
            assert word in s, (where, word, s)
