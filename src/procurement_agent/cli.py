import argparse
import sys
from pathlib import Path

from .agent import ProcurementAgent
from .openrouter import OpenRouterClient, OpenRouterError
from .tools.packet import read_packet
from .tools.report import check_output, write_report


def _progress(message: str):
    print(f"[review] {message}", file=sys.stderr, flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evidence-backed procurement quote review")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Make a small, billable OpenRouter connection check")
    review = commands.add_parser("review", help="Review a quote packet and save a Markdown report")
    review.add_argument("packet", type=Path)
    review.add_argument("-o", "--output", type=Path, default=Path("report.md"))
    review.add_argument("--force", action="store_true", help="Replace an existing report after a successful review")
    args = parser.parse_args(argv)
    try:
        packet = None
        if args.command == "review":
            _progress(f"Reading {args.packet}...")
            packet = read_packet(args.packet)
            check_output(args.output, args.packet, args.force)
        client = OpenRouterClient.from_env()
        if args.command == "check":
            result = client.complete([
                {"role": "user", "content": "Reply with exactly: CONNECTION_OK"},
            ], max_tokens=128)
            if result != "CONNECTION_OK":
                raise OpenRouterError("Received a completion, but the connection check response was unexpected.")
            print(f"OpenRouter connection verified ({client.model}).")
        else:
            _progress(f"Using model {client.model} (network timeout: {client.timeout:g}s).")
            report = ProcurementAgent(client, on_progress=_progress).review(packet)
            _progress(f"Saving {args.output}...")
            write_report(args.output, report, args.force)
            print(f"Report saved to {args.output}")
        return 0
    except (OpenRouterError, OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
