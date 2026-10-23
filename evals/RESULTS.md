# Validation snapshot

The fixed workflow with `openai/gpt-4.1` passed **6/6 live semantic evals**.
This run used 12 provider calls total: extraction and analysis for each case,
with no correction calls. The separate offline suite passed **123 tests**.

| Synthetic case | GPT-4.1 after fixes |
| --- | --- |
| Clear comparable quotes | Passed |
| Missing required unit price | Passed |
| Conflicting revisions / unknown buyer revision | Passed |
| Low nominal price excluding freight/duty | Passed |
| Provisional price and tooling | Passed |
| New fifth supplier / unfamiliar energy-supplement clause | Passed |

Before the fixes, `openai/gpt-4o-mini` passed 2/6 cases; four stopped on contract
or issue-reference validation. After the fixes, a comparison run with that model
passed 4/6: it still held fully comparable offers and left follow-up coverage
incomplete in the freight/duty case. The user selected GPT-4.1 for reliability,
accepting its higher API cost. Both final runs used `temperature=0`.

The fixes align structured-output schemas with local validation, make repair
diagnostics actionable, distinguish actual commercial gaps from optional null
fields, and clarify issue ownership and question links. Unknown values still
require null citations; missing prices cannot support advancement; unsupported
facts remain rejected. The semantic eval cases and assertions were not relaxed.
No fallback business results were fabricated.

The separate example-packet CLI run also generated `report.md` and `report.pdf`
using GPT-4.1. It required one analysis correction and retained one internal
supplier follow-up coverage warning. That smoke run demonstrates artifact
generation, not a fully clean analysis. Both artifacts contain the four report
sections; checked annual amounts and source evidence agree, and internal debug
labels do not appear in the buyer-facing output.

This records individual runs, not a guarantee of unseen-case quality. Outputs
may vary even with temperature zero. The suite remains opt-in and separate from
the offline unit-test pass/fail signal; its limits are in [`README.md`](README.md).
