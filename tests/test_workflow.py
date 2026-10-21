"""Offline acceptance tests; fixture responses are not live model validation."""

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from procurement_agent.agent import ProcurementAgent
from procurement_agent.cli import main
from procurement_agent.openrouter import OpenRouterError
from procurement_agent.schema import (
    BUYER_FIELDS, SUPPLIER_FIELDS, ValidationError, analysis_format, extraction_format, load_response, validate_analysis,
    validate_extraction,
)
from procurement_agent.tools.calculations import calculate_amounts, follow_up_context
from procurement_agent.tools.packet import MAX_INPUT_BYTES, parse_packet, read_packet
from procurement_agent.tools.report import render_report, write_report

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "quote_packet.txt"


def fact(value=None, evidence=None):
    return {"value": value, "evidence": evidence}


def extracted_example():
    buyer = {field: fact() for field in BUYER_FIELDS}
    buyer.update({
        "part": fact("BRK-4471-A", "part BRK-4471-A"),
        "description": fact("Machined aluminium bracket", "machined aluminium bracket"),
        "quantity": fact("60000", "60,000 units a year"),
        "quantity_basis": fact("annual", "60,000 units a year"),
    })
    suppliers = [{"source_id": f"supplier_{index}", **{field: fact() for field in SUPPLIER_FIELDS}}
                 for index in range(1, 5)]
    for item in suppliers:
        item["part"] = fact("BRK-4471-A", "BRK-4471-A")
    suppliers[0].update({
        "supplier": fact("Tri-State Metalcraft", "Tri-State Metalcraft"),
        "quoted_price": fact("4.85", "$4.85 per piece"),
        "price_basis_quantity": fact("1", "$4.85 per piece"),
        "currency": fact("$", "$4.85"),
        "annual_volume": fact("60000", "60k annual"),
        "min_release": fact("5000", "releases of 5,000 or more"),
        "tooling_amount": fact("6200", "Tooling is $6,200, one time, invoiced on PO."),
        "tooling_currency": fact("$", "Tooling is $6,200"),
        "tooling_terms": fact("One time, invoiced on PO", "one time, invoiced on PO"),
        "delivery_terms": fact("FOB supplier dock in Cleveland", "FOB our dock in Cleveland"),
        "lead_time": fact("4 weeks from release", "4 weeks from release"),
        "payment_terms": fact("Net 30", "Net 30"),
        "validity": fact("90 days, issue date unknown", "Pricing firm for 90 days"),
        "material_finish": fact("Anodizing in house; compliance unconfirmed", "Anodizing is done in house"),
    })
    suppliers[1].update({
        "supplier": fact("Nordkant Prazisionsteile GmbH", "Nordkant Prazisionsteile GmbH"),
        "revision": fact("C", "drawing rev C"),
        "quoted_price": fact("3.92", "60,000 pcs EUR 3.92 / pc"),
        "price_basis_quantity": fact("1", "EUR 3.92 / pc"),
        "currency": fact("EUR", "EUR 3.92"),
        "annual_volume": fact("60000", "60,000 pcs EUR 3.92 / pc"),
        "tooling_terms": fact("Included, amortized over first 40,000 pcs", "Tooling: included, amortized over first 40,000 pcs"),
        "deposit_amount": fact("2800", "deposit EUR 2,800 (refundable)"),
        "deposit_currency": fact("EUR", "deposit EUR 2,800"),
        "deposit_terms": fact("Refundable container deposit", "returnable steel containers, deposit EUR 2,800 (refundable)"),
        "delivery_terms": fact("DDP Columbus, Ohio", "DDP Columbus, Ohio"),
        "lead_time": fact("11 weeks from order release", "11 weeks from order release"),
        "payment_terms": fact("Net 60; 2% within 10 days", "Net 60 days. 2% discount for payment within 10 days."),
        "price_adjustment": fact("Quarterly LME adjustment above 4% movement", "Prices subject to quarterly adjustment per LME aluminium index,\nbase 2026 Q1. Adjustments applied where index moves more than 4%."),
        "validity": fact("30 days from issue; date missing", "30 days from date of issue"),
    })
    suppliers[2].update({
        "supplier": fact("Pacific Rim Components", "Pacific Rim Components"),
        "revision": fact("B", "DRAWING REV B"),
        "quoted_price": fact("3240", "USD 3,240.00 / 1,000 PCS"),
        "price_basis_quantity": fact("1000", "USD 3,240.00 / 1,000 PCS"),
        "currency": fact("USD", "USD 3,240.00"),
        "moq": fact("25000", "MOQ 25,000 PCS"),
        "tooling_amount": fact("4800", "TOOLING USD 4,800.00"),
        "tooling_currency": fact("USD", "TOOLING USD 4,800.00"),
        "delivery_terms": fact("FOB Kaohsiung; freight/duty excluded", "TERMS FOB KAOHSIUNG\nLEAD TIME 9 WEEKS PRODUCTION\nSHIPPING 5 WEEKS OCEAN\nTOOLING USD 4,800.00\nPAYMENT 30% T/T DEPOSIT, 70% BEFORE SHIPMENT\nNOTES PRICE BASED ON DRAWING REV B\n ANODIZING SUBCONTRACTED\n FREIGHT AND DUTY NOT INCLUDED"),
        "lead_time": fact("9 weeks production plus 5 weeks ocean; not full delivered lead time", "LEAD TIME 9 WEEKS PRODUCTION\nSHIPPING 5 WEEKS OCEAN"),
        "payment_terms": fact("30% deposit, 70% before shipment", "30% T/T DEPOSIT, 70% BEFORE SHIPMENT"),
        "material_finish": fact("Anodizing subcontracted", "ANODIZING SUBCONTRACTED"),
    })
    suppliers[3].update({
        "supplier": fact("Brightwater Precision", "Brightwater Precision"),
        "quoted_price": fact("4.40", "around $4.40 a piece"),
        "price_basis_quantity": fact("1", "$4.40 a piece"),
        "currency": fact("$", "$4.40"),
        "price_qualification": fact("Approximate", "around $4.40 a piece at your volumes"),
        "tooling_terms": fact("Pending engineering review", "Tooling we'd need to confirm after our engineering team reviews the\ndrawing"),
        "delivery_terms": fact("EXW Queretaro", "EXW Queretaro"),
        "lead_time": fact("6-8 weeks once running; startup unknown", "6-8 weeks once we're running"),
        "other_terms": fact("Four weeks of free safety stock at supplier facility", "we'd carry four weeks of safety stock for\nyou at our facility at no charge"),
    })
    return {"buyer": buyer, "suppliers": suppliers}


def model_extraction():
    """Wire-format fixture with named suppliers and source-line citations."""
    data = extracted_example()
    sources = parse_packet(EXAMPLE.read_text()).sources
    records = [("buyer", data["buyer"]), *[(item["source_id"], item) for item in data["suppliers"]]]
    for source_id, record in records:
        lines = sources[source_id].splitlines()
        for field, value in record.items():
            if field == "source_id" or value["value"] is None:
                continue
            needle = " ".join(value["evidence"].split())
            found = False
            for size in range(1, len(lines) + 1):
                for start in range(len(lines) - size + 1):
                    excerpt = " ".join("\n".join(lines[start:start + size]).split())
                    if needle in excerpt:
                        first, last = start + 1, start + size
                        value["evidence"] = f"L{first}" if first == last else f"L{first}-L{last}"
                        found = True
                        break
                if found:
                    break
            if not found:
                raise AssertionError(f"Fixture evidence missing from {source_id}.{field}")
    return {"buyer": data["buyer"], "suppliers": {
        item["source_id"]: {field: value for field, value in item.items() if field != "source_id"}
        for item in data["suppliers"]
    }}


