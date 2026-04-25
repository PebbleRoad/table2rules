# Integrating table2rules into your pipeline

This doc is for engineers wiring `table2rules` into a production pipeline —
RAG ingestion, document-conversion services, or any batch system that needs
to know when a conversion went sideways, not just what it produced.

The [README](../README.md) covers what the library does and a minimal
hello-world. This doc covers the questions that come up on day two: how to
route flagged tables, how to categorize failures, and what the failure modes
actually mean.

## Table of contents

- [Minimum viable integration](#minimum-viable-integration)
- [End-to-end example](#end-to-end-example)
- [TableReport reference](#tablereport-reference)
- [Render modes: what each one means](#render-modes-what-each-one-means)
- [Reason codes: severity and grouping](#reason-codes-severity-and-grouping)
- [gate_score interpretation](#gate_score-interpretation)
- [Batch aggregation](#batch-aggregation)
- [Strict mode for tests and development](#strict-mode-for-tests-and-development)
- [Logging](#logging)
- [Thread safety](#thread-safety)
- [Custom exporters](#custom-exporters)
- [A conservative policy template](#a-conservative-policy-template)

## Minimum viable integration

If you only have five minutes, this is enough:

```python
import logging
from table2rules import process_tables_with_stats

logger = logging.getLogger(__name__)

text, report = process_tables_with_stats(html)

for t in report.tables:
    if t.render_mode != "rules":
        logger.warning(
            "table2rules degraded: index=%d mode=%s reasons=%s",
            t.table_index, t.render_mode, t.reasons,
        )
```

You now have structured signal on every call. Everything below is about
turning that signal into policy.

## End-to-end example

A realistic integration does three things with the report: log degraded
tables, aggregate counts to the run record, and route a subset (e.g. hostile
input) to an alternate pipeline. Here is the full shape:

```python
import logging
from dataclasses import dataclass, field
from typing import List

from table2rules import process_tables_with_stats, RenderReport, TableReport

logger = logging.getLogger(__name__)


@dataclass
class DocumentResult:
    doc_id: str
    text: str
    report: RenderReport
    reprocess_queue: List[int] = field(default_factory=list)


def convert_document(doc_id: str, html: str) -> DocumentResult:
    text, report = process_tables_with_stats(html)

    reprocess: List[int] = []
    for t in report.tables:
        if t.render_mode == "rules":
            continue

        logger.warning(
            "table degraded doc=%s index=%d mode=%s reasons=%s score=%.2f",
            doc_id, t.table_index, t.render_mode, list(t.reasons), t.gate_score,
        )

        # Policy: route too-large tables to the VLM table pipeline instead,
        # alert on passthrough (raw HTML escaping into downstream text),
        # silently accept flat fallback for now.
        if "input_too_large" in t.reasons:
            reprocess.append(t.table_index)
        elif t.render_mode == "passthrough":
            logger.error(
                "doc=%s table=%d emitted raw HTML — downstream may misparse",
                doc_id, t.table_index,
            )

    return DocumentResult(
        doc_id=doc_id,
        text=text,
        report=report,
        reprocess_queue=reprocess,
    )


def process_batch(docs: list[tuple[str, str]]) -> None:
    results = [convert_document(doc_id, html) for doc_id, html in docs]
    batch = RenderReport.merge(r.report for r in results)
    logger.info(
        "batch complete: %d rendered, %d flagged across %d documents",
        batch.tables_rendered, batch.tables_flagged, len(results),
    )
```

The shape of this code stays the same whether you have two documents or two
million. The policy (which reasons trigger which action) is up to you.

## TableReport reference

Every `TableReport` in `report.tables` has these fields:

| Field | Type | Meaning |
|-------|------|---------|
| `table_index` | `int` | 0-based position among **top-level** `<table>` elements in the input HTML. Nested tables are folded into their parent's cell text and do not get their own index. Input HTML with N top-level tables always produces N reports. |
| `render_mode` | `Literal["rules","flat","passthrough","skipped"]` | Which output path this table took. See [Render modes](#render-modes-what-each-one-means) for semantics. |
| `gate_ok` | `bool` | `True` iff the quality gate accepted this table's rules output. When `False`, fallback kicked in. |
| `gate_score` | `float` | Continuous confidence in `[0, 1]`. See [gate_score interpretation](#gate_score-interpretation). `0.0` when the table was skipped before scoring. |
| `reasons` | `Tuple[str, ...]` | Stable reason codes from the `REASONS` catalogue. Empty when `render_mode == "rules"`. |
| `error` | `Optional[str]` | Exception message captured when `strict=False` swallowed a parse error. `None` otherwise. |

All fields are frozen — `TableReport` is safe to cache, hash, or pickle.

## Render modes: what each one means

`render_mode` is the single most important field for policy. Each value
corresponds to a different output quality and deserves a different reaction.

The four values are also available as module-level constants —
`RENDER_MODE_RULES`, `RENDER_MODE_FLAT`, `RENDER_MODE_PASSTHROUGH`,
`RENDER_MODE_SKIPPED` — if you'd rather not sprinkle string literals through
your policy code:

```python
from table2rules import RENDER_MODE_PASSTHROUGH

if t.render_mode == RENDER_MODE_PASSTHROUGH:
    ...
```

They are the string literals, not an enum — equality against the raw
strings still works, so adopting them is a drop-in change.

### `"rules"` — clean conversion

The gate accepted the output; each line in `text` is a self-contained
`row-path | col-path: value`. Take no action. This is the ~95% case on
well-formed input.

### `"flat"` — header-free fallback

The gate rejected rules output and the library fell back to pipe-joined raw
cell rows (`"A | B | C"` per row). Rows still round-trip correctly but
**header context is missing** — downstream retrieval may match the values
without knowing which column they belong to.

**Operational stance:** log at warning; accept the output if your downstream
can tolerate header-free rows (e.g. OCR receipts, homogeneous invoices); route
to an alternate extractor if header context is critical.

### `"passthrough"` — raw HTML in your text stream

**This is the loudest signal the library emits short of raising.** Neither
rules nor flat extraction produced anything usable, so the library emitted
the raw `<table>...</table>` HTML into the output string.

If you feed that string to an LLM or embedder without filtering, the model
sees HTML markup mid-stream and will either parse it or treat it as
gibberish. Both outcomes are bad.

**Operational stance:** log at error; filter or re-process; do not pass
through to the LLM unmodified. The text field still contains the raw HTML
for those tables — you can detect `<table` substrings as a belt-and-braces
check before sending to the model.

### `"skipped"` — input was refused

The library declined to process the table. Today this only happens for
span-bomb input (clamped rowspan/colspan producing an expanded grid past the
1M-cell cap), surfaced as `reasons=("input_too_large",)`.

**Operational stance:** alarm; this is almost always a signal that your
upstream extractor handed you malformed or adversarial HTML. Investigate the
source document before lowering the alarm threshold.

## Reason codes: severity and grouping

The full `REASONS` catalogue is 16 codes today. Not all carry the same
operational weight. The grouping below is also available programmatically
as `REASONS_BY_SEVERITY` — a `dict[str, frozenset[str]]` with three buckets
(`"defensive"`, `"confidence"`, `"input"`) — so you can build exhaustive
switch statements and auto-populated metrics dashboards without hardcoding
the lists from this doc:

```python
from table2rules import REASONS_BY_SEVERITY

if any(r in REASONS_BY_SEVERITY["input"] for r in t.reasons):
    escalate_to_upstream(t)
elif any(r in REASONS_BY_SEVERITY["confidence"] for r in t.reasons):
    log_degraded(t)
elif any(r in REASONS_BY_SEVERITY["defensive"] for r in t.reasons):
    open_library_bug(t)
```

Every code in `REASONS` appears in exactly one bucket — enforced by tests,
so the partition is safe to treat as total.

### Defensive invariants (shouldn't fire — file an issue)

These are structural checks the library runs on its own output. They should
never appear in production unless the library itself has a bug. If you see
one, capture the HTML and open an issue against `table2rules`.

- `empty_grid`
- `position_out_of_bounds`
- `non_td_rule_cell`
- `header_cell_emitted`
- `empty_rule_outcome`
- `empty_header_text`

### Confidence signals (soft — tune policy against these)

The gate computed a low-confidence verdict and fell back. These are the
codes you'll see most often on real-world input, and they're the ones worth
tracking as metrics.

- `no_candidate_data_cells` — table had no data cells at all
- `low_coverage` — fewer than 60% of data cells produced rules
- `low_header_attachment` — fewer than 25% of rules have header context
- `high_self_echo` — >50% of rules repeat their column header as value
- `high_duplicate_positions` — at least one logical grid position produced multiple rules
- `high_position_conflict` — at least one logical grid position carried conflicting outcomes
- `numeric_column_headers` — first row likely misread as header
- `placeholder_column_headers` — column headers are underscores/dashes

### Input-side signals (your upstream sent bad data)

- `input_too_large` — adversarial or malformed span values
- `processing_error` — parser raised an exception; see `TableReport.error`

Treat input-side reasons differently from confidence reasons: the fix isn't
in table2rules, it's upstream.

## gate_score interpretation

`gate_score` is a continuous number in `[0, 1]` produced only when the
library actually ran the gate (i.e. not for `"skipped"` tables). It's a
weighted combination of data coverage, header attachment, and the various
penalty signals.

No strict threshold, but as rough anchors:

| Score range | Typical meaning |
|-------------|-----------------|
| ≥ 0.90 | Clean parse, high confidence. `gate_ok == True`. |
| 0.60 – 0.90 | Mild signals flagged but structure is sound. `gate_ok` can go either way depending on which signals fired. |
| 0.30 – 0.60 | Meaningful structural ambiguity; the gate usually rejects. |
| < 0.30 | Structure mostly absent or severely malformed. |

If you want a single numeric dial for your alerting, `gate_score < 0.6` is a
reasonable starting line — it cleanly separates ordinary parses from weak
ones in our test corpus. Tune from there against your own data.

## Batch aggregation

`RenderReport.merge` concatenates per-call reports into one aggregate:

```python
from table2rules import RenderReport, process_tables_with_stats

# Keep both the text and the report from each call.
results = [process_tables_with_stats(html) for html in documents]

# Merge just the reports for a run-level view.
batch = RenderReport.merge(report for _, report in results)

print(f"{batch.tables_rendered} rendered, {batch.tables_flagged} flagged")
```

Per-report `table_index` values are preserved as-is — they still refer to
positions within each original call, not the merged sequence. If you need a
globally unique identifier across the batch, pair each report with its
document id yourself.

## Strict mode for tests and development

Every entry point that can fail open takes `strict=False` by default.
Passing `strict=True` flips the library from "swallow and signal" to "raise
and fail":

```python
from table2rules import process_tables_with_stats, TableTooLargeError

# In tests / dev — surface failures loudly.
text, report = process_tables_with_stats(html, strict=True)

# TableTooLargeError is a Table2RulesError subclass, so you can catch either.
try:
    process_tables_with_stats(untrusted_html, strict=True)
except TableTooLargeError:
    ...
```

Use `strict=True` in:
- Tests that assert on specific failure modes
- CLI tools where a visible traceback is preferable to silent degradation
- Development loops where you want parse errors front-and-centre

Keep `strict=False` (the default) in production pipelines that process
untrusted or mixed-quality input.

## Logging

`table2rules` deliberately does **not** call `logging.warning(...)` or any
other log function on its own. The library returns signals; routing them
through your logger is your job. This keeps the library a good citizen in
applications with structured logging, log filtering, or custom handlers.

If you want the same format as the examples in this doc, wire the stats
output through your logger once at the integration boundary and every
downstream component inherits your formatting.

## Thread safety

The library's processing functions are **pure with respect to shared state**
— no module-level mutable globals are written during a call. You can safely
call `process_tables_to_text` / `process_tables_with_stats` from multiple
threads or processes in parallel.

One caveat: the exporter registry (`register_exporter(...)`) writes to a
process-global dict. Register all custom exporters once at import time,
before any worker threads start processing.

## Custom exporters

Output formatting is pluggable. Any object with two methods — `export_rules`
(given a list of `LogicRule`) and `export_flat` (given a list of cell-text
rows, used when the gate fails and the library falls back to header-free
output) — satisfies the `Exporter` protocol:

```python
from typing import List

from table2rules import Exporter, LogicRule, register_exporter, process_tables_to_text


class JsonlExporter:
    name = "jsonl"

    def export_rules(self, rules: List[LogicRule]) -> List[str]:
        import json
        return [
            json.dumps({
                "row": " > ".join(r.row_headers),
                "col": " > ".join(r.col_headers),
                "value": r.outcome.strip(),
            })
            for r in rules
        ]

    def export_flat(self, cell_rows: List[List[str]]) -> List[str]:
        # Called only when the quality gate fails. You can return [] to
        # suppress fallback output entirely, or emit something that makes
        # sense for your format.
        return [" | ".join(r) for r in cell_rows if any(r)]


register_exporter(JsonlExporter())
print(process_tables_to_text(html, format="jsonl"))
```

The registered name is what you pass to `format=...`. Check what's
registered with `available_exporters()`:

```python
from table2rules import available_exporters
available_exporters()   # -> ['rules', 'jsonl']
```

Both exporter methods should return `List[str]`. The library joins the
list with `\n` between tables, so each element is typically one line.

### Combining a custom exporter with stats

`process_tables_with_stats` accepts the same `format=` keyword as
`process_tables_to_text` — you can get a custom-formatted string *and* the
structured report from the same call:

```python
from table2rules import process_tables_with_stats

text, report = process_tables_with_stats(
    html,
    format="jsonl",
    strict=False,
)
```

`format=` and `strict=` compose independently — there's no need to pick
between "custom format" and "observability."

## A conservative policy template

If you're wiring this up for the first time, start here:

```python
from table2rules import process_tables_with_stats, RenderReport

def convert(html: str, doc_id: str, logger) -> tuple[str, RenderReport]:
    text, report = process_tables_with_stats(html)

    for t in report.tables:
        # Baseline: log everything non-clean at the appropriate level,
        # do nothing automatic. No retry, no re-routing, no failing docs.
        # Collect data for a week. Then tune.
        if t.render_mode == "skipped" or "processing_error" in t.reasons:
            logger.error(
                "doc=%s table=%d failed: mode=%s reasons=%s error=%s",
                doc_id, t.table_index, t.render_mode,
                list(t.reasons), t.error,
            )
        elif t.render_mode == "passthrough":
            logger.error(
                "doc=%s table=%d emitted raw HTML into output",
                doc_id, t.table_index,
            )
        elif t.render_mode == "flat":
            logger.warning(
                "doc=%s table=%d degraded to flat: reasons=%s score=%.2f",
                doc_id, t.table_index, list(t.reasons), t.gate_score,
            )

    return text, report
```

This does nothing *clever*. It captures the signal at the right severity so
you can see real traffic before deciding on retry/route/fail policies. Most
teams end up with exactly this structure plus one or two specific routes
(e.g. `input_too_large` → VLM pipeline) after observing a week of
production traffic.
