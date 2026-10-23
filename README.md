# Procurement Agent

Procurement Review CLI for the Aron procurement exercise. It reconciles free-text
supplier quotes against a buyer's requirements and produces evidence-backed
Markdown and PDF reports. It uses OpenRouter, Python's standard library, and
`python-dotenv` to load local configuration through `main.py`.

The bracket exercise is an example, not a runtime preset. Each run takes the item,
quantity and its basis, currency, relevant specifications, and supplier set from
the input. Optional manufacturing fields do not automatically create requirements
or follow-up questions for unrelated purchases. The MVP compares unit-priced goods
for one RFQ per run; mixed measurement units or service pricing need explicit
normalization support rather than being silently treated as per-piece prices.

## Quick Start

**Procurement Review is the primary functionality.** It reads buyer requirements
and supplier quotes, uses LLM-based structured extraction, validates extracted
facts and source evidence, performs deterministic calculations and risk checks,
and uses LLM analysis to produce recommendations and follow-up questions. It
saves `report.md` and renders `report.pdf` from the same Markdown artifact.

You need **Python 3.12+**, an OpenRouter account with API credits, and **Pandoc and
XeLaTeX** for PDF generation. Python dependency installation does not install the
PDF tools.

1. **Install the project.** From your local checkout (replace the path below):

   ```bash
   cd /path/to/Procurement-Agent
   python3.12 -m venv .venv
   .venv/bin/python -m pip install -e .
   test -e .env || cp .env.example .env
   ```

   `pip install -e .` installs the project and dependencies declared in
   `pyproject.toml`.

2. **Configure the API key.** Get a key from
   [OpenRouter](https://openrouter.ai/settings/keys), then edit `.env` in the
   repository root, next to `main.py`:

   ```dotenv
   OPENROUTER_API_KEY=your-openrouter-api-key
   OPENROUTER_MODEL=openai/gpt-4.1
   ```

   Replace the placeholder with your key. `openai/gpt-4.1` is the recommended
   model. `.env` is ignored by Git. `main.py` loads it automatically; exported
   environment variables take precedence. Reviews send the packet to OpenRouter
   and its model provider and incur API charges.

3. **Install the PDF tools** for your platform:

   - macOS with [Homebrew](https://brew.sh/): run `brew install pandoc`, then
     `brew install --cask mactex-no-gui`. Reopen your terminal or run
     `export PATH="/Library/TeX/texbin:$PATH"`.
   - Debian/Ubuntu: run `sudo apt-get update`, then
     `sudo apt-get install pandoc texlive-xetex texlive-latex-extra`.

   Check that `pandoc --version` and `xelatex --version` both work in the terminal
   where you run the agent.

4. **Optionally check the connection** (also a paid model call):

   ```bash
   .venv/bin/python main.py check
   ```

5. **Run Procurement Review:**

   ```bash
   .venv/bin/python main.py review examples/quote_packet.txt -o report.md
   ```

   Find `report.md` and `report.pdf` in the current directory (the project root
   when following these steps). This repository includes example reports, so add
   `--force` to the command when intentionally replacing those existing files.
   A successful run prints `Report saved to report.md` and `PDF saved to report.pdf`.
   If PDF export fails, the successful Markdown result is kept; see
   [PDF setup and export recovery](#install-pdf-dependencies).

Running `.venv/bin/python main.py` without a subcommand starts **optional
Interactive Chat** for free-text conversations. Chat does **not** execute the full
procurement review workflow or generate formal reports. See
[Interactive Chat](#optional-interactive-chat) for details.

## Procurement Review (primary workflow)

Use the Quick Start command for the bundled example. For your own input, put buyer
requirements and supplier replies into one UTF-8 text file using the
[input format below](#input-format), then run:

```bash
.venv/bin/python main.py review examples/quote_packet.txt -o report.md
```

Add `--force` only when you want to replace existing Markdown and PDF outputs.
`main.py --help` shows all commands and options.

Alternatively, use the installed command after exporting the configuration:

```bash
set -a
. ./.env
set +a
.venv/bin/procurement-agent review examples/quote_packet.txt --force
# Or use your own input and output paths:
.venv/bin/procurement-agent review quote_packet.txt --output report.md
```

Unlike `main.py`, the installed `procurement-agent` command does not load `.env`
automatically; the export commands above load your trusted local configuration.

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

### Install PDF dependencies

Automatic PDF export also requires **Pandoc and XeLaTeX**. Installing the Python
package does not install these tools.

The [Quick Start](#quick-start) includes macOS and Debian/Ubuntu installation
commands. Verify that both tools are available in the terminal where you run the agent:

```bash
pandoc --version
xelatex --version
```

If `xelatex` is still not found on macOS, reopen your terminal after installing
MacTeX, or add `export PATH="/Library/TeX/texbin:$PATH"` to your shell configuration.

### Report

The saved Markdown remains the source artifact; `review` creates its reviewer PDF
automatically. To retry PDF export or export an existing report without re-running
the model:

```bash
.venv/bin/python main.py pdf report.md -o report.pdf --force
```

If a run reports `Markdown saved ... but PDF export failed`, the Markdown is
already usable. Install or fix the [PDF dependencies](#install-pdf-dependencies),
then run the export command above. It requires no API key and makes no model
calls, so there is no need to repeat the paid review.
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

## Optional interactive chat

After installing the project and filling in `.env`, run from the repository root:

```bash
.venv/bin/python main.py
```

Enter a question at `You:`; type `exit` or `quit` to leave. Conversation history
is kept in memory for this session and sent with each question; it is not saved
between runs. Each turn may incur API charges. Quotes must be provided in the
conversation; chat does not automatically read repository files or generate the
validated reports. Use `main.py review` for the quote comparison workflow.

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