def analysis_example():
    return {
        "risks": [
            {"text": "Required revision, finish, destination, release schedule and required delivery date are missing.", "source_ids": ["buyer"]},
            {"text": "Quoted revisions differ; confirm the required revision before treating offers as equivalent.", "source_ids": ["supplier_2", "supplier_3", "buyer"]},
            {"text": "The container deposit is refundable cash exposure, not permanent cost. Clarify amortization and index adjustments.", "source_ids": ["supplier_2"]},
            {"text": "Approximate pricing, unconfirmed tooling and steady-state lead time prevent a firm comparison.", "source_ids": ["supplier_4"]},
        ],
        "recommendation": [
            {"supplier_id": "supplier_1", "action": "advance", "text": "Pursue a firm delivered offer; confirm revision and planned releases.", "source_ids": ["buyer", "supplier_1"]},
            {"supplier_id": "supplier_2", "action": "advance", "text": "Pursue for stated DDP coverage; clarify index adjustments and tooling amortization.", "source_ids": ["supplier_2"]},
            {"supplier_id": "supplier_3", "action": "hold", "text": "Ask the buyer to establish the required revision before checking compliance; freight and duty remain excluded.", "source_ids": ["buyer", "supplier_2", "supplier_3"]},
            {"supplier_id": "supplier_4", "action": "hold", "text": "Obtain firm pricing and tooling, and confirm currency and drawing revision.", "source_ids": ["supplier_4"]},
        ],
        "follow_up_questions": [
            {"owner": "buyer", "priority": "blocking", "fields": ["revision"], "text": "Which drawing revision is required? Nordkant quotes C and Pacific Rim B; neither establishes the buyer requirement.", "source_ids": ["buyer", "supplier_2", "supplier_3"]},
            {"owner": "buyer", "priority": "blocking", "fields": ["destination"], "text": "Where must the parts be delivered so delivered costs can be compared?", "source_ids": ["buyer"]},
            {"owner": "buyer", "priority": "blocking", "fields": ["release_schedule"], "text": "What release quantities and frequency are planned against the 60,000-unit annual demand?", "source_ids": ["buyer"]},
            {"owner": "supplier_1", "priority": "important", "fields": ["currency", "revision", "material_finish", "delivery_terms", "release_schedule"], "text": "Please confirm currency, required-revision compliance, finish inclusion, delivered freight and price for the planned release schedule.", "source_ids": ["supplier_1"]},
            {"owner": "supplier_2", "priority": "important", "fields": ["tooling_terms", "price_adjustment", "deposit_terms", "validity"], "text": "Please explain post-amortization pricing, the index adjustment formula, deposit recovery and quote issue date.", "source_ids": ["supplier_2"]},
            {"owner": "supplier_3", "priority": "blocking", "fields": ["revision"], "text": "Can you re-quote against the buyer-confirmed current drawing revision?", "source_ids": ["supplier_3", "buyer"]},
            {"owner": "supplier_3", "priority": "blocking", "fields": ["delivery_terms"], "text": "What freight and duty charges apply to the buyer destination?", "source_ids": ["supplier_3"]},
            {"owner": "supplier_3", "priority": "blocking", "fields": ["lead_time"], "text": "Does the quoted lead time include end-to-end transit through final delivery?", "source_ids": ["supplier_3"]},
            {"owner": "supplier_4", "priority": "blocking", "fields": ["tooling_amount"], "text": "What is the tooling cost after engineering review?", "source_ids": ["supplier_4"]},
            {"owner": "supplier_4", "priority": "blocking", "fields": ["currency"], "text": "Can you confirm the pricing currency explicitly?", "source_ids": ["supplier_4"]},
            {"owner": "supplier_4", "priority": "blocking", "fields": ["revision"], "text": "Which drawing revision has engineering reviewed?", "source_ids": ["supplier_4"]},
        ],
    }


def model_analysis():
    data = analysis_example()
    data["recommendation"] = {
        item["supplier_id"]: {key: value for key, value in item.items() if key != "supplier_id"}
        for item in data["recommendation"]
    }
    return data


