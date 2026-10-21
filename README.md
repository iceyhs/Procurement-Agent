# Procurement Agent

Python 3.12+ CLI for the Aron procurement exercise. It reconciles free-text supplier
quotes against a buyer's requirements and produces an evidence-backed Markdown
report. It uses OpenRouter and Python's standard library, with no runtime dependencies.

## Setup

```bash
cd /workspace/Procurement-Agent
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
test -e .env || cp .env.example .env
# Edit .env locally: add your key and choose your model. Do not share the file.
set -a
. ./.env
set +a
```

The CLI reads process environment variables; it does not automatically load .env.
Alternatively export OPENROUTER_API_KEY and OPENROUTER_MODEL directly. HTTPS access
to openrouter.ai and an account with access/credits for the selected model are
required. Each check/review sends real API requests and may incur charges. To test
the configured account separately, run `.venv/bin/procurement-agent check`.

## Review a packet

```bash
.venv/bin/procurement-agent review examples/quote_packet.txt
# Or use your own input and output paths:
.venv/bin/procurement-agent review quote_packet.txt --output report.md
```

The default output is `report.md` in the current directory. Existing reports are
preserved unless you pass `--force`. A failed review leaves the previous report
intact; output cannot be the input file. Successful runs print the output path.

### Input format

Use one local UTF-8 file. The first block contains free-text buyer requirements.
Each subsequent block contains one supplier reply copied from an email, message,
or document. Separate blocks with `===PACKET===` on its own line; spaces inside
the separator (`=== PACKET ===`) are also accepted. No headings or internal
template are required. All replies concern the same RFQ; independent RFQs require
separate runs. PDF parsing is outside the MVP.

```text
We need machined aluminium bracket BRK-4471-A, 60,000 units a year.
Our release schedule is not confirmed.

===PACKET===

From: supplier@example.com
BRK-4471-A: USD 4.85 per piece, releases of 5,000 or more.
Tooling USD 6,200. Lead time 4 weeks from release. Net 30.

===PACKET===

[Another supplier's original reply]
```

The complete four-supplier exercise is in `examples/quote_packet.txt`. Say
"a year" when quantity means annual demand: "60,000 units" alone is unspecified.
Missing revision, finish, destination, delivery date, and other requirements are
reported as unknown rather than inferred from suppliers. Limits: 100,000 UTF-8
bytes and eight supplier replies per run.

### Report

1. **Normalized supplier comparison** — buyer requirements, quote terms, price
   normalization, conditional quantity extensions, and exact source excerpts.
2. **Risks / unknowns** — harness warnings and model assessment.
3. **Shortlist / recommendation** — conditional next steps, not an award decision.
4. **Follow-up questions** — drafts grouped by buyer and supplier, ordered by impact.

Unit-price extensions are not landed costs or confirmed ordering plans. Currencies
remain separate; bare `$` is not automatically USD. Unknown charges remain unknown.
Refundable container deposits are shown separately from permanent cost. Payment
discounts, index changes, and amortization savings are not automatically applied.
The tooling scenario adds one separately quoted charge, explicitly as an assumption;
no tooling total is calculated when amount/currency is unresolved or differs from
the price currency. Decimal arithmetic avoids intermediate money rounding.

### Architecture and boundaries

```text
cli.py -> agent.py -> harness.py
                       read/split -> LLM extraction -> validate
                       -> calculate -> LLM analysis -> validate -> render/save
```

- `agent.py`: public review interface.
- `harness.py`: per-run state, workflow, call budget, and validation policy.
- `prompts.py`: extraction and analysis instructions.
- `schema.py`: field contracts, response shape checks, numeric evidence checks,
  exact-excerpt matching (ignoring whitespace), and source validation.
- `tools/packet.py`, `tools/calculations.py`, `tools/report.py`: application tools
  invoked by application code. **No tools are exposed to the model.**
- `openrouter.py`: HTTPS transport and safe provider errors.

Model responses use JSON contracts. Each extracted field is
`{"value": "...", "evidence": "exact source excerpt"}` or
`{"value": null, "evidence": null}`. Prices retain their original denominator
until the harness calculates per-piece amounts. Numeric fields use decimal strings.

Normally there are two model calls: extraction, then analysis of validated facts
and calculations. At most one additional correction call is allowed across both
stages (three calls maximum). Provider/transport failures are not retried. Each
request has a 60-second network timeout and a bounded output-token budget.
State is in memory for that run; there is no database or cross-run conversation.

The packet is sent to OpenRouter and its model provider. Source text is treated
as untrusted data, and model text is escaped during report rendering. Evidence
matching verifies traceability, not that an interpretation is correct or every
important term was extracted. Narrative conclusions and technical compliance
still require buyer review. The agent cannot send email, negotiate, or place orders.

## Tests (no API key or network required)

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Tests cover the reference packet's calculations, parsing, evidence validation,
missing fields, call limits, report sections, output preservation, and a CLI run
through the OpenRouter adapter with mocked HTTP. They do not establish live model
quality. For live acceptance, run the example and review the generated facts,
evidence, revision discrepancies, cost exclusions, shortlist, and questions against
the original packet.
