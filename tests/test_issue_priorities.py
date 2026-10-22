"""Grounding, selection and recommendation consistency for issue-led questions."""

import copy
import json
import unittest
from unittest.mock import Mock

from procurement_agent.agent import ProcurementAgent
from procurement_agent.schema import BUYER_FIELDS, SUPPLIER_FIELDS, ValidationError, validate_analysis, validate_extraction
from procurement_agent.tools.calculations import calculate_amounts, follow_up_context
from procurement_agent.tools.packet import parse_packet
from procurement_agent.tools.report import render_report


def fact(value=None, evidence=None):
    return {"value": value, "evidence": evidence}


def case():
    text = (
        "Part AX-902\n1,000 units for this order\nRequired drawing Rev C\n"
        "Ship to Denver\nRequired delivery within 6 weeks\nRelease the full order at once\n"
        "===PACKET===\n"
        "Oak Assembly\nPart AX-902 drawing Rev C\nUSD 5.20 per piece\nTooling included\n"
        "DDP Denver\nLead time 12 weeks from release\n"
        "Payment 30% deposit; refund terms to be confirmed\n"
        "First-article approval required; approval duration unspecified\n"
        "Validity 30 days; issue date not supplied\nMOQ 100 pieces"
    )
    buyer = {f: fact() for f in BUYER_FIELDS}
    buyer.update({"part": fact("AX-902", "L1"), "quantity": fact("1000", "L2"),
                  "quantity_basis": fact("order", "L2"), "revision": fact("C", "L3"),
                  "destination": fact("Denver", "L4"), "required_delivery": fact("within 6 weeks", "L5"),
                  "release_schedule": fact("Full order at once", "L6")})
    supplier = {f: fact() for f in SUPPLIER_FIELDS}
    supplier.update({"supplier": fact("Oak Assembly", "L1"), "part": fact("AX-902", "L2"),
                     "revision": fact("C", "L2"), "quoted_price": fact("5.20", "L3"),
                     "price_basis_quantity": fact("1", "L3"), "currency": fact("USD", "L3"),
                     "tooling_terms": fact("Included", "L4"), "delivery_terms": fact("DDP Denver", "L5"),
                     "lead_time": fact("12 weeks from release", "L6"),
                     "payment_terms": fact("30% deposit; refund terms to be confirmed", "L7"),
                     "other_terms": fact("First-article approval required; duration unspecified", "L8"),
                     "validity": fact("30 days; issue date not supplied", "L9"), "moq": fact("100", "L10")})
    wire = {"buyer": buyer, "suppliers": {"supplier_1": supplier}}
    packet = parse_packet(text)
    extraction = validate_extraction(wire, packet.sources)
    calculations = calculate_amounts(extraction)
    context = follow_up_context(extraction, calculations)
    analysis = {"issues": [], "risks": [{"text": "Delivery timing and approval need clarification.", "source_ids": ["buyer", "supplier_1"]}],
                "recommendation": {"supplier_1": {"action": "advance", "text": "Pursue a firm compliant offer.",
                                                    "source_ids": ["supplier_1"], "clarification_issue_ids": []}},
                "follow_up_questions": []}
    return text, wire, packet, extraction, calculations, context, analysis


def add_issue(analysis, topic, field, severity, reason, question, *, basis="ambiguous", category="other", evidence_fields=None):
    issue_id = "supplier_1_" + topic
    analysis["issues"].append({"id": issue_id, "owner": "supplier_1", "category": category,
                               "severity": severity, "basis": basis, "reason": reason, "fields": [field],
                               "evidence_fields": evidence_fields or [field]})
    if question is not None:
        analysis["follow_up_questions"].append({"owner": "supplier_1", "priority": "blocking" if severity == "BLOCKER" else "optional" if severity == "LOW" else "important",
                                                "text": question, "fields": [field], "source_ids": ["supplier_1"], "issue_ids": [issue_id]})
    return issue_id


