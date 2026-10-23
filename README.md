# Procurement Agent

Python 3.12+ CLI for the Aron procurement exercise. It reconciles free-text supplier
quotes against a buyer's requirements and produces an evidence-backed Markdown
report. It uses OpenRouter, Python's standard library, and `python-dotenv` for the
interactive chat entry point.

The bracket exercise is an example, not a runtime preset. Each run takes the item,
quantity and its basis, currency, relevant specifications, and supplier set from
the input. Optional manufacturing fields do not automatically create requirements
or follow-up questions for unrelated purchases. The MVP compares unit-priced goods
for one RFQ per run; mixed measurement units or service pricing need explicit
normalization support rather than being silently treated as per-piece prices.

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

## Interactive chat

After installing the project and filling in `.env`, run from the repository root:

```bash
.venv/bin/python main.py
```

This entry point automatically loads `.env` without overriding existing process
variables. Enter a question at `You:`; type `exit` or `quit` to leave. Conversation
history is kept in memory for this session and sent with each question; it is not
saved between runs. Each turn may incur API charges. Quotes must be provided in
the conversation; the agent does not automatically read repository files.
Chat is a separate free-text interface; use the `review` command below for the
validated extraction, deterministic calculations, and four-section report.

## Review a packet

Using `main.py` automatically loads the repository's `.env`, preserving existing
process variables, and runs the same CLI and harness:

```bash
.venv/bin/python main.py review examples/quote_packet.txt -o report.md
# For your own input:
.venv/bin/python main.py review quote_packet.txt -o report.md
```

`main.py check` runs the connection check; `main.py --help` shows CLI options.
Running `main.py` without arguments still opens interactive chat.

Alternatively, use the installed command after exporting the configuration:

```bash
.venv/bin/procurement-agent review examples/quote_packet.txt
# Or use your own input and output paths:
.venv/bin/procurement-agent review quote_packet.txt --output report.md
```

The default outputs are `report.md` and `report.pdf` in the current directory.
After saving Markdown, `review` automatically exports the PDF from that file,
without additional model calls. A custom `-o reviews/buyer.md` also creates
`reviews/buyer.pdf`. Existing outputs are preserved unless you pass `--force`;
output collisions are checked before model calls, and neither output can replace
the input. A failed model review leaves previous reports intact. If PDF export
fails, the saved Markdown is retained, any previous PDF is preserved, and the
command reports the export error with a nonzero exit status. Successful runs print both output paths.
Progress is flushed to stderr before each model request and during validation,
calculation, and saving, so a running request does not appear idle. Ctrl+C cancels
the local run with exit code 130. A network timeout is reported explicitly.

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
reported as unknown rather than inferred from suppliers. The number of replies is
derived from the separator blocks: five, six, or more use the same workflow. There
is no fixed supplier-count cap. The input limit remains 100,000 UTF-8 bytes, and
each model request is bounded by its context/output capacity. Output budgets grow
with the number of replies up to 16,000 tokens; oversized responses fail clearly
rather than producing an incomplete comparison.

### Report

The saved Markdown remains the source artifact; `review` creates its reviewer PDF
automatically. To retry PDF export or export an existing report without re-running
the model:

```bash
.venv/bin/python main.py pdf report.md -o report.pdf
# Add --force to replace an existing PDF after a successful export.
```

PDF export requires Pandoc and XeLaTeX. On macOS install Pandoc with
`brew install pandoc` and a TeX distribution such as MacTeX. On Debian/Ubuntu use
`sudo apt-get install pandoc texlive-xetex texlive-latex-extra`.
The exporter typesets the existing Markdown locally; it
makes no model calls and does not change `report.md`. Landscape tables have
repeated headers, and numbered source excerpts appear at the end. All four
sections, qualifications, questions, and evidence are retained.

1. **Normalized supplier comparison** — buyer requirements, quote terms, price
   normalization, conditional quantity extensions, and exact source excerpts.
2. **Risks / unknowns** — warnings, model assessment, and supplier issues with
   category, severity, reason, and source evidence.
3. **Shortlist / recommendation** — explicit advance, hold, or do-not-advance action
   per supplier. Advance with clarification means pursue a conditional shortlist;
   hold means a material supplier clarification is needed; do not advance means a
   concrete supplier-specific blocker must be resolved. None approves an award.
4. **Follow-up questions** — model-drafted questions grounded in this case's gaps
   and risks, grouped by owner and ordered BLOCKER, HIGH, MEDIUM, LOW. At most
   three questions per supplier; fewer when fewer useful clarifications exist.

