"""Keep the interactive entry point working alongside structured reviews."""

import io
import unittest
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
        self.assertEqual(chat.main(), 0)
        self.assertEqual(client.complete.call_count, 1)
        self.assertEqual(client.complete.call_args.args[0][0], {"role": "system", "content": CHAT_PROMPT})
        self.assertIn("Please provide the quote.", stdout.getvalue())
        self.assertFalse(load_dotenv.call_args.kwargs["override"])
