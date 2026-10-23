# Decisions

## What I built

I built a lightweight procurement decision-support workflow that turns inconsistent supplier RFQ responses into a structured buyer report.

The workflow:

1. reads the RFQ packet
2. uses an LLM to extract structured commercial and technical facts
3. validates and normalizes the extracted data in code
4. performs deterministic calculations where the source evidence supports them
5. uses an LLM to identify risks, recommend which suppliers to advance, and draft follow-up questions
6. renders a buyer-facing report with source evidence

The output focuses on helping a buyer move from messy supplier responses to a clearer next action, rather than simply summarizing the quotes.

## What I intentionally cut

I intentionally did not build:

- a model-directed ReAct / tool-calling loop
- multi-agent orchestration
- vector search or embeddings
- live FX conversion
- ERP or procurement-system integrations
- automatic supplier outreach
- browser automation
- a full landed-cost engine

The input is a small, bounded RFQ packet and the processing sequence is known in advance. Adding autonomous tool selection or retrieval infrastructure would increase implementation and failure complexity without materially improving the core workflow in the time box.

## Key design choices

### Fixed workflow instead of an open-ended agent loop

The core sequence is predictable:

`extract → validate / normalize → analyze → render`

Intermediate observations do not materially change which operation should happen next, so the application owns orchestration rather than asking the model to dynamically select tools.

I still use the LLM where semantic reasoning is valuable, but keep execution bounded and predictable.

### LLM for semantics, deterministic code for guarantees

The LLM handles tasks such as:

- extracting facts from inconsistent free text
- interpreting ambiguous supplier language
- identifying and prioritizing commercial or technical risks
- generating recommendations
- drafting follow-up questions

Deterministic code handles:

- schema validation
- arithmetic
- unit-price normalization
- annual price extensions
- evidence checks
- handling unknown values
- bounded retries
- report rendering

This keeps flexible language understanding separate from calculations and invariants that should be reproducible.

### Preserve uncertainty instead of inventing comparability

Supplier quotes do not always provide enough information for a complete comparison.

For example, missing destination, drawing revision, freight, duty, tooling, or currency information is kept as unresolved rather than silently assuming a value.

The report therefore distinguishes nominal pricing from landed cost and avoids ranking cross-currency offers without a valid FX basis.

### Evidence-backed output

Important extracted facts and recommendations retain references to the original supplier text.

This makes it easier for the buyer to understand why the system reached a conclusion and to verify questionable fields before taking action.

## Where it falls over

The current implementation has several limitations:

- ambiguous or contradictory supplier language can still lead to incorrect extraction or interpretation
- inferred values, such as currency from a bare `$` symbol, still require confirmation
- there is no live FX or logistics data, so the system cannot produce a true landed-cost ranking
- buyer requirements may themselves be incomplete, which limits technical and commercial comparison
- the quality of the recommendation depends on the quality of extracted facts
- the system only drafts follow-up questions; it does not send messages or manage the resulting conversation
- PDF export depends on local Pandoc / XeLaTeX availability

The workflow is designed to surface these uncertainties rather than hide them.

## What I would do with another day

With another day, I would prioritize:

1. Add a small semantic evaluation suite using synthetic supplier quotes to measure extraction, risk identification, and recommendation quality.
2. Add stronger field-level confidence and provenance checks.
3. Support additional input formats such as PDFs, spreadsheets, and email attachments.
4. Add live FX and logistics inputs for a more realistic landed-cost comparison.
5. Add an interactive clarification loop so the buyer can provide missing requirements and rerun the comparison.
6. Add optional supplier outreach behind explicit user confirmation and idempotent action safeguards.