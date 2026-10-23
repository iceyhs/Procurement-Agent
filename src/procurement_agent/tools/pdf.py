"""Offline presentation export of the Markdown report; no procurement reasoning."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .report import check_output


# Pandoc's document tree is used only for layout: column widths and endnotes.
_LAYOUT = r'''
local notes = {}
local note_numbers = {}
local evidence_heading = nil

function Note(note)
  local key = pandoc.write(pandoc.Pandoc(note.content), "native")
  local number = note_numbers[key]
  if not number then
    number = tostring(#notes + 1)
    note_numbers[key] = number
    notes[#notes + 1] = {pandoc.Div(note.content, pandoc.Attr("source-" .. number))}
  end
  return pandoc.Superscript({pandoc.Link(number, "#source-" .. number)})
end

function Header(heading)
  if heading.identifier == "source-evidence" then
    evidence_heading = heading
    return {}
  end
end

function Table(tbl)
  local count = #tbl.colspecs
  local label = pandoc.utils.stringify(tbl.head.rows[1].cells[1].contents)
  local widths = nil
  if label == "Supplier" and count == 3 then
    widths = {0.18, 0.21, 0.61}
  elseif label:match("^Severity") and count == 4 then
    widths = {0.12, 0.18, 0.43, 0.27}
  elseif label == "Field" and count > 1 then
    widths = {0.18}
    for column = 2, count do widths[column] = 0.82 / (count - 1) end
  end
  if widths then
    for column = 1, count do tbl.colspecs[column][2] = widths[column] end
  end
  return {pandoc.RawBlock("latex", "\\begingroup\\small"), tbl,
          pandoc.RawBlock("latex", "\\endgroup")}
end

function Pandoc(doc)
  if #notes > 0 then
    doc.blocks:insert(pandoc.RawBlock("latex", "\\clearpage"))
    doc.blocks:insert(evidence_heading or pandoc.Header(3, "Source evidence"))
    doc.blocks:insert(pandoc.RawBlock("latex", "\\begingroup\\footnotesize\\begin{multicols}{2}"))
    doc.blocks:insert(pandoc.OrderedList(notes))
    doc.blocks:insert(pandoc.RawBlock("latex", "\\end{multicols}\\endgroup"))
  end
  return doc
end
'''

_HEADER = r'''
\usepackage{multicol}
\renewcommand{\familydefault}{\sfdefault}
\setlength{\emergencystretch}{3em}
\setlength{\columnsep}{8mm}
\setlength{\tabcolsep}{4pt}
\AtBeginDocument{\hypersetup{pdftitle={Procurement report},colorlinks=true,linkcolor=black,urlcolor=black}}
'''


def export_pdf(source: Path, output: Path, overwrite: bool = False):
    """Convert the saved Markdown artifact, publishing only a complete PDF."""
    check_output(output, source, overwrite)
    markdown = source.read_text(encoding="utf-8")
    pandoc, xelatex = shutil.which("pandoc"), shutil.which("xelatex")
    if not pandoc or not xelatex:
        raise ValueError("PDF export requires Pandoc and XeLaTeX. See README.md for setup.")
    with tempfile.TemporaryDirectory(prefix=".report-pdf-", dir=output.parent) as directory:
        temporary = Path(directory)
        layout, header, pdf = temporary / "layout.lua", temporary / "header.tex", temporary / "report.pdf"
        layout.write_text(_LAYOUT, encoding="utf-8")
        header.write_text(_HEADER, encoding="utf-8")
        command = [pandoc, "--from=markdown+pipe_tables+footnotes-raw_html-raw_tex", f"--pdf-engine={xelatex}",
                   f"--lua-filter={layout.resolve()}", f"--include-in-header={header.resolve()}",
                   "--variable=papersize:a4", "--variable=geometry:landscape,margin=14mm",
                   "--variable=fontsize:10pt", f"--output={pdf.resolve()}"]
        try:
            result = subprocess.run(command, input=markdown, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("PDF export timed out; the previous PDF was preserved.") from exc
        if result.returncode:
            raise ValueError(f"PDF export failed: {result.stderr[-1500:].strip()}")
        if not pdf.is_file() or pdf.read_bytes()[:5] != b"%PDF-":
            raise ValueError("PDF export did not produce a valid PDF; the previous PDF was preserved.")
        if overwrite:
            os.replace(pdf, output)
        else:
            os.link(pdf, output)