class PacketTests(unittest.TestCase):
    def test_raw_text_and_both_separator_spacings(self):
        packet = parse_packet("\ufeffBRK-4471-A\n60,000 units\r\n===PACKET===\r\nEmail reply\n=== PACKET ===\nChat reply")
        self.assertEqual(packet.buyer, "BRK-4471-A\n60,000 units")
        self.assertEqual(packet.sources["supplier_2"], "Chat reply")

    def test_reject_empty_missing_separator_and_empty_blocks(self):
        for text in ("", "No replies", "===PACKET===\nReply", "Buyer\n===PACKET==="):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_packet(text)

    def test_input_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.txt"
            path.write_bytes(b"x" * (MAX_INPUT_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "exceeds"):
                read_packet(path)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.sources = parse_packet(EXAMPLE.read_text()).sources
        self.data = extracted_example()

    def test_reference_extraction_is_valid_and_order_is_stable(self):
        self.data["suppliers"].reverse()
        result = validate_extraction(self.data, self.sources)
        self.assertEqual(result["suppliers"][0]["source_id"], "supplier_1")
        self.assertIsNone(result["buyer"]["revision"]["value"])

    def test_named_records_and_line_citations_resolve_to_original_text(self):
        wire = model_extraction()
        original = copy.deepcopy(wire)
        data = validate_extraction(wire, self.sources)
        self.assertEqual([item["source_id"] for item in data["suppliers"]], list(self.sources)[1:])
        self.assertIn("$4.85 per piece", data["suppliers"][0]["quoted_price"]["evidence"])
        self.assertNotEqual(data["suppliers"][0]["quoted_price"]["evidence"], wire["suppliers"]["supplier_1"]["quoted_price"]["evidence"])
        self.assertEqual(wire, original)

    def test_missing_named_supplier_is_a_structural_error_even_in_partial_mode(self):
        wire = model_extraction()
        del wire["suppliers"]["supplier_4"]
        with self.assertRaisesRegex(ValidationError, "suppliers: expected fields"):
            validate_extraction(wire, self.sources, allow_partial=True)

    def test_invalid_line_references_and_blank_lines_are_rejected(self):
        for citation in ("L999", "L4-L2", "L2-L999", "L" + "9" * 100, "supplier_2:L1"):
            wire = model_extraction()
            wire["suppliers"]["supplier_1"]["payment_terms"]["evidence"] = citation
            with self.subTest(citation=citation), self.assertRaises(ValidationError):
                validate_extraction(wire, self.sources)
        wire = model_extraction()
        sources = {**self.sources, "supplier_1": self.sources["supplier_1"] + "\n\nExtra note"}
        blank = len(self.sources["supplier_1"].splitlines()) + 1
        wire["suppliers"]["supplier_1"]["payment_terms"]["evidence"] = f"L{blank}"
        with self.assertRaisesRegex(ValidationError, "nonempty source text"):
            validate_extraction(wire, sources)

    def test_partial_mode_excludes_unsupported_price_and_withholds_calculations(self):
        wire = model_extraction()
        wire["suppliers"]["supplier_3"]["quoted_price"]["value"] = "99999"
        result = validate_extraction(wire, self.sources, allow_partial=True)
        supplier = result["suppliers"][2]
        self.assertIsNone(supplier["quoted_price"]["value"])
        self.assertEqual(supplier["price_basis_quantity"]["value"], "1000")
        self.assertEqual(supplier["currency"]["value"], "USD")
        calculation = calculate_amounts(result)[2]
        self.assertIsNone(calculation["normalized_unit_price"])
        self.assertIsNone(calculation["quantity_price_extension"])
        self.assertTrue(any(item["field"] == "quoted_price" for item in result["validation_warnings"]))

    def test_minimum_release_is_not_accepted_as_an_moq(self):
        wire = model_extraction()
        supplier = wire["suppliers"]["supplier_1"]
        supplier["moq"] = fact("5000", supplier["min_release"]["evidence"])
        with self.assertRaisesRegex(ValidationError, "explicit minimum-order evidence"):
            validate_extraction(wire, self.sources)

    def test_reject_evidence_from_another_supplier(self):
        self.data["suppliers"][0]["revision"] = fact("C", "drawing rev C")
        with self.assertRaisesRegex(ValidationError, "evidence must occur"):
            validate_extraction(self.data, self.sources)

    def test_part_number_with_bad_excerpt_is_grounded_in_own_source(self):
        self.data["suppliers"][0]["part"] = fact("BRK-4471-A", "Part: BRK-4471-A")
        result = validate_extraction(self.data, self.sources)
        self.assertEqual(result["suppliers"][0]["part"]["evidence"], "BRK-4471-A")

    def test_part_number_missing_from_own_source_still_fails(self):
        self.data["suppliers"][0]["part"] = fact("BRK-9999-Z", "Part: BRK-9999-Z")
        with self.assertRaisesRegex(ValidationError, "supplier_1.part: evidence must occur"):
            validate_extraction(self.data, self.sources)

    def test_reject_part_that_is_only_a_substring_of_another_identifier(self):
        self.data["suppliers"][0]["part"] = fact("BRK-4471", "Part: BRK-4471")
        with self.assertRaisesRegex(ValidationError, "supplier_1.part: evidence must occur"):
            validate_extraction(self.data, self.sources)

    def test_correction_reports_multiple_invalid_fields(self):
        self.data["suppliers"][0]["revision"] = fact("C", "drawing rev C")
        self.data["suppliers"][2]["quoted_price"]["value"] = "3.24"
        with self.assertRaises(ValidationError) as error:
            validate_extraction(self.data, self.sources)
        self.assertIn("supplier_1.revision", str(error.exception))
        self.assertIn("supplier_3.quoted_price", str(error.exception))

    def test_raw_values_instead_of_fact_objects_have_actionable_shape_errors(self):
        for field in BUYER_FIELDS:
            self.data["buyer"][field] = self.data["buyer"][field]["value"]
        with self.assertRaises(ValidationError) as error:
            validate_extraction(self.data, self.sources)
        message = str(error.exception)
        self.assertIn("buyer.part: expected an object with fields [value, evidence]; got str", message)
        self.assertIn("buyer.revision: expected an object with fields [value, evidence]; got NoneType", message)
        self.assertNotIn("BRK-4471-A", message)

    def test_extra_fact_keys_are_reported_without_logging_values(self):
        self.data["buyer"]["part"]["confidence"] = "sensitive model output"
        with self.assertRaises(ValidationError) as error:
            validate_extraction(self.data, self.sources)
        self.assertIn("got fields [value, evidence, confidence]", str(error.exception))
        self.assertNotIn("sensitive model output", str(error.exception))

    def test_reject_number_without_supporting_evidence(self):
        self.data["suppliers"][2]["quoted_price"]["value"] = "3.24"
        with self.assertRaisesRegex(ValidationError, "numeric value"):
            validate_extraction(self.data, self.sources)

    def test_model_inferred_usd_is_preserved_as_a_symbol_then_labelled_inferred(self):
        self.data["suppliers"][0]["currency"]["value"] = "USD"
        data = validate_extraction(self.data, self.sources)
        self.assertEqual(data["suppliers"][0]["currency"]["value"], "$")
        info = calculate_amounts(data)[0]["currency_info"]
        self.assertEqual(info["code"], "USD")
        self.assertEqual(info["status"], "inferred")

    def test_reject_duplicate_suppliers_and_invalid_fact_shapes(self):
        broken = copy.deepcopy(self.data)
        broken["suppliers"][1] = broken["suppliers"][0]
        with self.assertRaises(ValidationError):
            validate_extraction(broken, self.sources)
        for value in ([], {"value": "x"}, fact(None, "BRK-4471-A"), fact("NaN", "60,000")):
            broken = copy.deepcopy(self.data)
            broken["buyer"]["quantity"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_extraction(broken, self.sources)

    def test_reject_ambiguous_json(self):
        for raw in ('{"a": 1, "a": 2}', '{"a": NaN}', '[]', 'not json'):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                load_response(raw)


class CalculationTests(unittest.TestCase):
    def test_reference_amounts_and_deposits(self):
        results = calculate_amounts(extracted_example())
        self.assertEqual([item["quantity_price_extension"] for item in results],
                         ["291000.00", "235200.00", "194400", "264000.00"])
        self.assertEqual(results[2]["normalized_unit_price"], "3.24")
        self.assertEqual(results[0]["extension_plus_stated_tooling"], "297200.00")
        self.assertEqual(results[2]["extension_plus_stated_tooling"], "199200")
        self.assertEqual(results[1]["refundable_deposit"], "2800")
        self.assertIsNone(results[1]["extension_plus_stated_tooling"])
        self.assertIsNone(results[3]["extension_plus_stated_tooling"])
        self.assertEqual([result["currency"] for result in results], ["$", "EUR", "USD", "$"])
        self.assertTrue(any("releases" in text for text in results[0]["warnings"]))
        self.assertTrue(any("MOQ" in text for text in results[2]["warnings"]))

    def test_unmatched_annual_tier_withholds_extension(self):
        data = extracted_example()
        data["buyer"]["quantity_basis"]["value"] = "unspecified"
        results = calculate_amounts(data)
        self.assertIsNone(results[0]["quantity_price_extension"])
        self.assertIsNone(results[1]["quantity_price_extension"])
        self.assertTrue(any("annual" in warning for warning in results[1]["warnings"]))

    def test_unknown_quantity_and_mixed_tooling_currency(self):
        data = extracted_example()
        data["suppliers"][2]["tooling_currency"]["value"] = "EUR"
        self.assertIsNone(calculate_amounts(data)[2]["extension_plus_stated_tooling"])
        data["buyer"]["quantity"] = fact()
        self.assertTrue(all(item["quantity_price_extension"] is None for item in calculate_amounts(data)))

    def test_no_intermediate_rounding(self):
        data = extracted_example()
        supplier = data["suppliers"][2]
        supplier["quoted_price"]["value"] = "1"
        supplier["price_basis_quantity"]["value"] = "3"
        self.assertEqual(calculate_amounts(data)[2]["quantity_price_extension"], "20000")

    def test_unverified_tooling_terms_withhold_tooling_scenario(self):
        packet = parse_packet(EXAMPLE.read_text())
        wire = model_extraction()
        wire["suppliers"]["supplier_1"]["tooling_terms"] = fact("Unsupported terms", "L999")
        data = validate_extraction(wire, packet.sources, allow_partial=True)
        result = calculate_amounts(data)[0]
        self.assertEqual(result["quantity_price_extension"], "291000.00")
        self.assertIsNone(result["extension_plus_stated_tooling"])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.packet = EXAMPLE.read_text()
        self.extraction = extracted_example()
        self.analysis = analysis_example()

    def client(self, *responses):
        return Mock(model="test/model", timeout=60, complete=Mock(side_effect=list(responses)))

    def test_full_two_call_workflow_and_four_sections(self):
        client = self.client(json.dumps(model_extraction()), json.dumps(model_analysis()))
        report = ProcurementAgent(client).review(self.packet)
        self.assertEqual(client.complete.call_count, 2)
        self.assertEqual([line for line in report.splitlines() if line.startswith("## ")], [
            "## 1. Normalized supplier comparison", "## 2. Risks / unknowns",
            "## 3. Shortlist / recommendation", "## 4. Follow-up questions",
        ])
        for expected in ("USD 3.24", "194,400.00", "EUR 235,200.00", "Unknown / not stated", "Source evidence", "amortized over first 40,000", "around $4.40", "not full delivered lead time"):
            self.assertIn(expected, report)
        analysis_input = json.loads(client.complete.call_args_list[1].args[0][1]["content"])
        self.assertEqual(analysis_input["calculations"][2]["quantity_price_extension"], "194400")
        for index, name in enumerate(("procurement_extraction", "procurement_analysis")):
            contract = client.complete.call_args_list[index].kwargs["response_format"]
            self.assertEqual(contract["type"], "json_schema")
            self.assertEqual(contract["json_schema"]["name"], name)
            self.assertTrue(contract["json_schema"]["strict"])

    def test_one_correction_then_success(self):
        client = self.client("invalid json", json.dumps(self.extraction), json.dumps(self.analysis))
        ProcurementAgent(client).review(self.packet)
        self.assertEqual(client.complete.call_count, 3)
        self.assertIn("failed validation", client.complete.call_args_list[1].args[0][-1]["content"])
        self.assertEqual(client.complete.call_args_list[1].args[0][-2], {"role": "assistant", "content": "invalid json"})
        self.assertEqual(client.complete.call_args_list[0].kwargs["response_format"],
                         client.complete.call_args_list[1].kwargs["response_format"])

    def test_progress_is_emitted_before_each_model_request(self):
        events = []
        responses = iter((json.dumps(self.extraction), json.dumps(self.analysis)))
        def complete(messages, **kwargs):
            self.assertIn("waiting for model response", events[-1])
            return next(responses)
        client = Mock(complete=Mock(side_effect=complete))
        ProcurementAgent(client, on_progress=events.append).review(self.packet)
        self.assertIn("Extraction: waiting for model response (request 1/3)...", events)
        self.assertIn("Analysis: waiting for model response (request 2/3)...", events)
        self.assertEqual(events[-1], "Rendering the report...")

    def test_validation_feedback_repairs_remaining_evidence_errors(self):
        broken = copy.deepcopy(self.extraction)
        broken["suppliers"][0]["part"] = fact("BRK-4471-A", "Part: BRK-4471-A")
        broken["suppliers"][0]["payment_terms"] = fact("Net 30", "Payment: Net 30")
        client = self.client(json.dumps(broken), json.dumps(self.extraction), json.dumps(self.analysis))
        ProcurementAgent(client).review(self.packet)
        correction = client.complete.call_args_list[1].args[0]
        self.assertEqual(correction[-2]["content"], json.dumps(broken))
        self.assertIn("supplier_1.payment_terms", correction[-1]["content"])
        self.assertIn("using L3 or L3-L5", correction[-1]["content"])

    def test_report_survives_the_reported_optional_field_failures(self):
        missing = model_extraction()
        del missing["suppliers"]["supplier_4"]
        broken = model_extraction()
        supplier = broken["suppliers"]["supplier_1"]
        supplier["price_qualification"] = fact("UNSUPPORTED_TEST_CLAIM", "L999")
        supplier["annual_volume"] = fact("60000", "L999")
        supplier["moq"] = fact("99999", supplier["quoted_price"]["evidence"])
        supplier["other_terms"] = fact("", None)
        broken["suppliers"]["supplier_4"]["other_terms"] = fact("UNSUPPORTED_TEST_CLAIM", "L999")
        client = self.client(json.dumps(missing), json.dumps(broken), json.dumps(self.analysis))
        progress = []
        report = ProcurementAgent(client, on_progress=progress.append).review(self.packet)
        self.assertEqual(client.complete.call_count, 3)
        self.assertIn("Data quality", report)
        self.assertIn("Unverified / excluded", report)
        self.assertIn("Data-quality notes", report)
        self.assertNotIn("Harness checks", report)
        self.assertNotIn("evidence line range is outside", report)
        self.assertNotIn("UNSUPPORTED_TEST_CLAIM", report)
        self.assertTrue(any("Extraction incomplete" in event for event in progress))
        payload = json.loads(client.complete.call_args_list[2].args[0][1]["content"])
        warnings = payload["extraction"]["validation_warnings"]
        self.assertTrue(all("reason" not in item for item in warnings))
        self.assertEqual({item["field"] for item in warnings}, {"price_qualification", "annual_volume", "moq", "other_terms"})
        self.assertIsNone(payload["extraction"]["suppliers"][0]["moq"]["value"])
        self.assertIsNone(payload["calculations"][0]["quantity_price_extension"])
        self.assertEqual(payload["calculations"][2]["quantity_price_extension"], "194400")
        self.assertIn("Unknown / not stated", report)

    def test_shared_correction_budget(self):
        for responses in (
            ("{}", "{}"),
            ("{}", json.dumps(self.extraction), "{}"),
            (json.dumps(self.extraction), "{}", "{}"),
        ):
            client = self.client(*responses)
            with self.subTest(responses=responses), self.assertRaises(ValidationError):
                ProcurementAgent(client).review(self.packet)
            self.assertLessEqual(client.complete.call_count, 3)

    def test_no_transport_retry(self):
        client = self.client(OpenRouterError("OpenRouter HTTP 402. Check credits."))
        with self.assertRaises(OpenRouterError):
            ProcurementAgent(client).review(self.packet)
        self.assertEqual(client.complete.call_count, 1)

    def test_reject_unknown_analysis_sources_and_unknown_question_owner(self):
        self.analysis["risks"][0]["source_ids"] = ["unknown"]
        with self.assertRaises(ValidationError):
            validate_analysis(self.analysis, parse_packet(self.packet).sources)
        self.analysis = analysis_example()
        self.analysis["follow_up_questions"][0]["owner"] = "unknown_supplier"
        with self.assertRaises(ValidationError):
            validate_analysis(self.analysis, parse_packet(self.packet).sources)

    def test_source_and_model_text_cannot_create_report_sections_or_html(self):
        self.analysis["risks"][0]["text"] = "<script>alert(1)</script>\n## Injected section\n[click](https://example.com)"
        report = render_report(self.extraction, calculate_amounts(self.extraction), self.analysis)
        self.assertNotIn("<script>", report)
        self.assertNotIn("\n## Injected", report)
        self.assertNotIn("[click](", report)

    def test_cli_writes_report_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.md"
            client = self.client(json.dumps(self.extraction), json.dumps(self.analysis))
            with patch("procurement_agent.cli.OpenRouterClient.from_env", return_value=client), patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO) as progress:
                self.assertEqual(main(["review", str(EXAMPLE), "-o", str(output)]), 0)
                self.assertIn("Extraction: waiting", progress.getvalue())
                self.assertIn("Saving", progress.getvalue())
            previous = output.read_text()
            with patch("procurement_agent.cli.OpenRouterClient.from_env") as config, patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(main(["review", str(EXAMPLE), "-o", str(output)]), 1)
                config.assert_not_called()
            with patch("procurement_agent.cli.OpenRouterClient.from_env", return_value=self.client(OpenRouterError("failed"))), patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(main(["review", str(EXAMPLE), "-o", str(output), "--force"]), 1)
            self.assertEqual(output.read_text(), previous)

    def test_cli_cannot_overwrite_input_even_with_force(self):
        with patch("procurement_agent.cli.OpenRouterClient.from_env") as config, patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["review", str(EXAMPLE), "-o", str(EXAMPLE), "--force"]), 1)
            config.assert_not_called()

    def test_cli_cancellation_exits_without_writing_report(self):
        client = self.client(KeyboardInterrupt())
        with tempfile.TemporaryDirectory() as directory, patch("sys.stderr", new_callable=io.StringIO) as stderr:
            output = Path(directory) / "report.md"
            with patch("procurement_agent.cli.OpenRouterClient.from_env", return_value=client):
                self.assertEqual(main(["review", str(EXAMPLE), "-o", str(output)]), 130)
            self.assertFalse(output.exists())
            self.assertIn("Cancelled", stderr.getvalue())

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-secret", "OPENROUTER_MODEL": "test/model"})
    @patch("procurement_agent.openrouter.urlopen")
    def test_cli_through_real_adapter_with_mocked_http(self, send):
        def response_for(content):
            response = Mock()
            response.__enter__ = Mock(return_value=io.BytesIO(json.dumps({
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
            }).encode()))
            response.__exit__ = Mock(return_value=False)
            return response

        send.side_effect = [response_for(model_extraction()), response_for(model_analysis())]
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
            output = Path(directory) / "report.md"
            self.assertEqual(main(["review", str(EXAMPLE), "--output", str(output)]), 0)
            self.assertIn("## 4. Follow-up questions", output.read_text())
            self.assertEqual(send.call_count, 2)
            for index, call in enumerate(send.call_args_list):
                request = json.loads(call.args[0].data)
                self.assertEqual(request["model"], "test/model")
                self.assertNotIn("tools", request)
                self.assertEqual(request["response_format"]["type"], "json_schema")
                name = "procurement_extraction" if index == 0 else "procurement_analysis"
                self.assertEqual(request["response_format"]["json_schema"]["name"], name)
                self.assertEqual(request["provider"], {"require_parameters": True})


