"""Public interface; execution policy lives in the harness."""

from .harness import ReviewHarness
from .openrouter import OpenRouterClient


class ProcurementAgent:
    def __init__(self, client: OpenRouterClient, on_progress=None):
        self.harness = ReviewHarness(client, on_progress=on_progress)

    def review(self, packet: str) -> str:
        return self.harness.review(packet)
