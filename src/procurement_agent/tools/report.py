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
            if "." not in rendered:
                rendered += ".00"
            elif len(rendered.rsplit(".", 1)[1]) < 2:
                rendered += "0"
    return f"{_escape(currency or 'Currency unknown')} {rendered}"


def render_report(extraction: dict, calculations: list[dict], analysis: dict) -> str:
    suppliers = extraction["suppliers"]
    validation_warnings = extraction.get("validation_warnings", [])
    excluded = {(warning["source_id"], warning["field"]) for warning in validation_warnings}
    names = {"buyer": "Buyer"}
    names.update({item["source_id"]: item["supplier"]["value"] or item["source_id"] for item in suppliers})
    amounts = {item["source_id"]: item for item in calculations}
    evidence = {}

    def fact(source_id, field, value):
        if value["value"] is None:
            if (source_id, field) in excluded or (
                (source_id, "price") in excluded and field in {"quoted_price", "price_basis_quantity", "currency"}
            ):
                return "Unverified / excluded — see data-quality notes"
            return "Unknown / not stated"
        key = f"{source_id}-{field}"
        evidence[key] = value["evidence"]
        return f"{_escape(value['value'])}[^{key}]"

    lines = ["# Procurement report", ""]
    if validation_warnings:
        lines += ["**Data quality:** Some terms need confirmation. Unverified values are excluded "
                  "from affected totals; see the concise notes below.", ""]
    lines += ["## 1. Normalized supplier comparison", "", "### Buyer requirements", ""]
    for field, value in extraction["buyer"].items():
        lines.append(f"- **{field.replace('_', ' ').capitalize()}:** {fact('buyer', field, value)}")
    lines += [
        "", "### Supplier terms", "",
        "Price extensions are arithmetic scenarios, not confirmed ordering plans or landed costs. "
        "Unknown charges are not zero. No FX conversion, automatic discount, index adjustment, "
        "or tooling-amortization saving is applied. Contextual currency assumptions are labelled inferred and require confirmation.", "",
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
        cells = []
        for item in suppliers:
            source_id = item["source_id"]
            cell = fact(source_id, field, item[field])
            if field in {"currency", "tooling_currency"} and item[field]["value"] is not None:
                info = amounts[source_id]["currency_info" if field == "currency" else "tooling_currency_info"]
                quoted = f"; quoted {_escape(item[field]['value'])}" if info["status"] == "inferred" else ""
                cell = f"{_escape(info['code'])} ({info['status']}{quoted})[^{source_id}-{field}]"
            cells.append(cell)
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("| Currency basis | " + " | ".join(_escape(item["currency_info"]["note"]) for item in calculations) + " |")
    lines.append("| Delivery-cost coverage | " + " | ".join(_escape(item["cost_comparability_note"]) for item in calculations) + " |")
    annual = extraction["buyer"]["quantity_basis"]["value"] == "annual"
    computed = [
        ("Nominal unit price / piece (not landed cost)", "normalized_unit_price", 6),
        ("Annual price extension (conditional)" if annual else "Quantity price extension (conditional)", "quantity_price_extension", 2),
        ("Extension + one stated tooling charge (conditional)", "extension_plus_stated_tooling", 2),
    ]
    for label, field, places in computed:
        cells = []
        for result in calculations:
            info = result["currency_info"]
            cell = _money(result[field], info["code"], places)
            inferred = info["status"] == "inferred" or (
                field == "extension_plus_stated_tooling" and result["tooling_currency_info"]["status"] == "inferred"
            )
            if result[field] is not None and inferred:
                cell += " (inferred currency)"
            cells.append(cell)
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += [
        "", "Calculated rows use the cited original price, price basis, buyer quantity, and stated tooling. "
        "Deposits remain separate. Unit prices are displayed to at most six decimal places; "
        "extensions to two, using decimal half-even rounding. Approximate quotes remain indicative.",
        "", "### Source evidence", "",
    ]
    for key, excerpt in evidence.items():
        lines.append(f"[^{key}]: {_escape(excerpt)}")
    lines += ["", "## 2. Risks / unknowns", ""]
    for result in calculations:
        if result["revision_blocker"]:
            lines.append(f"- **Drawing revision blocker — {_escape(names[result['source_id']])}:** {_escape(result['revision_blocker'])}")
        if "excluded" in result["cost_comparability_note"]:
            lines.append(f"- **Cost comparison — {_escape(names[result['source_id']])}:** {_escape(result['cost_comparability_note'])}")

    def assessment(items):
        for item in items:
            refs = ", ".join(_escape(names[source_id]) for source_id in item["source_ids"])
            lines.append(f"- {_escape(item['text'])} (Sources: {refs})")

    assessment(analysis["risks"])
    if validation_warnings:
        lines += ["", "### Data-quality notes", ""]
        for source_id, name in names.items():
            fields = sorted({labels.get(warning["field"], warning["field"].replace("_", " "))
                             for warning in validation_warnings if warning["source_id"] == source_id})
            if fields:
                lines.append(f"- **{_escape(name)}:** Confirm {_escape(', '.join(fields))}. "
                             "These terms could not be verified from the reply; related totals may be unavailable. "
                             "This does not establish that the supplier omitted them.")
    lines += ["", "## 3. Shortlist / recommendation", "",
              "Advance means pursue clarification or a firm offer, not approve a purchase.", "",
              "| Supplier | Action | Reason / next step |", "| --- | --- | --- |"]
    decisions = {item["supplier_id"]: item for item in analysis["recommendation"]}
    action_labels = {"advance": "Shortlist / advance", "hold": "Hold / needs clarification", "do_not_advance": "Do not advance yet"}
    for supplier in suppliers:
        source_id = supplier["source_id"]
        decision = decisions[source_id]
        blocker = amounts[source_id]["revision_blocker"]
        action = "do_not_advance" if blocker else decision["action"]
        reason = blocker or decision["text"]
        lines.append(f"| {_escape(names[source_id])} | **{action_labels[action]}** | {_escape(reason)} |")
    lines += ["", "## 4. Follow-up questions", "", "Drafts only; no messages have been sent.", ""]
    for owner, name in names.items():
        lines += [f"### {_escape(name)}", ""]
        questions = [item for item in analysis["follow_up_questions"] if item["owner"] == owner]
        seen = set()
        for priority, label in (("blocking", "Resolve first"), ("important", "Commercial clarification"), ("optional", "Optional")):
            selected = []
            for item in questions:
                key = " ".join(item["text"].split()).casefold()
                if item["priority"] == priority and key not in seen:
                    selected.append(item)
                    seen.add(key)
            if selected:
                lines += [f"**{label}:**", ""]
                assessment(selected)
                lines.append("")
        if not questions:
            lines.append("No follow-up questions drafted for this party.")
        lines.append("")
    lines += [
        "Confirm assumptions, technical compliance and unresolved costs against the original quotes before a purchasing decision.", "",
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
