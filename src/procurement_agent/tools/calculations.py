"""Narrow, deterministic calculations. No model calls, FX, or landed-cost guesses."""

from decimal import Decimal, localcontext
import re


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
    for peer in extraction["suppliers"]:
        if peer["source_id"] == supplier["source_id"]:
            continue
        if supplier["part"]["value"] and peer["part"]["value"] and supplier["part"]["value"] != peer["part"]["value"]:
            continue
        other = _revision(peer["revision"]["value"])
        if other is None or other == quoted:
            continue
        comparable = quoted.isdigit() == other.isdigit()
        later = (int(other) > int(quoted)) if other.isdigit() and quoted.isdigit() else other > quoted
        if not comparable or later:
            return (
                f"Quoted Rev {quoted} conflicts with Rev {other} referenced in another reply. "
                "The buyer's required revision is unknown. Do not advance until the buyer confirms "
                "the current revision and the supplier confirms compliance or re-quotes."
            )
    return None


def _buyer_notes(supplier, extraction, currency):
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
    blocker = _revision_blocker(supplier, extraction)
    questions = []
    if blocker:
        questions.append("Can you re-quote against the buyer-confirmed current drawing revision, or confirm your quoted revision is the required one?")
    elif supplier["revision"]["value"] is None:
        questions.append("Which drawing revision is this quote based on, and can you confirm compliance with the buyer's required revision?")
    if excluded or fob:
        questions.append("What freight and duty charges should be expected to the buyer destination? Please provide delivered pricing once the destination is confirmed.")
        if re.search(r"\b(?:ocean|production|shipping)\b", text("lead_time"), re.IGNORECASE):
            questions.append("Does the quoted lead time include full end-to-end transit, customs clearance where applicable, and final delivery? Please confirm the complete delivered lead time.")
        else:
            questions.append("What is the complete lead time from release through arrival at the buyer destination?")
    if supplier["tooling_amount"]["value"] is None and not re.search(r"\bincluded\b", text("tooling_terms"), re.IGNORECASE):
        questions.append("Please confirm the tooling cost and whether it is a one-time charge.")
    if currency["status"] != "explicit":
        questions.append("Please confirm the pricing currency explicitly for unit prices and tooling; any USD interpretation is currently an assumption.")
    return {"revision_blocker": blocker, "cost_comparability_note": cost_note, "priority_questions": questions}


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
            **_buyer_notes(supplier, extraction, currency),
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
