"""Bounded workflow. State exists only for the current review; no callable tools."""

import json
from dataclasses import dataclass

from .prompts import ANALYSIS_PROMPT, EXTRACTION_PROMPT
from .schema import MAX_RESPONSE_CHARS, ValidationError, load_response, validate_analysis, validate_extraction
from .tools.calculations import calculate_amounts
from .tools.packet import Packet, parse_packet
from .tools.report import render_report


@dataclass
class RunState:
    packet: Packet
    extraction: dict | None = None
    calculations: list[dict] | None = None
    analysis: dict | None = None
    correction_remaining: int = 1
    model_calls: int = 0


class ReviewHarness:
    def __init__(self, client, on_progress=None):
        self.client = client
        self.on_progress = on_progress

    def _progress(self, message):
        if self.on_progress is not None:
            self.on_progress(message)

    def _request(self, state, prompt, payload, validator, max_tokens, stage):
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        while True:
            state.model_calls += 1
            self._progress(f"{stage}: waiting for model response (request {state.model_calls}/3)...")
            # Transport/provider errors propagate. They are never retried automatically.
            response = self.client.complete(messages, max_tokens=max_tokens)
            self._progress(f"{stage}: validating response...")
            try:
                return validator(load_response(response), state.packet.sources)
            except ValidationError as error:
                if state.correction_remaining == 0:
                    raise ValidationError(f"Review stopped after invalid model output: {error}") from None
                state.correction_remaining -= 1
                self._progress(f"{stage}: requesting the one allowed correction ({error})")
                # Keep the rejected response so the model can repair specific
                # fields. Oversized output is excluded, and remains untrusted.
                if isinstance(response, str) and len(response) <= MAX_RESPONSE_CHARS:
                    messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": (
                    f"The response failed validation: {error} "
                    "Fix all listed fields. Evidence must be copied verbatim from the field's own source, "
                    "without paraphrases, inferred labels, or another source's text. "
                    "Return a complete corrected JSON object using the original sources and contract."
                )})

    def review(self, text: str) -> str:
        state = RunState(parse_packet(text))
        self._progress(f"Parsed buyer requirements and {len(state.packet.suppliers)} supplier replies.")
        state.extraction = self._request(
            state, EXTRACTION_PROMPT, {"sources": state.packet.sources},
            validate_extraction, max_tokens=14000, stage="Extraction",
        )
        self._progress("Calculating normalized prices and conditional amounts...")
        state.calculations = calculate_amounts(state.extraction)
        state.analysis = self._request(
            state, ANALYSIS_PROMPT,
            {"extraction": state.extraction, "calculations": state.calculations},
            validate_analysis, max_tokens=6000, stage="Analysis",
        )
        self._progress("Rendering the report...")
        return render_report(state.extraction, state.calculations, state.analysis)
