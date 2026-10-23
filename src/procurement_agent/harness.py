"""Bounded workflow. State exists only for the current review; no callable tools."""

import json
from dataclasses import dataclass

from .prompts import ANALYSIS_PROMPT, EXTRACTION_PROMPT
from .schema import (
    MAX_RESPONSE_CHARS, ValidationError, analysis_format, extraction_format,
    load_response, validate_analysis, validate_extraction,
)
from .tools.calculations import calculate_amounts, follow_up_context
from .tools.packet import Packet, parse_packet
from .tools.report import render_report


@dataclass
class RunState:
    packet: Packet
    extraction: dict | None = None
    calculations: list[dict] | None = None
    analysis: dict | None = None
    model_calls: int = 0


class ReviewHarness:
    def __init__(self, client, on_progress=None):
        self.client = client
        self.on_progress = on_progress

    def _progress(self, message):
        if self.on_progress is not None:
            self.on_progress(message)

    def _request(self, state, prompt, payload, validator, max_tokens, stage, response_format, allow_partial=False, partial_validator=None):
        # Extraction repair must not consume analysis's chance to repair its own output.
        correction_remaining = 1
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        while True:
            state.model_calls += 1
            self._progress(f"{stage}: waiting for model response (request {state.model_calls}/4)...")
            # Transport/provider errors propagate. They are never retried automatically.
            response = self.client.complete(
                messages, max_tokens=max_tokens, response_format=response_format,
            )
            self._progress(f"{stage}: validating response...")
            try:
                return validator(load_response(response), state.packet.sources)
            except ValidationError as error:
                if correction_remaining == 0:
                    if allow_partial:
                        try:
                            result = validate_extraction(load_response(response), state.packet.sources, allow_partial=True)
                        except ValidationError:
                            raise ValidationError(f"Review stopped after invalid model output: {error}") from None
                        count = len(result.get("validation_warnings", []))
                        self._progress(f"Extraction incomplete: excluded {count} unverified fields; see report warnings.")
                        return result
                    if partial_validator is not None:
                        try:
                            result = partial_validator(load_response(response), state.packet.sources)
                        except ValidationError:
                            raise ValidationError(f"Review stopped after invalid model output: {error}") from None
                        self._progress("Analysis incomplete: follow-up coverage gaps remain; report marked incomplete.")
                        return result
                    raise ValidationError(f"Review stopped after invalid model output: {error}") from None
                correction_remaining -= 1
                self._progress(f"{stage}: requesting this stage's one allowed correction ({error})")
                # Keep the rejected response so the model can repair specific
                # fields. Oversized output is excluded, and remains untrusted.
                if isinstance(response, str) and len(response) <= MAX_RESPONSE_CHARS:
                    messages.append({"role": "assistant", "content": response})
                if stage == "Extraction":
                    repair = (
                        "Fix all listed fields. Extraction evidence must cite the field's own source lines "
                        "using L3 or L3-L5, not copied or paraphrased excerpts. "
                        "When unsupported, use {\"value\": null, \"evidence\": null}. "
                    )
                else:
                    repair = (
                        "Fix the issue/question links and clarification conditions. Address BLOCKER before HIGH, "
                        "MEDIUM and LOW; keep at most three questions per supplier. Use candidate IDs or "
                        "declare grounded new issues, and include a question for every recommendation condition. "
                        "Within each severity, prioritize the listed uncovered conditions. Combine closely related "
                        "issues if needed to fit three questions; keep unresolved conditions visible. "
                    )
                messages.append({"role": "user", "content": (
                    f"The response failed validation: {error} " + repair +
                    "Return a complete corrected JSON object using the original sources and contract."
                )})

    def review(self, text: str) -> str:
        state = RunState(parse_packet(text))
        self._progress(f"Parsed buyer requirements and {len(state.packet.suppliers)} supplier replies.")
        state.extraction = self._request(
            state, EXTRACTION_PROMPT, {"sources": state.packet.numbered_sources},
            validate_extraction, max_tokens=min(16000, max(14000, 1000 * len(state.packet.suppliers))), stage="Extraction",
            response_format=extraction_format(list(state.packet.sources)[1:]),
            allow_partial=True,
        )
        self._progress("Calculating normalized prices and conditional amounts...")
        state.calculations = calculate_amounts(state.extraction)
        analysis_extraction = dict(state.extraction)
        if "validation_warnings" in analysis_extraction:
            analysis_extraction["validation_warnings"] = [
                {"source_id": warning["source_id"], "field": warning["field"]}
                for warning in state.extraction["validation_warnings"]
            ]
        questions_context = follow_up_context(state.extraction, state.calculations)
        state.analysis = self._request(
            state, ANALYSIS_PROMPT,
            {"extraction": analysis_extraction, "calculations": state.calculations,
             "follow_up_context": questions_context},
            lambda data, sources: validate_analysis(data, sources, follow_up_context=questions_context, extraction=state.extraction),
            max_tokens=min(16000, max(8000, 1200 * len(state.packet.suppliers))), stage="Analysis",
            response_format=analysis_format(list(state.packet.sources)),
            partial_validator=lambda data, sources: validate_analysis(
                data, sources, follow_up_context=questions_context, extraction=state.extraction, allow_incomplete=True,
            ),
        )
        if state.analysis.get("follow_up_warnings"):
            count = len(state.analysis["follow_up_warnings"])
            self._progress(f"Analysis: {count} supplier follow-up coverage notes; see data-quality notes.")
        self._progress("Rendering the report...")
        return render_report(state.extraction, state.calculations, state.analysis)
