"""Six opt-in live cases. Grade structured meaning, not exact report prose."""

import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from dotenv import load_dotenv

from procurement_agent.agent import ProcurementAgent
from procurement_agent.openrouter import OpenRouterClient
from procurement_agent.tools.issues import SEVERITIES
from procurement_agent.tools.packet import parse_packet
from procurement_agent.tools.report import render_report


BUYER = """RFQ for part SP-842, 1,200 units per year.
Drawing revision D is required.
Deliver to Manchester, UK.
Release 100 units each month.
Delivery must be within 6 weeks of release.
Selection requires firm per-piece prices, tooling costs and payment terms."""


def offer(name, price="6.40", revision="D"):
    return f"""{name}
Part SP-842, drawing rev {revision}.
GBP {price} per piece at annual volume 1,200.
Tooling included. No separately billed tooling.
DDP Manchester, UK; freight, duties and final delivery included.
Lead time: 4 weeks from release, including production, transit and final delivery.
Payment Net 30.
Price fixed through 31 December 2027. Minimum release 100 pieces."""


@unittest.skipUnless(os.environ.get("RUN_SEMANTIC_EVALS") == "1", "Opt in with RUN_SEMANTIC_EVALS=1; uses paid model calls")
class SemanticEvals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        cls.provider = OpenRouterClient.from_env()
        print(f"[eval] Model: {cls.provider.model}", file=sys.stderr, flush=True)

    def review(self, replies, buyer=BUYER):
        packet = parse_packet("\n===PACKET===\n".join([buyer, *replies]))
        client = Mock(complete=Mock(wraps=self.provider.complete))
        # Observe the existing final render boundary without changing its output or workflow.
        with patch("procurement_agent.harness.render_report", wraps=render_report) as renderer:
            ProcurementAgent(client, on_progress=lambda message: print(f"[eval] {message}", file=sys.stderr, flush=True)).review(
                "\n===PACKET===\n".join([buyer, *replies]))
        renderer.assert_called_once()
        self.extraction, amounts, self.analysis = renderer.call_args.args
        self.amounts = {item["source_id"]: item for item in amounts}
        self.decisions = {item["supplier_id"]: item for item in self.analysis["recommendation"]}
        self.issues = {item["id"]: item for item in self.analysis["issues"]}
        self.questions = self.analysis["follow_up_questions"]
        self.assertLessEqual(client.complete.call_count, 4)
        self.assertFalse(self.extraction.get("validation_warnings"), "Clean synthetic evidence was excluded")
        self.assertFalse(self.analysis.get("coverage_warnings"), "Important questions/conditions remain uncovered")
        self.assertEqual(set(self.decisions), set(packet.sources) - {"buyer"})
        self.assertEqual(len(self.extraction["suppliers"]), len(replies))
        records = {"buyer": self.extraction["buyer"], **{s["source_id"]: s for s in self.extraction["suppliers"]}}
        for owner, record in records.items():
            self.assertEqual(record["part"]["value"], "SP-842", f"Invented or lost part for {owner}")
            self.assertIsNone(record["material_finish"]["value"], "No case specifies material/finish")
            for field, fact in record.items():
                if field == "source_id":
                    continue
                if fact["value"] is None:
                    self.assertIsNone(fact["evidence"])
                else:
                    self.assertIn(" ".join(fact["evidence"].split()), " ".join(packet.sources[owner].split()))
            if owner != "buyer":
                self.assertIsNone(record["tooling_amount"]["value"], "Included/pending tooling is not a numeric zero")
                self.assertIsNone(record["deposit_amount"]["value"], "No refundable container deposit was quoted")
            questions = [q for q in self.questions if q["owner"] == owner]
            ranks = [SEVERITIES.index(q["severity"]) for q in questions]
            self.assertEqual(ranks, sorted(ranks))
            if owner != "buyer":
                self.assertLessEqual(len(questions), 3)
            unresolved = [i for i in self.issues.values() if i["owner"] == owner]
            if questions and unresolved:
                self.assertEqual(ranks[0], min(SEVERITIES.index(i["severity"]) for i in unresolved))
        covered = {ref for q in self.questions for ref in q["issue_ids"]}
        for issue in self.issues.values():
            if issue["severity"] == "BLOCKER":
                self.assertIn(issue["id"], covered)
                if issue["owner"] != "buyer":
                    self.assertIn(self.decisions[issue["owner"]]["action"], {"hold", "do_not_advance"})
        for decision in self.decisions.values():
            self.assertLessEqual(set(decision["clarification_issue_ids"]), covered)

    def require_follow_up(self, owner, field, severity="HIGH"):
        issues = {i["id"] for i in self.issues.values() if i["owner"] == owner and field in i["fields"]
                  and SEVERITIES.index(i["severity"]) <= SEVERITIES.index(severity)}
        self.assertTrue(issues, f"Missing important {owner}.{field} issue")
        self.assertTrue(any(q["owner"] == owner and field in q["fields"] and issues.intersection(q["issue_ids"])
                            for q in self.questions), f"Missing targeted {owner}.{field} question")
        if owner != "buyer" and self.decisions[owner]["action"] == "advance":
            self.assertTrue(issues.intersection(self.decisions[owner]["clarification_issue_ids"]),
                            "Conditional advancement must name the unresolved issue")

    def test_clear_comparable_quotes(self):
        other = offer("Birch Forming").replace("GBP 6.40 per piece", "GBP 620.00 / 100 pieces")
        self.review([offer("Aster Industries"), other])
        for owner, unit, annual in (("supplier_1", "6.40", "7680"), ("supplier_2", "6.20", "7440")):
            self.assertEqual(Decimal(self.amounts[owner]["normalized_unit_price"]), Decimal(unit))
            self.assertEqual(Decimal(self.amounts[owner]["quantity_price_extension"]), Decimal(annual))
            self.assertEqual(self.amounts[owner]["currency_info"]["status"], "explicit")
            self.assertEqual(self.decisions[owner]["action"], "advance")
        important = [(i["owner"], i["fields"], i["reason"]) for i in self.issues.values()
                     if i["severity"] in {"BLOCKER", "HIGH"}]
        self.assertFalse(important, f"Clear quotes received unnecessary material risks: {important}")
        self.assertEqual(self.questions, [], "A clear offer should not generate busywork")

    def test_missing_required_unit_price(self):
        reply = offer("Cobalt Supply").replace("GBP 6.40 per piece at annual volume 1,200.",
                                               "Pricing will follow separately; settlement currency is GBP.")
        self.review([reply])
        self.assertIsNone(self.extraction["suppliers"][0]["quoted_price"]["value"])
        self.assertIsNone(self.amounts["supplier_1"]["normalized_unit_price"])
        self.assertIsNone(self.amounts["supplier_1"]["quantity_price_extension"])
        self.assertIn(self.decisions["supplier_1"]["action"], {"hold", "do_not_advance"})
        self.require_follow_up("supplier_1", "quoted_price")

    def test_conflicting_supplier_revisions_do_not_define_buyer_revision(self):
        buyer = BUYER.replace("Drawing revision D is required.", "Engineering has not confirmed the required drawing revision.")
        self.review([offer("Dune Manufacturing", revision="C"), offer("Elm Precision", revision="D")], buyer)
        self.assertIsNone(self.extraction["buyer"]["revision"]["value"])
        self.require_follow_up("buyer", "revision", "BLOCKER")
        for owner in self.decisions:
            self.assertIsNone(self.amounts[owner]["revision_blocker"])
            self.assertIsNotNone(self.amounts[owner]["revision_comparability_gap"])
            self.assertIn(self.decisions[owner]["action"], {"advance", "hold"})
            self.require_follow_up(owner, "revision")

    def test_nominal_low_price_with_excluded_freight_and_duty(self):
        cheap = offer("Harbor Components", "3.10").replace(
            "DDP Manchester, UK; freight, duties and final delivery included.",
            "Freight and duty excluded; customer must arrange transport.")
        self.review([offer("Glade Supply", "7.20"), cheap])
        self.assertEqual(Decimal(self.amounts["supplier_2"]["normalized_unit_price"]), Decimal("3.10"))
        self.assertIsNone(self.amounts["supplier_2"]["extension_plus_stated_tooling"])
        self.assertIn(self.decisions["supplier_2"]["action"], {"advance", "hold"})
        self.require_follow_up("supplier_2", "delivery_terms")

    def test_provisional_price_and_tooling_remain_unresolved(self):
        reply = offer("Indigo Fabrication", "3.80").replace(
            "GBP 3.80 per piece", "Approximately GBP 3.80 per piece").replace(
            "Tooling included. No separately billed tooling.", "Tooling cost pending engineering review.").replace(
            "Price fixed through 31 December 2027.", "Price is provisional until engineering review.")
        self.review([reply])
        self.assertEqual(Decimal(self.amounts["supplier_1"]["normalized_unit_price"]), Decimal("3.80"))
        self.assertIsNotNone(self.extraction["suppliers"][0]["price_qualification"]["value"])
        self.assertIsNone(self.amounts["supplier_1"]["extension_plus_stated_tooling"])
        self.assertIn(self.decisions["supplier_1"]["action"], {"advance", "hold"})
        self.require_follow_up("supplier_1", "price_qualification")
        self.require_follow_up("supplier_1", "tooling_amount")

    def test_fifth_supplier_with_unfamiliar_style_and_energy_supplement(self):
        fifth = """Hi buyer — Wren Atelier here, replying from the shop floor.
SP-842 / drawing D is the print I priced. Annual 1,200, calls of 100 are fine.
GBP 4.90 per piece. The fixture bill is absorbed; no separate tooling invoice.
Door to door: DDP Manchester, UK, all freight, duties and final delivery paid by us.
Four weeks from your release including manufacture, transit and final delivery. Net 30.
Each dispatch invoice may carry an energy supplement. Its formula and ceiling are not agreed.
This quote is valid through 31 December 2027."""
        self.review([*(offer(name) for name in ("Juniper Works", "Kite Supply", "Moraine Parts", "Solace Systems")), fifth])
        supplier = self.extraction["suppliers"][4]
        self.assertIn("wren", supplier["supplier"]["value"].casefold())
        self.assertEqual(Decimal(self.amounts["supplier_5"]["normalized_unit_price"]), Decimal("4.90"))
        self.assertIsNotNone(supplier["price_adjustment"]["value"])
        self.assertIn(self.decisions["supplier_5"]["action"], {"advance", "hold"})
        self.require_follow_up("supplier_5", "price_adjustment")


if __name__ == "__main__":
    unittest.main()
