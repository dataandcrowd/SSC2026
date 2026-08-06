"""Re-assemble paper_update_combined.md from the individual pack files.

Rules (matching the 2026-07-29 hand-built original): each source file's first
`# ` title line is dropped, every other heading is demoted one level (## ->
###), content is otherwise verbatim; each section gets an anchor, a `##`
header and a `*Source file*` line. Headings inside fenced code blocks are
left alone.

Usage:  python build_combined.py   (from paper_update/ or anywhere)
"""
import datetime
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

SECTIONS = [
    ("overview", "Overview", "README.md"),
    ("abstract", "Abstract", "abstract_revised.md"),
    ("methods", "Methods", "methods_revised.md"),
    ("results", "Results", "results_revised.md"),
    ("behavioural-extensions", "Behavioural extensions", "behavioural_extensions.md"),
    ("conclusion", "Conclusion", "conclusion_revised.md"),
    ("conclusions-as-bullets", "Conclusions as bullets", "conclusions_bullets.md"),
    ("numbers-and-sources", "Numbers and sources", "numbers.md"),
    ("decisions-log", "Decisions log", "decisions_log.md"),
]


def demote(text):
    out, fence = [], False
    dropped_title = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            out.append(line)
            continue
        if not fence and re.match(r"^#{1,5} ", line):
            if not dropped_title and line.startswith("# "):
                dropped_title = True
                continue
            out.append("#" + line)
            continue
        out.append(line)
    return "\n".join(out).strip("\n")


def main():
    today = datetime.date.today().isoformat()
    parts = [
        "# Manuscript update pack — calibrated model",
        "",
        f"*SSC2026 cordon-pricing paper. Combined from `paper_update/` on {today}. "
        "Calibrated NetLogo model (scale-factor 160, suburban destinations) after "
        "the trip-suppression fix; all four arms re-run 2026-08-06, 14 simulated "
        "days, seed 11.*",
        "",
        "## Contents",
        "",
    ]
    for slug, title, fname in SECTIONS:
        parts.append(f"- [{title}](#{slug}) — `{fname}`")
    for slug, title, fname in SECTIONS:
        with open(os.path.join(HERE, fname), encoding="utf-8") as f:
            body = demote(f.read())
        parts += ["", "---", "", f'<a id="{slug}"></a>', "", f"## {title}", "",
                  f"*Source file: `{fname}`*", "", "", body]
    out = os.path.join(HERE, "paper_update_combined.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(parts) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
