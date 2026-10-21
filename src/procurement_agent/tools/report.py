"""Render four sections and write atomically; never let model text control files."""

import html
import os
import tempfile
from decimal import Decimal, localcontext
from pathlib import Path


def _escape(value) -> str:
    text = html.escape(" ".join(str(value).split()), quote=False)
    for character in ("\\", "|", "`", "*", "_", "[", "]", "#"):
        text = text.replace(character, "\\" + character)
    return text


def _money(amount, currency, places=2):
    if amount is None:
        return "Unknown / not calculated"
    with localcontext() as context:
        context.prec = 60
        number = Decimal(amount).quantize(Decimal(1).scaleb(-places))
        rendered = f"{number:,.{places}f}"
        if places > 2:
            rendered = rendered.rstrip("0").rstrip(".")
    return f"{_escape(currency or 'Currency unknown')} {rendered}"


def render_report(extraction: dict, calculations: list[dict], analysis: dict) -> str:
    suppliers = extraction["suppliers"]
    validation_warnings = extraction.get("validation_warnings", [])
    excluded = {(warning["source_id"], warning["field"]) for warning in validation_warnings}
    names = {"buyer": "Buyer"}
    names.update({item["source_id"]: item["supplier"]["value"] or item["source_id"] for item in suppliers})
    evidence = {}

    def fact(source_id, field, value):
        if value["value"] is None:
            if (source_id, field) in excluded or (
                (source_id, "price") in excluded and field in {"quoted_price", "price_basis_quantity", "currency"}
            ):
                return "Unverified / excluded — see warnings"
            return "Unknown / not stated"
        key = f"{source_id}-{field}"
        evidence[key] = value["evidence"]
        return f"{_escape(value['value'])}[^{key}]"

    lines = ["# Procurement report", ""]
    if validation_warnings:
        lines += ["**Incomplete evidence validation:** unverified fields were excluded and marked unknown. "
                  "Affected calculations are withheld. Review the validation warnings before relying on the shortlist.", ""]
    lines += ["## 1. Normalized supplier comparison", "", "### Buyer requirements", ""]
    for field, value in extraction["buyer"].items():
        lines.append(f"- **{field.replace('_', ' ').capitalize()}:** {fact('buyer', field, value)}")
    lines += [
        "", "### Supplier terms", "",
        "Price extensions are arithmetic scenarios, not confirmed ordering plans or landed costs. "
        "Unknown charges are not zero. No FX conversion, automatic discount, index adjustment, "
        "or tooling-amortization saving is applied. Bare $ does not establish a dollar currency code.", "",
        "| Field | " + " | ".join(_escape(names[item["source_id"]]) for item in suppliers) + " |",
        "| --- | " + " | ".join("---" for _ in suppliers) + " |",
    ]
    labels = {
        "supplier": "Supplier / source", "part": "Part", "revision": "Drawing revision",
        "material_finish": "Material / finish statements", "quoted_price": "Original quoted price",
        "price_basis_quantity": "Pieces per quoted price", "currency": "Price currency",
        "price_qualification": "Price qualifications", "annual_volume": "Selected annual volume tier",
        "moq": "MOQ", "min_release": "Minimum release", "tooling_amount": "Stated tooling amount",
        "tooling_currency": "Tooling currency", "tooling_terms": "Tooling terms",
        "deposit_amount": "Container / packaging deposit", "deposit_currency": "Deposit currency",
        "deposit_terms": "Deposit conditions", "delivery_terms": "Delivery / cost coverage",
        "lead_time": "Lead time / starting condition", "payment_terms": "Payment",
        "validity": "Price validity", "price_adjustment": "Price adjustment", "other_terms": "Other terms",
    }
    for field, label in labels.items():
        cells = [fact(item["source_id"], field, item[field]) for item in suppliers]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    annual = extraction["buyer"]["quantity_basis"]["value"] == "annual"
    computed = [
        ("Normalized price / piece (calculated)", "normalized_unit_price", 6),
        ("Annual price extension (conditional)" if annual else "Quantity price extension (conditional)", "quantity_price_extension", 2),
        ("Extension + stated tooling only (conditional)", "extension_plus_stated_tooling", 2),
    ]
    for label, field, places in computed:
        cells = [_money(result[field], result["currency"], places) for result in calculations]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += [
        "", "Calculated rows use the cited original price, price basis, buyer quantity, and stated tooling. "
        "Deposits remain separate. Unit prices are displayed to at most six decimal places; "
        "extensions to two, using decimal half-even rounding. Approximate quotes remain indicative.",
        "", "### Source evidence", "",
    ]
    for key, excerpt in evidence.items():
        lines.append(f"[^{key}]: {_escape(excerpt)}")
    lines += ["", "## 2. Risks / unknowns", "", "### Harness checks", ""]
    for warning in validation_warnings:
        lines.append(f"- **Excluded {_escape(warning['source_id'])}.{_escape(warning['field'])}:** {_escape(warning['reason'])}")
    for result in calculations:
        for warning in result["warnings"]:
            lines.append(f"- **{_escape(names[result['source_id']])}:** {_escape(warning)}")
    lines += ["", "### Model assessment", ""]

    def assessment(items):
        for item in items:
            refs = ", ".join(_escape(names[source_id]) for source_id in item["source_ids"])
            lines.append(f"- {_escape(item['text'])} (Sources: {refs})")

    assessment(analysis["risks"])
    lines += ["", "## 3. Shortlist / recommendation", ""]
    assessment(analysis["recommendation"])
    lines += ["", "## 4. Follow-up questions", "", "Drafts only; no messages have been sent.", ""]
    for owner, name in names.items():
        lines += [f"### {_escape(name)}", ""]
        assessment([item for item in analysis["follow_up_questions"] if item["owner"] == owner])
        lines.append("")
    lines += [
        "Evidence matching checks excerpt presence, not interpretation or technical compliance. "
        "Review the original quotes before a purchasing decision.", "",
    ]
    return "\n".join(lines)


def check_output(path: Path, input_path: Path, overwrite: bool = False):
    if path.resolve() == input_path.resolve():
        raise ValueError("Report output must differ from the input file.")
    if not path.parent.is_dir():
        raise ValueError("Report output directory does not exist.")
    if path.exists() and (not overwrite or not path.is_file()):
        raise ValueError("Report output already exists; choose another path or use --force for a file.")


def write_report(path: Path, text: str, overwrite: bool = False):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        if overwrite:
            os.replace(temporary, path)
        else:
            # Atomic creation without clobbering a file created during model calls.
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
