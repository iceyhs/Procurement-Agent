"""Narrow, deterministic calculations. No model calls, FX, or landed-cost guesses."""

from decimal import Decimal, localcontext
import re

from .issues import issue_candidates


def _currency_info(raw, extraction):
    if raw is None:
        return {"code": None, "status": "unknown", "note": "Currency not stated or not verified."}
    if raw != "$":
        return {"code": raw, "status": "explicit", "note": "Explicitly stated in the quote."}
    currencies = {item["currency"]["value"] for item in extraction["suppliers"]}
    conflicting = currencies & {"CAD", "AUD", "NZD", "SGD", "HKD", "TWD", "MXN", "ARS", "CLP", "COP", "UYU"}
    if "USD" in currencies and not conflicting:
        return {
            "code": "USD", "status": "inferred",
            "note": "USD inferred from the bare $ symbol and explicit USD pricing in this RFQ; supplier confirmation required.",
        }
    return {"code": "$", "status": "unresolved", "note": "Dollar currency unconfirmed; context does not establish a currency code."}


def _revision(value):
    match = re.fullmatch(r"(?:rev(?:ision)?\.?\s*)?([A-Za-z]|[0-9]+)", value or "", re.IGNORECASE)
    return match[1].upper() if match else None


def _revision_blocker(supplier, extraction):
    quoted = _revision(supplier["revision"]["value"])
    required = _revision(extraction["buyer"]["revision"]["value"])
    if quoted is None:
        return None
    if required is not None:
        if quoted != required:
            return f"Quoted Rev {quoted} differs from buyer-required Rev {required}. Do not advance until confirmed compliant or re-quoted."
        return None
    return None


def _revision_comparability_gap(supplier, extraction):
    quoted = _revision(supplier["revision"]["value"])
    if quoted is None or extraction["buyer"]["revision"]["value"] is not None:
        return None
    for peer in extraction["suppliers"]:
        if peer["source_id"] == supplier["source_id"]:
            continue
        if supplier["part"]["value"] and peer["part"]["value"] and supplier["part"]["value"] != peer["part"]["value"]:
            continue
        other = _revision(peer["revision"]["value"])
        if other is None or other == quoted:
            continue
        name = supplier["supplier"]["value"] or supplier["source_id"]
        peer_name = peer["supplier"]["value"] or peer["source_id"]
        return (
            f"{name} quotes Rev {quoted}; {peer_name} references Rev {other}. "
            "The buyer's required revision is unknown. Technical equivalence is unconfirmed pending "
            "buyer confirmation; neither supplier's quoted revision establishes the requirement."
        )
    return None


def _buyer_notes(supplier, extraction):
    def text(*fields):
        return " ".join(str(supplier[field][key] or "") for field in fields for key in ("value", "evidence"))

    delivery = text("delivery_terms", "other_terms")
    excluded = bool(re.search(r"freight.{0,25}dut(?:y|ies).{0,25}(?:not included|excluded)", delivery, re.IGNORECASE))
    fob = bool(re.search(r"\bFOB\b", delivery, re.IGNORECASE))
    if excluded:
        cost_note = "Nominal unit price only: freight and duty excluded. No confirmed landed-cost advantage over delivered offers."
    elif re.search(r"\bDDP\b", delivery, re.IGNORECASE):
        cost_note = "DDP to the quoted location; confirm that it matches the buyer destination. No cross-currency landed-cost ranking."
    elif re.search(r"\bEXW\b", delivery, re.IGNORECASE):
        cost_note = "Nominal ex-works price; transport and import costs are not established."
    elif fob:
        cost_note = "Nominal FOB price; full delivered cost is not established. Confirm freight and duty coverage."
    else:
        cost_note = "Delivery-cost coverage unknown; no confirmed landed-cost comparison."
    return {"revision_blocker": _revision_blocker(supplier, extraction),
            "revision_comparability_gap": _revision_comparability_gap(supplier, extraction),
            "cost_comparability_note": cost_note}