class IssuePriorityTests(unittest.TestCase):
    def setUp(self):
        self.text, self.wire, self.packet, self.extraction, self.calculations, self.context, self.analysis = case()

    def validate(self, analysis=None):
        return validate_analysis(analysis or self.analysis, self.packet.sources,
                                 follow_up_context=self.context, extraction=self.extraction)

    def test_deterministic_layer_does_not_reask_known_terms_or_optional_nulls(self):
        self.assertEqual(self.context["supplier_1"]["issues"], [])
        self.assertEqual(self.context["buyer"]["issues"], [])
        self.assertEqual(self.validate()["follow_up_questions"], [])

    def test_provisional_cost_and_explicit_cost_exclusions_receive_priorities_and_evidence(self):
        supplier = self.extraction["suppliers"][0]
        supplier["price_qualification"] = fact("Indicative", "Indicative USD 5.20 per piece")
        supplier["tooling_terms"] = fact("Pending engineering review", "Tooling pending engineering review")
        supplier["delivery_terms"] = fact("EXW plant", "EXW plant")
        calculations = calculate_amounts(self.extraction)
        context = follow_up_context(self.extraction, calculations)
        issues = {i["id"]: i for i in context["supplier_1"]["issues"]}
        for field in ("price_qualification", "tooling_amount", "delivery_terms"):
            issue = issues["supplier_1_" + field]
            self.assertEqual(issue["severity"], "HIGH")
            self.assertTrue(issue["reason"])
            self.assertTrue(issue["evidence_fields"])
        self.assertNotIn("supplier_1_moq", issues)

    def test_severity_sorting_and_top_three_cap_preserve_blockers(self):
        add_issue(self.analysis, "validity", "validity", "LOW", "The issue date is unresolved.", "What date was this offer issued?")
        add_issue(self.analysis, "refund", "payment_terms", "MEDIUM", "Refund conditions on the advance payment are unresolved.", "When is the advance payment refundable?")
        add_issue(self.analysis, "approval", "other_terms", "HIGH", "Approval duration before deliveries is unspecified.", "Who approves the first article and how long does approval take?")
        blocker = add_issue(self.analysis, "timing", "lead_time", "BLOCKER", "Quoted 12-week timing conflicts with the buyer's 6-week requirement.", "Can you offer delivery meeting the buyer's required timing?", basis="conflict", category="delivery")
        result = self.validate()
        self.assertEqual([q["severity"] for q in result["follow_up_questions"]], ["BLOCKER", "HIGH", "MEDIUM"])
        self.assertEqual(len(result["follow_up_questions"]), 3)
        evidence = next(i for i in result["issues"] if i["id"] == blocker)["evidence"]
        self.assertIn("Lead time 12 weeks from release", [e["evidence"] for e in evidence])
        self.assertIn("Required delivery within 6 weeks", [e["evidence"] for e in evidence])
        report = render_report(self.extraction, self.calculations, result).split("## 4. Follow-up questions", 1)[1]
        self.assertLess(report.index("Can you offer"), report.index("Who approves"))
        self.assertLess(report.index("Who approves"), report.index("When is"))
        self.assertNotIn("What date", report)

    def test_lower_priority_question_cannot_replace_an_unaddressed_high_issue(self):
        add_issue(self.analysis, "approval", "other_terms", "HIGH", "Approval duration is unspecified.", None)
        add_issue(self.analysis, "validity", "validity", "LOW", "The issue date is unresolved.", "What date was this offer issued?")
        with self.assertRaisesRegex(ValidationError, "Higher-priority unresolved issues"):
            self.validate()

    def test_blocker_cannot_be_omitted(self):
        add_issue(self.analysis, "timing", "lead_time", "BLOCKER", "The quoted timing conflicts with required delivery.", None, basis="conflict")
        with self.assertRaisesRegex(ValidationError, "BLOCKER questions required"):
            self.validate()

    def test_deterministic_moq_blocker_cannot_be_downgraded_by_model_metadata(self):
        self.text = self.text.replace("MOQ 100 pieces", "MOQ 2,000 pieces")
        self.packet = parse_packet(self.text)
        self.wire["suppliers"]["supplier_1"]["moq"] = fact("2000", "L10")
        self.extraction = validate_extraction(self.wire, self.packet.sources)
        self.calculations = calculate_amounts(self.extraction)
        self.context = follow_up_context(self.extraction, self.calculations)
        add_issue(self.analysis, "moq", "moq", "LOW", "Treat the MOQ as routine clarification.", "Can you accept our full 1,000-piece order?", basis="conflict", category="quantity")
        self.analysis["recommendation"]["supplier_1"]["action"] = "do_not_advance"
        result = self.validate()
        question = result["follow_up_questions"][0]
        self.assertEqual(question["severity"], "BLOCKER")
        self.assertEqual(question["priority"], "blocking")
        issue = next(i for i in result["issues"] if i["id"] == "supplier_1_moq")
        self.assertIn("exceeds", issue["reason"])
        self.assertIn("1000", [e["value"] for e in issue["evidence"]])

    def test_known_moq_and_included_tooling_are_not_missing_supplier_information(self):
        for field, topic in (("moq", "minimum"), ("tooling_amount", "tooling_cost")):
            analysis = copy.deepcopy(self.analysis)
            add_issue(analysis, topic, field, "HIGH", "This term is missing.", "Please supply this term.", basis="missing", evidence_fields=["tooling_terms" if field == "tooling_amount" else "moq"])
            with self.subTest(field=field), self.assertRaisesRegex(ValidationError, "already answered"):
                self.validate(analysis)

    def test_unverified_issue_requires_actual_validation_warning(self):
        add_issue(self.analysis, "unverified_payment", "payment_terms", "HIGH", "Payment could not be validated.", "Can you verify payment terms?", basis="unverified")
        with self.assertRaisesRegex(ValidationError, "actual validation warning"):
            self.validate()

    def test_unanchored_ambiguity_is_rejected(self):
        add_issue(self.analysis, "invented", "price_adjustment", "HIGH", "The unquoted index adjustment conflicts with the offer.", "Which index applies?", evidence_fields=["price_adjustment"])
        with self.assertRaisesRegex(ValidationError, "supporting quoted evidence"):
            self.validate()

    def test_an_answered_heuristic_candidate_does_not_generate_a_redundant_question(self):
        self.text = self.text.replace("Lead time 12 weeks from release", "Lead time 4 weeks including production, transit and final delivery")
        self.wire["suppliers"]["supplier_1"]["lead_time"] = fact("4 weeks including production, transit and final delivery", "L6")
        self.packet = parse_packet(self.text)
        self.extraction = validate_extraction(self.wire, self.packet.sources)
        self.calculations = calculate_amounts(self.extraction)
        self.context = follow_up_context(self.extraction, self.calculations)
        candidate = copy.deepcopy(next(i for i in self.context["supplier_1"]["issues"] if i["id"] == "supplier_1_lead_time"))
        candidate["basis"] = "answered"
        candidate["reason"] = "The quote explicitly includes production, transit and final delivery in the four weeks."
        self.analysis["issues"] = [candidate]
        result = self.validate()
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["follow_up_questions"], [])

    def test_a_confirmed_blocker_cannot_be_dismissed_as_answered(self):
        self.text = self.text.replace("Required drawing Rev C", "Required drawing Rev B")
        self.wire["buyer"]["revision"] = fact("B", "L3")
        self.packet = parse_packet(self.text)
        self.extraction = validate_extraction(self.wire, self.packet.sources)
        self.calculations = calculate_amounts(self.extraction)
        self.context = follow_up_context(self.extraction, self.calculations)
        candidate = copy.deepcopy(next(i for i in self.context["supplier_1"]["issues"] if i["id"] == "supplier_1_revision"))
        candidate["basis"] = "answered"
        candidate["reason"] = "The supplier references revision C."
        self.analysis["issues"] = [candidate]
        with self.assertRaisesRegex(ValidationError, "confirmed blockers"):
            self.validate()

    def test_a_low_topic_cannot_hide_in_a_high_question_to_skip_a_medium_issue(self):
        high = add_issue(self.analysis, "approval", "other_terms", "HIGH", "Approval duration is unspecified.", "How long does approval take, and when was the offer issued?")
        low = add_issue(self.analysis, "validity", "validity", "LOW", "The issue date is unresolved.", None)
        add_issue(self.analysis, "refund", "payment_terms", "MEDIUM", "Refund terms need clarification.", None)
        self.analysis["follow_up_questions"][0]["issue_ids"] = [high, low]
        with self.assertRaisesRegex(ValidationError, "Higher-priority unresolved issues"):
            self.validate()

    def test_recommendation_condition_requires_a_question_for_that_issue(self):
        issue_id = add_issue(self.analysis, "approval", "other_terms", "HIGH", "Approval duration is unspecified.", None)
        decision = self.analysis["recommendation"]["supplier_1"]
        decision["text"] = "Advance with clarification about first-article approval timing."
        decision["clarification_issue_ids"] = [issue_id]
        with self.assertRaisesRegex(ValidationError, "Recommendation/follow-up inconsistency"):
            self.validate()

    def test_consistency_is_checked_after_the_question_cap(self):
        low = add_issue(self.analysis, "validity", "validity", "LOW", "The issue date is unresolved.", "What date was this offer issued?")
        add_issue(self.analysis, "refund", "payment_terms", "MEDIUM", "Refund terms need clarification.", "When is the payment refundable?")
        add_issue(self.analysis, "approval", "other_terms", "HIGH", "Approval duration is unspecified.", "How long does approval take?")
        add_issue(self.analysis, "timing", "lead_time", "BLOCKER", "Quoted timing conflicts with required delivery.", "Can you meet required delivery?", basis="conflict")
        self.analysis["recommendation"]["supplier_1"]["clarification_issue_ids"] = [low]
        with self.assertRaisesRegex(ValidationError, "Recommendation/follow-up inconsistency"):
            self.validate()

    def test_a_shared_buyer_condition_is_covered_in_the_buyer_section(self):
        self.analysis["issues"].append({"id": "buyer_priorities", "owner": "buyer", "category": "other", "basis": "missing",
                                        "severity": "MEDIUM", "reason": "Tradeoffs between cost and delivery have not been specified.",
                                        "fields": ["priorities"], "evidence_fields": ["priorities", "quantity"]})
        self.analysis["recommendation"]["supplier_1"]["clarification_issue_ids"] = ["buyer_priorities"]
        self.analysis["follow_up_questions"].append({"owner": "buyer", "priority": "important", "fields": ["priorities"],
                                                    "issue_ids": ["buyer_priorities"], "source_ids": ["buyer"],
                                                    "text": "How should cost and delivery tradeoffs be prioritized?"})
        result = self.validate()
        self.assertEqual([q["owner"] for q in result["follow_up_questions"]], ["buyer"])

    def test_consistency_failure_uses_existing_correction_and_preserves_generated_question(self):
        issue_id = add_issue(self.analysis, "approval", "other_terms", "HIGH", "Approval duration is unspecified.", None)
        self.analysis["recommendation"]["supplier_1"]["clarification_issue_ids"] = [issue_id]
        corrected = copy.deepcopy(self.analysis)
        question = "Who signs off the first article, and what approval duration should the delivery plan allow?"
        corrected["follow_up_questions"].append({"owner": "supplier_1", "priority": "important", "text": question,
                                                "fields": ["other_terms"], "source_ids": ["supplier_1"], "issue_ids": [issue_id]})
        client = Mock(complete=Mock(side_effect=[json.dumps(self.wire), json.dumps(self.analysis), json.dumps(corrected)]))
        report = ProcurementAgent(client).review(self.text)
        self.assertEqual(client.complete.call_count, 3)
        self.assertIn("Recommendation/follow-up inconsistency", client.complete.call_args_list[2].args[0][-1]["content"])
        self.assertIn(question, report)
        self.assertIn("First-article approval required", report)

    def test_cross_owner_links_and_unknown_issue_links_are_rejected(self):
        issue_id = add_issue(self.analysis, "approval", "other_terms", "HIGH", "Approval duration is unspecified.", "How long does approval take?")
        for wrong in ("owner", "issue"):
            analysis = copy.deepcopy(self.analysis)
            if wrong == "owner":
                analysis["follow_up_questions"][0]["owner"] = "buyer"
            else:
                analysis["follow_up_questions"][0]["issue_ids"] = [issue_id + "_unknown"]
            with self.subTest(wrong=wrong), self.assertRaises(ValidationError):
                self.validate(analysis)


if __name__ == "__main__":
    unittest.main()