class StructuredContractTests(unittest.TestCase):
    def test_extraction_contract_covers_all_fields_with_required_fact_objects(self):
        contract = extraction_format(["supplier_1", "supplier_2"])
        schema = contract["json_schema"]["schema"]
        self.assertEqual(set(schema["required"]), {"buyer", "suppliers"})
        buyer = schema["properties"]["buyer"]
        self.assertEqual(set(buyer["properties"]), set(BUYER_FIELDS))
        self.assertEqual(set(buyer["required"]), set(BUYER_FIELDS))
        named_suppliers = schema["properties"]["suppliers"]
        self.assertEqual(named_suppliers["type"], "object")
        self.assertEqual(named_suppliers["required"], ["supplier_1", "supplier_2"])
        self.assertEqual(set(named_suppliers["properties"]), {"supplier_1", "supplier_2"})
        supplier = schema["$defs"]["supplier"]
        self.assertEqual(set(supplier["properties"]), set(SUPPLIER_FIELDS))
        self.assertEqual(named_suppliers["properties"]["supplier_1"], {"$ref": "#/$defs/supplier"})
        fact_schema = schema["$defs"]["fact"]
        self.assertEqual(fact_schema["type"], "object")
        self.assertEqual(set(fact_schema["required"]), {"value", "evidence"})
        self.assertEqual(fact_schema["properties"]["value"]["type"], ["string", "null"])
        self.assertIn("pattern", fact_schema["properties"]["evidence"])
        self.assertEqual(buyer["properties"]["part"], {"$ref": "#/$defs/fact"})
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(buyer["additionalProperties"])
        self.assertFalse(supplier["additionalProperties"])
        self.assertFalse(fact_schema["additionalProperties"])

    def test_analysis_contract_uses_case_source_ids(self):
        sources = ["buyer", "supplier_1"]
        schema = analysis_format(sources)["json_schema"]["schema"]
        self.assertEqual(set(schema["required"]), {"risks", "recommendation", "follow_up_questions"})
        for key in ("risks", "follow_up_questions"):
            section = schema["properties"][key]
            item = section["items"]
            self.assertFalse(item["additionalProperties"])
            self.assertEqual(item["properties"]["source_ids"]["items"]["enum"], sources)
        follow_up = schema["properties"]["follow_up_questions"]["items"]
        self.assertEqual(follow_up["properties"]["owner"]["enum"], sources)
        self.assertEqual(follow_up["properties"]["priority"]["enum"], ["blocking", "important", "optional"])
        self.assertIn("fields", follow_up["required"])
        self.assertTrue({"revision", "destination", "release_schedule"}.issubset(
            follow_up["properties"]["fields"]["items"]["enum"]))
        recommendations = schema["properties"]["recommendation"]
        self.assertEqual(recommendations["required"], ["supplier_1"])
        self.assertEqual(recommendations["properties"]["supplier_1"]["properties"]["action"]["enum"],
                         ["advance", "hold", "do_not_advance"])


