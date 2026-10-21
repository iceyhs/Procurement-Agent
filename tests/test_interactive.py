"""Keep the interactive entry point working alongside structured reviews."""

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main as chat

from procurement_agent.prompts import CHAT_PROMPT


class InteractiveTests(unittest.TestCase):
    @patch("main.load_dotenv")
    @patch("main.OpenRouterClient.from_env")
    @patch("builtins.input", side_effect=["Review this quote", "quit"])
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_chat_uses_its_own_prompt(self, stdout, user_input, from_env, load_dotenv):
        client = Mock(model="test/model")
        client.complete.return_value = "Please provide the quote."
        from_env.return_value = client
        self.assertEqual(chat.main([]), 0)
        self.assertEqual(client.complete.call_count, 1)
        self.assertEqual(client.complete.call_args.args[0][0], {"role": "system", "content": CHAT_PROMPT})
        self.assertIn("Please provide the quote.", stdout.getvalue())
        self.assertFalse(load_dotenv.call_args.kwargs["override"])

    @patch("main.load_dotenv")
    @patch("main.cli_main", return_value=1)
    @patch("main.OpenRouterClient.from_env")
    @patch("sys.argv", ["main.py", "check"])
    def test_script_arguments_and_exit_status_are_forwarded(self, from_env, cli_main, load_dotenv):
        self.assertEqual(chat.main(), 1)
        cli_main.assert_called_once_with(["check"])
        from_env.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    @patch("procurement_agent.cli.ProcurementAgent")
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_review_loads_local_dotenv_and_writes_cli_report(self, stdout, agent):
        agent.return_value.review.return_value = "# Procurement report\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "OPENROUTER_API_KEY=test-key\nOPENROUTER_MODEL=test/model\n", encoding="utf-8",
            )
            packet = root / "quote_packet.txt"
            packet.write_text("BRK-4471-A\n60,000 units\n===PACKET===\nSupplier reply", encoding="utf-8")
            output = root / "report.md"
            with patch("main.__file__", str(root / "main.py")):
                self.assertEqual(chat.main(["review", str(packet), "-o", str(output)]), 0)
            self.assertEqual(output.read_text(), "# Procurement report\n")
            self.assertEqual(agent.call_args.args[0].model, "test/model")
            agent.return_value.review.assert_called_once_with(packet.read_text())

    @patch.dict("os.environ", {"OPENROUTER_MODEL": "process/model"}, clear=True)
    @patch("main.cli_main", return_value=0)
    def test_process_configuration_takes_precedence(self, cli_main):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("OPENROUTER_MODEL=file/model\n", encoding="utf-8")
            with patch("main.__file__", str(root / "main.py")):
                self.assertEqual(chat.main(["check"]), 0)
            self.assertEqual(os.environ["OPENROUTER_MODEL"], "process/model")
