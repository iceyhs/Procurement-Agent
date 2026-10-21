"""Public interface; execution policy lives in the harness."""

from .harness import ReviewHarness
from .openrouter import OpenRouterClient


class ProcurementAgent:
    def __init__(self, client: OpenRouterClient):
        self.harness = ReviewHarness(client)

    def review(self, packet: str) -> str:
        return self.harness.review(packet)