class BuyerReportQualityTests(unittest.TestCase):
    def setUp(self):
        self.data = extracted_example()
        self.analysis = analysis_example()

    def report(self):
        return render_report(self.data, calculate_amounts(self.data), self.analysis)

    def test_currency_provenance_keeps_dollar_prices_visible(self):
        calculations = calculate_amounts(self.data)
        self.assertEqual([(item["currency_info"]["code"], item["currency_info"]["status"]) for item in calculations],
                         [("USD", "inferred"), ("EUR", "explicit"), ("USD", "explicit"), ("USD", "inferred")])
        report = self.report()
        self.assertIn("USD 4.85 (inferred currency)", report)
        self.assertIn("USD 4.40 (inferred currency)", report)
        self.assertIn("USD (inferred; quoted $)", report)
        self.assertIn("EUR (explicit)", report)
        self.assertIn("supplier confirmation required", report)
        self.assertEqual(self.data["suppliers"][0]["currency"]["value"], "$")

    def test_no_context_or_conflicting_dollar_context_does_not_infer_usd(self):
        self.data["suppliers"][2]["currency"] = fact()
        result = calculate_amounts(self.data)[0]
        self.assertEqual(result["currency_info"]["status"], "unresolved")
        self.assertEqual(result["normalized_unit_price"], "4.85")
        self.data = extracted_example()
        self.data["suppliers"][1]["currency"] = fact("CAD", "CAD 3.92 / pc")
        result = calculate_amounts(self.data)[0]
        self.assertEqual(result["currency_info"]["code"], "$")
        self.assertEqual(result["currency_info"]["status"], "unresolved")

    def test_missing_currency_does_not_discard_a_grounded_price(self):
        wire = model_extraction()
        wire["suppliers"]["supplier_1"]["currency"] = fact()
        data = validate_extraction(wire, parse_packet(EXAMPLE.read_text()).sources)
        result = calculate_amounts(data)[0]
        self.assertEqual(result["normalized_unit_price"], "4.85")
        self.assertEqual(result["currency_info"]["status"], "unknown")
        self.assertIsNone(result["extension_plus_stated_tooling"])

    def test_revision_blocker_overrides_a_model_advance_recommendation(self):
        self.data["buyer"]["revision"] = fact("C", "Required drawing revision C")
        decision = self.analysis["recommendation"][2]
        decision["action"] = "advance"
        decision["text"] = "Advance immediately with no revision checks."
        report = self.report()
        row = next(line for line in report.splitlines() if line.startswith("| Pacific Rim Components |"))
        self.assertIn("Do not advance yet", row)
        self.assertIn("Quoted Rev B differs from buyer-required Rev C", row)
        self.assertNotIn("Advance immediately", report)
        self.assertIn("Drawing revision blocker", report)

    def test_supplier_revisions_do_not_establish_the_buyer_requirement(self):
        for index in (1, 2):
            self.analysis["recommendation"][index]["action"] = "advance"
        calculations = calculate_amounts(self.data)
        self.assertTrue(all(item["revision_blocker"] is None for item in calculations))
        self.assertIsNone(self.data["buyer"]["revision"]["value"])
        report = self.report()
        for supplier in ("Nordkant Prazisionsteile GmbH", "Pacific Rim Components"):
            row = next(line for line in report.splitlines() if line.startswith(f"| {supplier} |"))
            self.assertIn("Hold / needs clarification", row)
            self.assertIn("buyer's required revision is unknown", row)
            self.assertIn("Nordkant Prazisionsteile GmbH", row)
            self.assertIn("Rev C", row)
            self.assertIn("Pacific Rim Components", row)
            self.assertIn("Rev B", row)
        self.assertNotIn("Drawing revision blocker", report)
        self.assertNotIn("buyer-required Rev C", report)

    def test_buyer_revision_takes_precedence_over_another_suppliers_revision(self):
        self.data["buyer"]["revision"] = fact("B", "Required drawing revision B")
        calculations = calculate_amounts(self.data)
        self.assertIsNone(calculations[2]["revision_blocker"])
        self.assertIn("buyer-required Rev B", calculations[1]["revision_blocker"])

    def test_nominal_pacific_rim_price_has_no_landed_cost_advantage_claim(self):
        result = calculate_amounts(self.data)[2]
        self.assertEqual(result["normalized_unit_price"], "3.24")
        self.assertIn("freight and duty excluded", result["cost_comparability_note"])
        self.assertIn("No confirmed landed-cost advantage", result["cost_comparability_note"])
        self.assertIn("Nominal unit price / piece (not landed cost)", self.report())

    def test_shortlist_and_blocking_questions_are_explicit(self):
        report = self.report()
        self.assertIn("Shortlist / advance", report)
        self.assertIn("Hold / needs clarification", report)
        pacific = report.split("### Pacific Rim Components\n", 1)[1].split("### Brightwater Precision", 1)[0]
        for expected in ("Resolve first", "re-quote", "drawing revision", "freight and duty", "buyer destination", "end-to-end transit"):
            self.assertIn(expected, pacific)
        brightwater = report.split("### Brightwater Precision\n", 1)[1]
        for expected in ("tooling cost", "pricing currency", "drawing revision"):
            self.assertIn(expected, brightwater)

    def test_validation_details_become_concise_buyer_notes(self):
        self.data["validation_warnings"] = [{
            "source_id": "supplier_1", "field": "moq",
            "reason": "supplier_1.moq: numeric value must appear in its evidence.",
        }]
        report = self.report()
        self.assertIn("Data-quality notes", report)
        self.assertIn("Tri-State Metalcraft", report)
        self.assertIn("Confirm MOQ", report)
        self.assertIn("Source evidence", report)
        self.assertNotIn("Harness checks", report)
        self.assertNotIn("Model assessment", report)
        self.assertNotIn("supplier_1.moq:", report)
        self.assertNotIn("numeric value must appear", report)

    def test_each_supplier_needs_one_valid_action(self):
        sources = parse_packet(EXAMPLE.read_text()).sources
        self.analysis["recommendation"].pop()
        with self.assertRaisesRegex(ValidationError, "every supplier"):
            validate_analysis(self.analysis, sources)


