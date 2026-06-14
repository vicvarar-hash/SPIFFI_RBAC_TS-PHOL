# PALADIN Experiment Report — Canonical Format

> Read this before writing a new report. Every report in `reports/*.md` (excluding
> files prefixed with `_`) appears as a selectable entry in **Experiment Lab → 📑 Reports**.
> The Reports tab simply renders the markdown — no other parsing happens.

## File naming

```
reports/YYYY-MM-DD_<scope>_<short-slug>.md
```

Examples:
- `2026-06-14_validation_four_models.md`
- `2026-06-14_selection_baseline_vs_bm25.md`
- `2026-07-02_selection_abc_ceiling.md`

The dropdown in the UI sorts by filename descending (newest first by date).

## Front matter (first lines)

The first non-empty line must be an H1 with the report title. The next line
should be a `> ` blockquote with metadata: date · author · evaluation mode ·
models tested. The Reports tab does **not** parse this — it's a human-readable
header only.

```markdown
# <Report title>

> **Date:** YYYY-MM-DD · **Author:** <name> · **Mode:** validation | selection · **Models:** <model list>
```

## Required sections (in order)

Every report must include the following sections, in this order. Skip sections
that don't apply (e.g., "ASTRA comparison" only applies to validation reports)
but keep the numbering stable so reviewers can reference sections across reports.

1. **TL;DR / Headline Result** — Three bullets max. The single most important
   finding and the single most important caveat.
2. **Experimental Setup** — Dataset, split, eval-mode, model(s), inference
   config (temperature, max tokens), sample size n.
3. **Metrics & How They're Calculated** — Define every metric used. Show the
   formula. Use a worked example with one row from the results.
4. **Methodology Details** — Any algorithm or technique used (BM25, capability
   pre-filter, RBAC scoping, RA-ICL, etc.). Include the math/pseudocode at a
   detail level the advisor can scrutinize.
5. **Results** — Tables first, prose second. Always include:
   - the absolute numbers
   - the delta vs the baseline/control
   - the sample size n
6. **ASTRA Comparison** (validation reports only) — What ASTRA did, what we
   did differently, apples-to-apples table.
7. **Dataset Quality Considerations** — Where labels are noisy, where the
   task is under-determined, where the metric is misleading. Required if the
   report mentions low accuracy.
8. **Learnings** — Numbered list of takeaways the reader should remember.
   Each learning should be supported by a specific result in §5.
9. **Limitations** — What the experiment does NOT show.
10. **Next Steps** — Bullet list of follow-up runs / open questions.

## Style rules

- **Tables > prose** for any quantitative comparison.
- **Every claim must have a number** (or a citation to the row that has it).
- **Define before use** for every acronym (RBAC, ABAC, TS-PHOL, RA-ICL, BM25,
  E1/E2/E3/E4, sec_fail, etc.).
- **No emojis in section headers** (they break markdown TOCs).
- **No external image links** (the report must render in the Streamlit panel
  without a network round-trip). Inline tables and ASCII diagrams only.
- **Always cite the log file** the numbers came from
  (`datasets/experiment_logs/run_YYYYMMDD_HHMMSS_*.json`).

## How the UI discovers reports

`app/ui/experiment_lab.py → _render_reports()`:

1. Scans `reports/*.md`.
2. Excludes files starting with `_` (this template, future drafts).
3. Sorts the list descending (newest filename first).
4. Renders the selected file via `st.markdown(..., unsafe_allow_html=False)`.

No code changes are needed to publish a new report — drop the `.md` file into
`reports/` and refresh the page.
