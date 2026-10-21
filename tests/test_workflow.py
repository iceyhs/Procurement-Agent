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
    BUYER_FIELDS, SUPPLIER_FIELDS, ValidationError, load_response, validate_analysis,
    validate_extraction,
)
from procurement_agent.tools.calculations import calculate_amounts
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


def analysis_example():
    return {
        "risks": [
            {"text": "Required revision, finish, destination, release schedule and required delivery date are missing.", "source_ids": ["buyer"]},
            {"text": "Quoted revisions differ; confirm the required revision before treating offers as equivalent.", "source_ids": ["supplier_2", "supplier_3", "buyer"]},
            {"text": "The container deposit is refundable cash exposure, not permanent cost. Clarify amortization and index adjustments.", "source_ids": ["supplier_2"]},
            {"text": "Approximate pricing, unconfirmed tooling and steady-state lead time prevent a firm comparison.", "source_ids": ["supplier_4"]},
        ],
        "recommendation": [
            {"text": "Conditionally pursue Tri-State for its quoted release lead time and Nordkant for its stated delivery coverage; confirm technical fit and buyer priorities. Partial totals do not establish a cheapest landed supplier.", "source_ids": ["buyer", "supplier_1", "supplier_2"]},
        ],
        "follow_up_questions": [
            {"owner": "buyer", "text": "What revision, finish, destination, release schedule and delivery date are required, and how should cost versus responsiveness be prioritized?", "source_ids": ["buyer"]},
            {"owner": "supplier_1", "text": "Please confirm currency, required-revision compliance, finish inclusion, delivered freight and price for the planned release schedule.", "source_ids": ["supplier_1"]},
            {"owner": "supplier_2", "text": "Please explain post-amortization pricing, the index adjustment formula, deposit recovery and quote issue date.", "source_ids": ["supplier_2"]},
            {"owner": "supplier_3", "text": "Can you quote the required revision and delivered costs, and confirm MOQ flexibility and full delivery timing?", "source_ids": ["supplier_3", "buyer"]},
            {"owner": "supplier_4", "text": "Please provide firm pricing and currency, tooling, payment terms, startup timing and safety-stock replenishment and ownership terms.", "source_ids": ["supplier_4"]},
        ],
    }


class PacketTests(unittest.TestCase):
    def test_raw_text_and_both_separator_spacings(self):
        packet = parse_packet("\ufeffBRK-4471-A\n60,000 units\r\n===PACKET===\r\nEmail reply\n=== PACKET ===\nChat reply")
        self.assertEqual(packet.buyer, "BRK-4471-A\n60,000 units")
        self.assertEqual(packet.sources["supplier_2"], "Chat reply")

    def test_reject_empty_missing_separator_empty_blocks_and_excess(self):
        for text in ("", "No replies", "===PACKET===\nReply", "Buyer\n===PACKET===", "Buyer\n" + "===PACKET===\nReply\n" * 9):
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

    def test_reject_number_without_supporting_evidence(self):
        self.data["suppliers"][2]["quoted_price"]["value"] = "3.24"
        with self.assertRaisesRegex(ValidationError, "numeric value"):
            validate_extraction(self.data, self.sources)

    def test_reject_inferred_dollar_currency(self):
        self.data["suppliers"][0]["currency"]["value"] = "USD"
        with self.assertRaisesRegex(ValidationError, "currency must be explicit"):
            validate_extraction(self.data, self.sources)

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


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.packet = EXAMPLE.read_text()
        self.extraction = extracted_example()
        self.analysis = analysis_example()

    def client(self, *responses):
        return Mock(model="test/model", timeout=60, complete=Mock(side_effect=list(responses)))

    def test_full_two_call_workflow_and_four_sections(self):
        client = self.client(json.dumps(self.extraction), json.dumps(self.analysis))
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

    def test_one_correction_then_success(self):
        client = self.client("invalid json", json.dumps(self.extraction), json.dumps(self.analysis))
        ProcurementAgent(client).review(self.packet)
        self.assertEqual(client.complete.call_count, 3)
        self.assertIn("failed validation", client.complete.call_args_list[1].args[0][-1]["content"])
        self.assertEqual(client.complete.call_args_list[1].args[0][-2], {"role": "assistant", "content": "invalid json"})

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
        self.assertIn("copied verbatim", correction[-1]["content"])

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

    def test_reject_unknown_analysis_sources_and_missing_question_owner(self):
        self.analysis["risks"][0]["source_ids"] = ["unknown"]
        with self.assertRaises(ValidationError):
            validate_analysis(self.analysis, parse_packet(self.packet).sources)
        self.analysis = analysis_example()
        self.analysis["follow_up_questions"].pop()
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

        send.side_effect = [response_for(self.extraction), response_for(self.analysis)]
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
            output = Path(directory) / "report.md"
            self.assertEqual(main(["review", str(EXAMPLE), "--output", str(output)]), 0)
            self.assertIn("## 4. Follow-up questions", output.read_text())
            self.assertEqual(send.call_count, 2)
            for call in send.call_args_list:
                request = json.loads(call.args[0].data)
                self.assertEqual(request["model"], "test/model")
                self.assertNotIn("tools", request)

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