class DynamicFollowUpTests(unittest.TestCase):
    def test_context_contains_gaps_uncertainty_validation_and_risk_signals(self):
        packet = parse_packet(EXAMPLE.read_text())
        wire = model_extraction()
        wire["suppliers"]["supplier_4"]["other_terms"] = fact("Unsupported", "L999")
        data = validate_extraction(wire, packet.sources, allow_partial=True)
        calculations = calculate_amounts(data)
        context = follow_up_context(data, calculations)
        self.assertIn("revision", context["buyer"]["missing_fields"])
        self.assertIn("destination", context["buyer"]["missing_fields"])
        self.assertIn("currency", context["supplier_4"]["uncertain_fields"])
        self.assertIn("other_terms", context["supplier_4"]["validation_fields"])
        self.assertTrue(context["supplier_3"]["detected_risks"][0]["blocking"])
        self.assertIn("freight and duty excluded", context["supplier_3"]["comparability_gaps"][0])
        self.assertTrue(all("priority_questions" not in item for item in calculations))

    def test_missing_buyer_requirements_are_blockers_owned_by_the_buyer(self):
        data = extracted_example()
        context = follow_up_context(data, calculate_amounts(data))
        risks = context["buyer"]["detected_risks"]
        self.assertEqual({risk["field"] for risk in risks}, {"revision", "destination", "release_schedule"})
        self.assertTrue(all(risk["blocking"] and risk["resolution_owner"] == "buyer" for risk in risks))
        revision = next(risk for risk in risks if risk["field"] == "revision")
        self.assertIn("Nordkant Prazisionsteile GmbH references drawing revision C", revision["detail"])
        self.assertIn("supplier_2", revision["source_ids"])
        self.assertIn("supplier_3", revision["source_ids"])
        self.assertIsNone(data["buyer"]["revision"]["value"])
        self.assertIsNone(data["buyer"]["destination"]["value"])

    def test_supplier_only_or_low_priority_questions_do_not_resolve_buyer_blockers(self):
        data = extracted_example()
        context = follow_up_context(data, calculate_amounts(data))
        sources = parse_packet(EXAMPLE.read_text()).sources
        for change in ("remove_buyer", "supplier_owner", "lower_priority", "missing_destination"):
            analysis = analysis_example()
            if change == "remove_buyer":
                analysis["follow_up_questions"] = [q for q in analysis["follow_up_questions"] if q["owner"] != "buyer"]
            elif change == "supplier_owner":
                for q in analysis["follow_up_questions"]:
                    if q["owner"] == "buyer":
                        q["owner"] = "supplier_2"
            elif change == "lower_priority":
                for q in analysis["follow_up_questions"]:
                    if q["owner"] == "buyer":
                        q["priority"] = "important"
            else:
                analysis["follow_up_questions"] = [q for q in analysis["follow_up_questions"] if "destination" not in q["fields"]]
            with self.subTest(change=change), self.assertRaisesRegex(ValidationError, "Missing blocking buyer follow-up questions.*destination"):
                validate_analysis(analysis, sources, follow_up_context=context)

    def test_known_buyer_requirements_do_not_force_reconfirmation(self):
        data = extracted_example()
        data["buyer"].update({
            "revision": fact("B", "Required Rev B"), "destination": fact("Cleveland", "Ship to Cleveland"),
            "release_schedule": fact("5,000 monthly", "Release 5,000 monthly"),
        })
        context = follow_up_context(data, calculate_amounts(data))
        self.assertEqual(context["buyer"]["detected_risks"], [])
        analysis = analysis_example()
        analysis["follow_up_questions"] = []
        validate_analysis(analysis, parse_packet(EXAMPLE.read_text()).sources, follow_up_context=context)

    def test_harness_requests_model_authored_buyer_questions_when_omitted(self):
        incomplete = model_analysis()
        incomplete["follow_up_questions"] = [q for q in incomplete["follow_up_questions"] if q["owner"] != "buyer"]
        corrected = copy.deepcopy(incomplete)
        questions = {
            "revision": "Nordkant references C and Pacific Rim B; which drawing revision must all offers meet?",
            "destination": "Where must the bracket be delivered so the FOB, DDP and EXW offers can be compared?",
            "release_schedule": "How will the 60,000 units be released, including order sizes and frequency?",
        }
        corrected["follow_up_questions"] += [
            {"owner": "buyer", "priority": "blocking", "fields": [field], "text": text, "source_ids": ["buyer"]}
            for field, text in questions.items()
        ]
        client = Mock(complete=Mock(side_effect=[json.dumps(model_extraction()), json.dumps(incomplete), json.dumps(corrected)]))
        report = ProcurementAgent(client).review(EXAMPLE.read_text())
        self.assertEqual(client.complete.call_count, 3)
        correction = client.complete.call_args_list[2].args[0][-1]["content"]
        for field in questions:
            self.assertIn(field, correction)
        buyer_section = report.split("### Buyer\n", 1)[1].split("### Tri-State Metalcraft", 1)[0]
        self.assertIn("Resolve first", buyer_section)
        for question in questions.values():
            self.assertIn(question, buyer_section)

    def test_renderer_uses_only_model_questions_and_sorts_priorities(self):
        data = extracted_example()
        analysis = analysis_example()
        analysis["follow_up_questions"] = [
            {"owner": "supplier_1", "priority": priority, "fields": ["other_terms"], "text": text, "source_ids": ["supplier_1"]}
            for priority, text in (("optional", "Optional topic?"), ("important", "Important topic?"),
                                   ("blocking", "Blocking topic?"), ("optional", "Blocking topic?"))
        ]
        analysis = validate_analysis(analysis, parse_packet(EXAMPLE.read_text()).sources)
        report = render_report(data, calculate_amounts(data), analysis).split("## 4. Follow-up questions", 1)[1]
        self.assertLess(report.index("Blocking topic?"), report.index("Important topic?"))
        self.assertLess(report.index("Important topic?"), report.index("Optional topic?"))
        self.assertEqual(report.count("Blocking topic?"), 1)
        self.assertIn("No follow-up questions drafted for this party.", report)
        self.assertNotIn("Which drawing revision", report)
        self.assertNotIn("What freight and duty", report)

    def test_empty_questions_do_not_force_busywork_and_invalid_priority_is_rejected(self):
        sources = parse_packet(EXAMPLE.read_text()).sources
        analysis = analysis_example()
        analysis["follow_up_questions"] = []
        self.assertEqual(validate_analysis(analysis, sources)["follow_up_questions"], [])
        analysis = analysis_example()
        analysis["follow_up_questions"][0]["priority"] = "unknown"
        with self.assertRaisesRegex(ValidationError, "Follow-up priority"):
            validate_analysis(analysis, sources)

    def test_fifth_supplier_flows_through_same_two_call_pipeline(self):
        fifth_text = (
            "Forge Delta\nPart BRK-4471-A, drawing Rev C\nIndicative USD 5.10 per piece\n"
            "Tooling to be confirmed after fixture design\nDDP Columbus, Ohio\n"
            "First-article approval required before series deliveries; approval duration unspecified\n"
            "Lead time 6 weeks after first-article approval"
        )
        packet_text = EXAMPLE.read_text() + "\n===PACKET===\n" + fifth_text
        wire = model_extraction()
        wire["suppliers"]["supplier_5"] = {field: fact() for field in SUPPLIER_FIELDS}
        wire["suppliers"]["supplier_5"].update({
            "supplier": fact("Forge Delta", "L1"), "part": fact("BRK-4471-A", "L2"),
            "revision": fact("C", "L2"), "quoted_price": fact("5.10", "L3"),
            "price_basis_quantity": fact("1", "L3"), "currency": fact("USD", "L3"),
            "price_qualification": fact("Indicative", "L3"),
            "tooling_terms": fact("Pending fixture design", "L4"),
            "delivery_terms": fact("DDP Columbus, Ohio", "L5"),
            "other_terms": fact("First-article approval required; approval duration unspecified", "L6"),
            "lead_time": fact("6 weeks after first-article approval", "L7"),
        })
        analysis = model_analysis()
        analysis["recommendation"]["supplier_5"] = {
            "action": "hold", "text": "Resolve approval timing and tooling before advancing.", "source_ids": ["supplier_5"],
        }
        question = "Who approves the first article, and how long does approval take before the quoted six-week lead time starts?"
        analysis["follow_up_questions"].append({
            "owner": "supplier_5", "priority": "blocking", "fields": ["other_terms", "lead_time"], "text": question, "source_ids": ["supplier_5"],
        })
        client = Mock(complete=Mock(side_effect=[json.dumps(wire), json.dumps(analysis)]))
        report = ProcurementAgent(client).review(packet_text)
        self.assertEqual(client.complete.call_count, 2)
        extraction_contract = client.complete.call_args_list[0].kwargs["response_format"]["json_schema"]["schema"]
        self.assertIn("supplier_5", extraction_contract["properties"]["suppliers"]["required"])
        payload = json.loads(client.complete.call_args_list[1].args[0][1]["content"])
        self.assertEqual(set(payload["follow_up_context"]), {"buyer", *(f"supplier_{i}" for i in range(1, 6))})
        fifth_context = payload["follow_up_context"]["supplier_5"]
        self.assertIn("tooling_amount", fifth_context["missing_fields"])
        self.assertIn("price_qualification", fifth_context["uncertain_fields"])
        self.assertIn("First-article approval", payload["extraction"]["suppliers"][4]["other_terms"]["value"])
        analysis_contract = client.complete.call_args_list[1].kwargs["response_format"]["json_schema"]["schema"]
        self.assertIn("supplier_5", analysis_contract["properties"]["follow_up_questions"]["items"]["properties"]["owner"]["enum"])
        self.assertIn("### Forge Delta", report)
        self.assertIn(question, report)


