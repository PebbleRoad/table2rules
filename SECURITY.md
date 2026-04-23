# Security policy

## Threat model

`table2rules` parses untrusted HTML. The design assumes hostile input — any
HTML, from any source, including adversarial markup crafted to trigger
resource exhaustion. Its safety contract:

- **Bounded memory.** Per-cell `rowspan` / `colspan` are clamped to 1000,
  and any table whose expanded grid would exceed 1,000,000 cells is
  rejected with `render_mode="skipped"` rather than expanded.
- **Fail-open.** When invariants or confidence checks fail, the library
  degrades to flat rows or raw HTML passthrough. It does not fabricate
  structure.
- **No network, no subprocess, no filesystem writes.** The library is
  pure-Python transformation over in-memory strings.

Bugs that violate any of the above — in particular, inputs that cause
unbounded memory growth, runaway CPU, or injected content that wasn't in
the source HTML — are treated as security issues.

## Reporting a vulnerability

Please **do not** file a public GitHub issue for suspected vulnerabilities.

Use GitHub's private [security advisory
form](https://github.com/pebbleroad/table2rules/security/advisories/new)
for this repository. If that isn't available to you, email
`maish.nichani@gmail.com` with:

- A minimal HTML input that reproduces the issue.
- A description of the observed behavior (OOM, hang, fabricated output,
  etc.) and what you expected.
- The `table2rules` version (`python -c "import table2rules;
  print(table2rules.__version__)"`).

You'll get an acknowledgement within 5 working days. Fixes for confirmed
vulnerabilities ship in a patch release with credit in
[CHANGELOG.md](CHANGELOG.md) unless you ask to stay anonymous.

## Supported versions

Only the latest minor release line receives security fixes.
