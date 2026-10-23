# Semantic evals

Six synthetic packets exercise clear comparable offers, missing unit price,
conflicting revisions with an unknown buyer requirement, excluded freight/duty,
provisional price/tooling, and a fifth supplier with a novel energy-supplement
clause. Names and wording are independent of the example quote packet.

These are **live, paid model evaluations**, separate from the offline unit tests.
They use the configured OpenRouter model and the unchanged review harness. Each
case has the normal two-call workflow with at most four calls including repairs;
there are no additional eval retries. The repository `.env` is loaded without
overriding process configuration. The recommended model is `openai/gpt-4.1`;
structured review requests use `temperature=0`. No PDF generation is needed.

```bash
RUN_SEMANTIC_EVALS=1 .venv/bin/python -m unittest discover -s evals -v
```

The rubric checks structured facts, nulls, evidence, issue topics/severity,
recommendation actions/conditions, and priority/ownership/coverage of questions.
It does not compare exact prose or use another model as a judge. A stopped review
or an incomplete result fails its case; the evaluator does not manufacture missing
results. Issue IDs may differ as long as their meaning and links satisfy the rubric.

This is a small regression signal, not proof that every narrative claim is true.
In particular, question intent is assessed through its declared fields and issue
links, not a separate semantic reading of the prose. Passing these cases does not
guarantee unseen-case quality. Model changes can change results, so retain failing
case names and diagnostics when reviewing a run.

Where a material clarification allows either hold or conditional advancement,
both are accepted. Advancement must explicitly link the unresolved issue to a
follow-up; it cannot silently treat provisional terms as firm.

The before/after validation snapshot for the unchanged rubric is in
[`RESULTS.md`](RESULTS.md).
