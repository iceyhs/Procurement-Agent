"""Bounded workflow. State exists only for the current review; no callable tools."""

import json
from dataclasses import dataclass

from .prompts import ANALYSIS_PROMPT, EXTRACTION_PROMPT
from .schema import ValidationError, load_response, validate_analysis, validate_extraction
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


class ReviewHarness:
    def __init__(self, client):
        self.client = client

    def _request(self, state, prompt, payload, validator, max_tokens):
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        while True:
            # Transport/provider errors propagate. They are never retried automatically.
            response = self.client.complete(messages, max_tokens=max_tokens)
            try:
                return validator(load_response(response), state.packet.sources)
            except ValidationError as error:
                if state.correction_remaining == 0:
                    raise ValidationError(f"Review stopped after invalid model output: {error}") from None
                state.correction_remaining -= 1
                # Do not reflect arbitrarily large or invalid response data into another request.
                messages.append({"role": "user", "content": (
                    f"The response failed validation: {error} "
                    "Return a complete corrected JSON object using the original sources and contract."
                )})

    def review(self, text: str) -> str:
        state = RunState(parse_packet(text))
        state.extraction = self._request(
            state, EXTRACTION_PROMPT, {"sources": state.packet.sources},
            validate_extraction, max_tokens=14000,
        )
        state.calculations = calculate_amounts(state.extraction)
        state.analysis = self._request(
            state, ANALYSIS_PROMPT,
            {"extraction": state.extraction, "calculations": state.calculations},
            validate_analysis, max_tokens=6000,
        )
        return render_report(state.extraction, state.calculations, state.analysis)
