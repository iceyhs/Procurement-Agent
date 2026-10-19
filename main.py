"""Run an interactive procurement chat: python main.py."""

from pathlib import Path

from dotenv import load_dotenv

from procurement_agent.agent import SYSTEM_PROMPT
from procurement_agent.openrouter import OpenRouterClient, OpenRouterError


def main() -> int:
    # Existing process configuration takes precedence over the local file.
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    try:
        client = OpenRouterClient.from_env()
    except OpenRouterError as exc:
        print(f"Error: {exc}")
        return 1

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"Procurement Agent ({client.model})")
    print("Ask a question. Type exit or quit to leave. Each turn sends an API request.")
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0
        if question.lower() in {"exit", "quit"}:
            return 0
        if not question:
            continue
        pending = messages + [{"role": "user", "content": question}]
        try:
            answer = client.complete(pending)
        except OpenRouterError as exc:
            print(f"Error: {exc}")
            continue
        except KeyboardInterrupt:
            print("\nGoodbye.")
            return 0
        messages = pending + [{"role": "assistant", "content": answer}]
        print(f"\nAgent: {answer}")


if __name__ == "__main__":
    raise SystemExit(main())