def follow_up_context(extraction: dict, calculations: list[dict]) -> dict:
    """Issue metadata for model-authored questions; contains no question templates."""
    records = {"buyer": extraction["buyer"], **{item["source_id"]: item for item in extraction["suppliers"]}}
    context = {}
    for owner, record in records.items():
        context[owner] = {
            "missing_fields": [field for field, fact in record.items() if field != "source_id" and fact["value"] is None],
            "uncertain_fields": [],
            "validation_fields": [item["field"] for item in extraction.get("validation_warnings", []) if item["source_id"] == owner],
            "detected_risks": [],
            "comparability_gaps": [],
        }
    buyer = extraction["buyer"]
    suppliers = extraction["suppliers"]

    def buyer_blocker(field, detail, related):
        context["buyer"]["detected_risks"].append({
            "field": field, "blocking": True, "resolution_owner": "buyer",
            "blocks": "final_comparison", "blocks_shortlisting": False,
            "detail": detail, "source_ids": ["buyer", *related],
        })

    quoted_revisions = [item for item in suppliers if item["revision"]["value"] is not None]
    if buyer["revision"]["value"] is None and quoted_revisions:
        references = "; ".join(
            f"{item['supplier']['value'] or item['source_id']} references drawing revision "
            f"{_revision(item['revision']['value']) or item['revision']['value']}"
            for item in quoted_revisions
        )
        buyer_blocker("revision", references + ". The buyer's required drawing revision is not provided; confirm it before assessing compliance.",
                      [item["source_id"] for item in quoted_revisions])
    delivery_quotes = [item for item in suppliers if item["delivery_terms"]["value"] is not None]
    if buyer["destination"]["value"] is None and delivery_quotes:
        buyer_blocker("destination", "Buyer destination is missing. Supplier delivery locations are quote terms, not buyer requirements; delivered-cost comparison needs the actual destination.",
                      [item["source_id"] for item in delivery_quotes])
    quantity_conditions = [item for item in suppliers if any(item[field]["value"] is not None for field in ("moq", "min_release", "annual_volume"))]
    if buyer["release_schedule"]["value"] is None and (buyer["quantity_basis"]["value"] == "annual" or quantity_conditions):
        buyer_blocker("release_schedule", "Buyer release schedule is missing. Annual demand does not establish order sizes or release frequency; quoted volume and minimum-quantity conditions cannot yet be checked against the purchasing plan.",
                      [item["source_id"] for item in quantity_conditions])
    for calculation in calculations:
        owner = calculation["source_id"]
        issue = context[owner]
        if calculation["currency_info"]["status"] != "explicit":
            issue["uncertain_fields"].append("currency")
        if calculation["tooling_amount"] is not None and calculation["tooling_currency_info"]["status"] != "explicit":
            issue["uncertain_fields"].append("tooling_currency")
        if calculation["revision_blocker"]:
            issue["detected_risks"].append({"field": "revision", "blocking": True,
                                           "blocks": "supplier_advancement", "resolution_owner": owner,
                                           "detail": calculation["revision_blocker"]})
        if calculation["revision_comparability_gap"]:
            issue["detected_risks"].append({"field": "revision", "blocking": True,
                                           "blocks": "technical_comparison", "resolution_owner": "buyer",
                                           "detail": calculation["revision_comparability_gap"]})
        qualification = records[owner]["price_qualification"]["value"]
        if qualification and re.search(r"around|approx|indicative|estimat|subject to|pending|confirm|provisional", qualification, re.IGNORECASE):
            issue["uncertain_fields"].append("price_qualification")
        issue["comparability_gaps"].append(calculation["cost_comparability_note"])
        if calculation["quantity_price_extension"] is None:
            issue["comparability_gaps"].append("No supported quantity price extension; quantity, price basis or conditions need clarification.")
    candidates = issue_candidates(extraction, calculations, context)
    for owner, issues in candidates.items():
        context[owner]["issues"] = issues
    return context


def calculate_amounts(extraction: dict) -> list[dict]:
    buyer = extraction["buyer"]
    quantity = buyer["quantity"]["value"]
    quantity_basis = buyer["quantity_basis"]["value"]
    results = []
    for supplier in extraction["suppliers"]:
        excluded_fields = {warning["field"] for warning in extraction.get("validation_warnings", [])
                           if warning["source_id"] == supplier["source_id"]}
        value = lambda field: supplier[field]["value"]
        currency = _currency_info(value("currency"), extraction)
        tooling_currency = _currency_info(value("tooling_currency"), extraction)
        result = {
            "calculation_id": f"calc_{supplier['source_id']}",
            "source_id": supplier["source_id"],
            "currency": value("currency"),
            "currency_info": currency,
            "tooling_currency_info": tooling_currency,
            **_buyer_notes(supplier, extraction),
            "quantity": quantity,
            "quantity_basis": quantity_basis,
            "normalized_unit_price": None,
            "quantity_price_extension": None,
            "extension_plus_stated_tooling": None,
            "tooling_amount": value("tooling_amount"),
            "tooling_currency": value("tooling_currency"),
            "refundable_deposit": value("deposit_amount"),
            "deposit_currency": value("deposit_currency"),
            "excluded_or_unknown_costs": [
                "No complete landed-cost calculation; unquoted costs remain unknown.",
                "Refundable deposits, payment discounts, and index adjustments are excluded from totals.",
            ],
            "warnings": [],
        }
        warnings = result["warnings"]
        if currency["status"] != "explicit":
            warnings.append(currency["note"])
        if value("tooling_amount") is None:
            warnings.append("No separate numeric tooling charge established; see tooling terms.")
        if value("min_release"):
            warnings.append(f"Price requires releases of at least {value('min_release')} pieces; confirm release schedule.")
        if value("moq"):
            warnings.append(f"MOQ is {value('moq')} pieces; annual demand alone does not establish compliant orders.")
        if quantity_basis != "annual":
            warnings.append("Buyer quantity is not explicitly annual; do not label this an annual total.")
        tier_ok = True
        if value("annual_volume") is not None:
            tier_ok = quantity_basis == "annual" and quantity is not None and Decimal(quantity) == Decimal(value("annual_volume"))
            if not tier_ok:
                warnings.append("Selected annual price tier does not match explicit annual demand; extension withheld.")
        if excluded_fields & {"annual_volume", "price_qualification", "moq", "min_release", "other_terms"}:
            tier_ok = False
            warnings.append("Price extension withheld because extracted pricing or quantity conditions could not be verified.")
        price, basis = value("quoted_price"), value("price_basis_quantity")
        if price is not None and basis is not None:
            with localcontext() as context:
                context.prec = 50
                # Extend using the original ratio, avoiding intermediate money rounding.
                result["normalized_unit_price"] = format(Decimal(price) / Decimal(basis), "f")
                if quantity is not None and tier_ok:
                    extension = Decimal(price) * Decimal(quantity) / Decimal(basis)
                    result["quantity_price_extension"] = format(extension, "f")
                    tooling = value("tooling_amount")
                    if tooling is not None and currency["code"] is not None and tooling_currency["code"] == currency["code"] and not excluded_fields & {"tooling_amount", "tooling_currency", "tooling_terms"}:
                        result["extension_plus_stated_tooling"] = format(extension + Decimal(tooling), "f")
                        warnings.append("Extension plus tooling assumes one additional tooling charge in this scenario; confirm applicability.")
        if result["quantity_price_extension"] is None:
            warnings.append("No supported quantity price extension is available.")
        results.append(result)
    return results