def variable_supplier_fixture(count, *, part="BRK-4471-A", quantity=60000, revision="C", currency="USD", annual=True):
    """Synthetic packet and structured responses for arbitrary supplier counts."""
    quantity_text = f"{quantity:,} units a year" if annual else f"{quantity:,} units for this order"
    revision_text = f"Required drawing Rev {revision}" if revision else "Description: Rubber sealing ring"
    buyer_text = f"Part {part}\n{quantity_text}\n{revision_text}\nShip to Columbus, Ohio"
    buyer = {field: fact() for field in BUYER_FIELDS}
    buyer.update({"part": fact(part, "L1"), "quantity": fact(str(quantity), "L2"),
                  "quantity_basis": fact("annual" if annual else "order", "L2"), "revision": fact(revision, "L3") if revision else fact(),
                  "destination": fact("Columbus, Ohio", "L4")})
    if not revision:
        buyer["description"] = fact("Rubber sealing ring", "L3")
    blocks = [buyer_text]
    suppliers, recommendations, questions = {}, {}, [{
        "owner": "buyer", "priority": "blocking", "fields": ["release_schedule" if annual else "required_delivery"], "text": "What release schedule is required?" if annual else "When must this order arrive?", "source_ids": ["buyer"],
    }]
    for index in range(1, count + 1):
        source_id = f"supplier_{index}"
        name, price = f"Variable Vendor {index}", f"5.{index:02d}"
        quoted_part = f"Part {part} drawing Rev {revision}" if revision else f"Part {part}"
        blocks.append(f"{name}\n{quoted_part}\n{currency} {price} per piece\nTooling included\nDDP Columbus, Ohio\nLead time 4 weeks from release")
        suppliers[source_id] = {field: fact() for field in SUPPLIER_FIELDS}
        suppliers[source_id].update({
            "supplier": fact(name, "L1"), "part": fact(part, "L2"), "revision": fact(revision, "L2") if revision else fact(),
            "quoted_price": fact(price, "L3"), "price_basis_quantity": fact("1", "L3"), "currency": fact(currency, "L3"),
            "tooling_terms": fact("Included", "L4"), "delivery_terms": fact("DDP Columbus, Ohio", "L5"),
            "lead_time": fact("4 weeks from release", "L6"),
        })
        recommendations[source_id] = {"action": "advance", "text": "Clarify commercial terms before selection.", "source_ids": [source_id]}
        question = f"Will you hold {currency} {price} per piece for our planned release quantities?" if annual else "What payment terms apply to this order?"
        questions.append({"owner": source_id, "priority": "important", "fields": ["min_release"] if annual else ["payment_terms"], "text": question, "source_ids": [source_id]})
    return "\n===PACKET===\n".join(blocks), {"buyer": buyer, "suppliers": suppliers}, {
        "risks": [{"text": "The buyer release schedule is unspecified." if annual else "Required arrival date is unspecified.", "source_ids": ["buyer"]}],
        "recommendation": recommendations, "follow_up_questions": questions,
    }