There are no application-level question templates or supplier-specific question
lists. The harness sends an issue inventory (missing/uncertain fields, validation
warnings, detected risks, and comparability gaps) alongside the validated facts.
The model authors each question, including questions about novel commercial terms.
The renderer displays those questions, removes exact duplicates, and groups them
by priority. Owners without useful questions need not receive generic busywork.
Buyer questions establish shared requirements; supplier questions resolve that
offer's own terms. Validation requires actionable supplier questions for hold/stop
decisions. Incomplete question coverage for uncertain terms on conditionally
advanced offers produces data-quality notes, rather than stopping the report or
spending a correction call. The terms remain unresolved; questions are not invented
by the application. A stop decision needs a blocking question referencing that supplier's quote.
Supplier IDs and schemas come from the input blocks; adding suppliers requires no
code changes. Detailed terms are displayed in groups of at most four columns for
readability; the shortlist still includes every supplier in one comparison.

The issue layer runs within the same two-call workflow. Deterministic candidates
cover confirmed revision/MOQ conflicts, validation exclusions, provisional prices
or tooling, quoted logistics gaps and uncertain currency. Missing optional fields
alone do not produce candidates. The model assesses additional ambiguities such
as amortization, index clauses or first-article approval using the actual facts.
Each issue records its owner, category, severity, basis (missing, unverified,
ambiguous or conflicting), reason and supporting extracted-field references. The
harness resolves references to validated evidence and labels unknown/unverified
facts. Known terms cannot be represented as missing; included tooling does not
justify asking whether tooling is included. The model may mark a heuristic
ambiguity `answered` with cited retained evidence when other quoted terms already
resolve it. Confirmed blockers and validation gaps cannot be dismissed this way.
Severity floors for remaining candidates survive model omission or downgrade.

Questions reference issue IDs, are deduplicated, sorted by severity and capped at
three per supplier. Within a severity, questions covering recommendation conditions
are selected first. All BLOCKER issues need coverage; lower-priority questions
cannot replace a higher-priority unresolved issue. Related issues can share a
question. Shared buyer requirements stay in the Buyer section. The model records
each recommendation condition in `clarification_issue_ids`; validation requires
that every condition has a question after selection, with the correct owner.
Missing blocker questions, skipped priorities or unmatched declared conditions use
the analysis stage's correction attempt. If coverage remains incomplete after that
attempt, a structurally valid analysis becomes an explicitly **Follow-up draft
incomplete** report. Uncovered issues remain in the report, are listed under the
correct buyer/supplier owner, and affected recommendations are flagged. The
application does not fabricate questions, remove conditions, clear blockers or
add more calls. Unknown references, unsupported issue evidence and malformed
responses still fail. General non-blocking coverage gaps remain advisory notes.
Interpreting prose, identifying all conditions
in the summary and assessing qualitative ambiguity still require model judgment;
ID checks do not prove semantic correctness of every sentence.

Unit-price extensions are not landed costs or confirmed ordering plans. Currencies
remain separate. Bare `$` is retained as quoted. When this RFQ also contains an
explicit USD quote and no conflicting dollar currency, the comparison provisionally
uses USD labelled **inferred**, with the context and supplier confirmation required.
Explicit codes remain labelled **explicit**. Without that context, the dollar code
remains unresolved; a missing currency does not erase a grounded nominal price.
Unknown charges remain unknown.
Refundable container deposits are shown separately from permanent cost. Payment
discounts, index changes, and amortization savings are not automatically applied.
The tooling scenario adds one separately quoted charge, explicitly as an assumption;
no tooling total is calculated when amount/currency is unresolved or differs from
the price currency. Decimal arithmetic avoids intermediate money rounding.
FOB/EXW prices are nominal; explicit freight/duty exclusions are highlighted rather
than treated as landed-cost advantages. A mismatch with the buyer-stated drawing
revision prevents advancement until compliance is confirmed or the supplier re-quotes.
When the buyer's requirement is unknown, different supplier revisions are unresolved
comparison gaps for both offers; neither a later-looking revision nor a supplier's
reference establishes the requirement. Missing buyer revision, destination or release
schedule generates a blocking buyer issue when needed to assess the quoted terms.
These issues block final comparison, not conditional shortlisting. Routine supplier
uncertainties can be clarified in parallel. Differing quoted revisions remain a
strong technical risk; the model may stop an offer with an explained reason and
supplier follow-up without declaring another supplier's revision buyer-required.
Only a confirmed buyer-revision mismatch automatically overrides the shortlist;
unresolved revision differences preserve the model's action and supplier-specific
reason alongside the warning.
The model drafts the buyer questions; validation checks that they cover those issues
as blocking, buyer-owned questions. Detailed validation reasons stay in run state;
the buyer report groups them into concise data-quality notes and preserves evidence.

