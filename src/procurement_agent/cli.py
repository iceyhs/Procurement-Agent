import argparse
import sys
from pathlib import Path

from .agent import ProcurementAgent
from .openrouter import OpenRouterClient, OpenRouterError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Procurement Agent (initial skeleton)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Make a small, billable OpenRouter connection check")
    review = commands.add_parser("review", help="Send a UTF-8 quote packet for preliminary review")
    review.add_argument("packet", type=Path)
    args = parser.parse_args(argv)
    try:
        packet = args.packet.read_text(encoding="utf-8") if args.command == "review" else None
        if packet is not None and not packet.strip():
            raise ValueError("Quote packet is empty.")
        client = OpenRouterClient.from_env()
        if args.command == "check":
            result = client.complete([
                {"role": "user", "content": "Reply with exactly: CONNECTION_OK"},
            ], max_tokens=128)
            if result != "CONNECTION_OK":
                raise OpenRouterError("Received a completion, but the connection check response was unexpected.")
            print(f"OpenRouter connection verified ({client.model}).")
        else:
            print(ProcurementAgent(client).review(packet))
        return 0
    except (OpenRouterError, OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