class VariableSupplierCountTests(unittest.TestCase):
    def test_a_different_product_quantity_currency_and_order_basis_are_input_driven(self):
        text, extraction, analysis = variable_supplier_fixture(6, part="SEAL-920", quantity=1200, revision=None, currency="EUR", annual=False)
        client = Mock(complete=Mock(side_effect=[json.dumps(extraction), json.dumps(analysis)]))
        report = ProcurementAgent(client).review(text)
        payload = json.loads(client.complete.call_args_list[1].args[0][1]["content"])
        self.assertEqual(payload["extraction"]["buyer"]["quantity"]["value"], "1200")
        self.assertEqual(payload["extraction"]["buyer"]["quantity_basis"]["value"], "order")
        self.assertEqual(payload["calculations"][0]["quantity_price_extension"], "6012.00")
        self.assertTrue(all(item["revision_blocker"] is None for item in payload["calculations"]))
        self.assertIn("SEAL-920", report)
        self.assertIn("Rubber sealing ring", report)
        self.assertIn("EUR 6,012.00", report)
        for unrelated in ("BRK-4471-A", "60,000", "USD 5.01", "Drawing revision blocker", "Annual price extension"):
            self.assertNotIn(unrelated, report)
        follow_ups = report.split("## 4. Follow-up questions", 1)[1]
        self.assertIn("payment terms", follow_ups)
        self.assertNotIn("drawing revision", follow_ups)

    def test_one_five_six_and_twelve_replies_use_the_same_pipeline(self):
        for count in (1, 5, 6, 12):
            with self.subTest(count=count):
                text, extraction, analysis = variable_supplier_fixture(count)
                client = Mock(complete=Mock(side_effect=[json.dumps(extraction), json.dumps(analysis)]))
                report = ProcurementAgent(client).review(text)
                self.assertEqual(client.complete.call_count, 2)
                self.assertIn(f"Comparing {count} supplier replies", report)
                expected = {f"supplier_{i}" for i in range(1, count + 1)}
                request = json.loads(client.complete.call_args_list[1].args[0][1]["content"])
                self.assertEqual({item["source_id"] for item in request["extraction"]["suppliers"]}, expected)
                self.assertEqual(set(request["follow_up_context"]), {"buyer", *expected})
                for index in range(1, count + 1):
                    self.assertIn(f"| Variable Vendor {index} | **Shortlist / advance**", report)
                    self.assertIn(f"### Variable Vendor {index}\n", report)
                headers = [line for line in report.splitlines() if line.startswith("| Field |")]
                self.assertEqual(len(headers), (count + 3) // 4)
                self.assertTrue(all(line.count("Variable Vendor") <= 4 for line in headers))
                if count > 8:
                    self.assertGreater(client.complete.call_args_list[1].kwargs["max_tokens"], 6000)

    def test_recommendation_count_is_not_limited_to_forty(self):
        text, extraction, analysis = variable_supplier_fixture(41)
        sources = parse_packet(text).sources
        self.assertEqual(len(validate_extraction(extraction, sources)["suppliers"]), 41)
        result = validate_analysis(analysis, sources)
        self.assertEqual(len(result["recommendation"]), 41)
        self.assertEqual(len(result["follow_up_questions"]), 42)


class ReportWriteTests(unittest.TestCase):
    def test_atomic_write_does_not_clobber_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.md"
            output.write_text("previous")
            with self.assertRaises(FileExistsError):
                write_report(output, "new")
            self.assertEqual(output.read_text(), "previous")
            write_report(output, "new", overwrite=True)
            self.assertEqual(output.read_text(), "new")
            self.assertEqual(list(Path(directory).iterdir()), [output])


if __name__ == "__main__":
    unittest.main()
