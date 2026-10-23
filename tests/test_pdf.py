import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from procurement_agent.cli import main


class PdfExportTests(unittest.TestCase):
    @unittest.skipUnless(all(shutil.which(tool) for tool in ("pandoc", "xelatex", "pdftotext")),
                         "PDF integration requires Pandoc, XeLaTeX and pdftotext")
    def test_offline_pdf_preserves_report_sections_facts_and_additional_suppliers(self):
        markdown = """# Procurement report

## 1. Normalized supplier comparison

| Field | Supplier E | Supplier F |
| --- | --- | --- |
| Price | USD 4.85 (inferred currency) | EUR 3.92 (explicit currency) |
| Annual extension | USD 291,000.00 | EUR 235,200.00 |

### Source evidence

[^tier]: 60,000 pcs EUR 3.92 / pc

## 2. Risks / unknowns

Required drawing revision is unknown. The volume tier is quoted.[^tier]

## 3. Shortlist / recommendation

The annual amount uses the quoted tier.[^tier]

| Supplier | Action | Reason / next step |
| --- | --- | --- |
""" + "\n".join(f"| Supplier {letter} | Advance with clarification | Confirm currency. |"
                  for letter in "ABCDEF") + """

## 4. Follow-up questions

### Buyer

- Which drawing revision is required?

### Supplier F

- Can you confirm your pricing currency?
"""
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "report.md", Path(directory) / "report.pdf"
            source.write_text(markdown, encoding="utf-8")
            original = source.read_bytes()
            with patch("procurement_agent.cli.OpenRouterClient.from_env") as model, patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(["pdf", str(source), "-o", str(output)]), 0)
            model.assert_not_called()
            self.assertEqual(source.read_bytes(), original)
            text = subprocess.run(["pdftotext", "-layout", str(output), "-"],
                                  capture_output=True, text=True, check=True).stdout
            text = " ".join(text.split())
            for expected in ("1. Normalized supplier comparison", "2. Risks / unknowns",
                             "3. Shortlist / recommendation", "4. Follow-up questions",
                             "USD 4.85 (inferred currency)", "EUR 3.92 (explicit currency)",
                             "USD 291,000.00", "EUR 235,200.00", "60,000 pcs EUR 3.92 / pc",
                             "Required drawing revision is unknown.", "Source evidence",
                             "Which drawing revision is required?", "Can you confirm your pricing currency?",
                             *(f"Supplier {letter}" for letter in "ABCDEF")):
                self.assertIn(expected, text)
            self.assertEqual(text.count("60,000 pcs EUR 3.92 / pc"), 1)

            # Review exports the exact saved Markdown, including custom output names.
            packet, reviewed = Path(directory) / "quote_packet.txt", Path(directory) / "buyer.md"
            packet.write_text("Buyer requirements\n===PACKET===\nSupplier reply", encoding="utf-8")
            with patch("procurement_agent.cli.OpenRouterClient.from_env", return_value=Mock(model="test/model", timeout=1)), \
                 patch("procurement_agent.cli.ProcurementAgent") as agent, \
                 patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
                agent.return_value.review.return_value = markdown
                self.assertEqual(main(["review", str(packet), "-o", str(reviewed)]), 0)
            agent.return_value.review.assert_called_once_with(packet.read_text())
            self.assertEqual(reviewed.read_bytes(), original)
            reviewed_text = subprocess.run(["pdftotext", "-layout", str(reviewed.with_suffix(".pdf")), "-"],
                                           capture_output=True, text=True, check=True).stdout
            self.assertEqual(" ".join(reviewed_text.split()), text)

    def test_review_checks_both_output_paths_before_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            packet, output = Path(directory) / "quote_packet.txt", Path(directory) / "buyer.md"
            packet.write_text("Buyer requirements\n===PACKET===\nSupplier reply", encoding="utf-8")
            pdf = output.with_suffix(".pdf")
            pdf.write_text("Existing artifact", encoding="utf-8")
            with patch("procurement_agent.cli.OpenRouterClient.from_env") as model, patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(main(["review", str(packet), "-o", str(output)]), 1)
                self.assertEqual(main(["review", str(pdf), "-o", str(output), "--force"]), 1)
                self.assertEqual(main(["review", str(packet), "-o", str(pdf), "--force"]), 1)
            model.assert_not_called()
            self.assertFalse(output.exists())
            self.assertEqual(pdf.read_text(), "Existing artifact")

    def test_review_keeps_saved_markdown_if_pdf_export_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            packet, output = Path(directory) / "quote_packet.txt", Path(directory) / "buyer.md"
            packet.write_text("Buyer requirements\n===PACKET===\nSupplier reply", encoding="utf-8")
            output.write_text("Previous Markdown", encoding="utf-8")
            pdf = output.with_suffix(".pdf")
            pdf.write_bytes(b"previous PDF")
            with patch("procurement_agent.cli.OpenRouterClient.from_env", return_value=Mock(model="test/model", timeout=1)), \
                 patch("procurement_agent.cli.ProcurementAgent") as agent, \
                 patch("procurement_agent.tools.pdf.shutil.which", return_value=None), \
                 patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO) as stderr:
                agent.return_value.review.return_value = "# New validated report\n"
                self.assertEqual(main(["review", str(packet), "-o", str(output), "--force"]), 1)
            agent.return_value.review.assert_called_once_with(packet.read_text())
            self.assertEqual(output.read_text(), "# New validated report\n")
            self.assertEqual(pdf.read_bytes(), b"previous PDF")
            self.assertIn(f"Markdown saved to {output}", stderr.getvalue())
            self.assertIn("PDF export failed", stderr.getvalue())
            self.assertIn("Pandoc and XeLaTeX", stderr.getvalue())

    def test_existing_artifacts_survive_collisions_and_failed_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "report.md", Path(directory) / "report.pdf"
            source.write_text("# Original report", encoding="utf-8")
            output.write_bytes(b"previous PDF")
            with patch("procurement_agent.cli.OpenRouterClient.from_env") as model, patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(main(["pdf", str(source), "-o", str(source), "--force"]), 1)
                self.assertEqual(main(["pdf", str(source), "-o", str(output)]), 1)
                with patch("procurement_agent.tools.pdf.shutil.which", return_value="/fake/tool"), \
                     patch("procurement_agent.tools.pdf.subprocess.run", return_value=Mock(returncode=1, stderr="Typesetting failed")):
                    self.assertEqual(main(["pdf", str(source), "-o", str(output), "--force"]), 1)
            model.assert_not_called()
            self.assertEqual(source.read_text(), "# Original report")
            self.assertEqual(output.read_bytes(), b"previous PDF")

    def test_missing_pdf_dependencies_reports_setup_without_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "report.md", Path(directory) / "report.pdf"
            source.write_text("# Report", encoding="utf-8")
            with patch("procurement_agent.cli.OpenRouterClient.from_env") as model, \
                 patch("procurement_agent.tools.pdf.shutil.which", return_value=None), \
                 patch("sys.stderr", new_callable=io.StringIO) as stderr:
                self.assertEqual(main(["pdf", str(source), "-o", str(output)]), 1)
            model.assert_not_called()
            self.assertIn("Pandoc and XeLaTeX", stderr.getvalue())
            self.assertFalse(output.exists())