### Architecture and boundaries

```text
cli.py -> agent.py -> harness.py
                       read/split -> LLM extraction -> validate
                       -> calculate / derive issues -> LLM analysis -> validate -> render/save
```

- `agent.py`: public review interface.
- `harness.py`: per-run state, workflow, call budget, and validation policy.
- `prompts.py`: extraction and analysis instructions.
- `schema.py`: field contracts, response shape checks, numeric evidence checks,
  source-line citation resolution, excerpt matching, and source validation.
- `tools/issues.py`: generic issue candidates, severity floors and question ordering.
  A malformed part-number excerpt is replaced with the exact identifier only when
  that identifier occurs as a whole identifier in the same source. Otherwise it
  is rejected. Correction feedback includes the rejected response and up to twelve
  validation errors so the model can repair multiple fields in one attempt.
- `tools/packet.py`, `tools/calculations.py`, `tools/report.py`: application tools
  invoked by application code. **No tools are exposed to the model.**
- `openrouter.py`: HTTPS transport and safe provider errors.

Model responses use JSON contracts. The harness numbers the original source lines;
each extracted field is `{"value": "...", "evidence": "L3"}` or cites a contiguous
range such as `L3-L5`. Unknown facts use `{"value": null, "evidence": null}`. The
harness resolves line references within that record's own source and retains the
exact original excerpt in the report. Users do not need to number input lines.
Supplier records are keyed by their source IDs, with every key required by the
schema, rather than an array that could omit or duplicate a supplier.
Prices retain their original denominator until the harness calculates per-piece
amounts. Numeric fields use decimal strings with schema-enforced numeric formats.
The response schema pairs a known value with a source citation, or an unknown
value with a null citation; it does not allow a null value with a citation.
Both review calls send `response_format: json_schema` with `strict: true` and
`provider.require_parameters: true`, using schemas built from the same field
definitions as local validation. Every fact must be an object, even when unknown;
bare strings or nulls in place of fact objects are invalid. Local validation still
checks evidence, numeric support, and conditions after structured generation.

After extraction's one allowed correction, remaining invalid facts are excluded and shown
as **Unverified / excluded**, distinct from terms that were not stated. The report
has a concise data-quality notice and groups affected terms by supplier. Detailed
validation reasons remain internal. The
analysis receives only retained facts and warnings, never the discarded claims.
Invalid price inputs prevent price calculations; unverified price/quantity
conditions prevent extensions; unverified tooling prevents the tooling scenario.
Structural errors such as a missing supplier, malformed root response, provider
failure, or invalid analysis references/evidence still stop the run. Evidence checks are not
weakened to accept unsupported facts. Analysis has its own correction attempt even
when extraction needed repair or excluded an unverified field.

Review requires a model/provider endpoint supporting JSON Schema structured outputs.
The recommended configuration is `openai/gpt-4.1`, which passed the six live
semantic evals and costs more than `gpt-4o-mini`. Requests use `temperature=0`;
the endpoint must support both this parameter and JSON Schema. If you already
have a `.env`, update its `OPENROUTER_MODEL` value explicitly. Unsupported endpoint/schema
errors stop the run with an actionable message; there is no silent plain-text
fallback. Chat and the connection check remain plain-text requests and do not
establish structured-output readiness. See OpenRouter's
[structured-output documentation](https://openrouter.ai/docs/guides/features/structured-outputs).

An exported model setting takes precedence over `.env`. To select the recommended
model in an existing shell, run `export OPENROUTER_MODEL=openai/gpt-4.1`.

Normally there are two model calls: extraction, then analysis of validated facts
and calculations. Each stage has at most one additional correction call (four
calls maximum). Extraction cannot consume analysis's correction budget.
Provider/transport failures are not retried. Each
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

Six opt-in live semantic evaluations and their rubric are documented in
[`evals/README.md`](evals/README.md). They use synthetic packets and structured
behavior checks, with no exact-prose comparisons. They are separate from these
offline tests and make paid model calls only when explicitly enabled.

Tests cover the reference packet's calculations, parsing, evidence validation,
missing fields, call limits, report sections, output preservation, and a CLI run
through the OpenRouter adapter with mocked HTTP. They do not establish live model
quality. For live acceptance, run the example and review the generated facts,
evidence, revision discrepancies, cost exclusions, shortlist, and questions against
the original packet.
