"""Narrow, deterministic calculations. No model calls, FX, or landed-cost guesses."""

from decimal import Decimal, localcontext


def calculate_amounts(extraction: dict) -> list[dict]:
    buyer = extraction["buyer"]
    quantity = buyer["quantity"]["value"]
    quantity_basis = buyer["quantity_basis"]["value"]
    results = []
    for supplier in extraction["suppliers"]:
        excluded_fields = {warning["field"] for warning in extraction.get("validation_warnings", [])
                           if warning["source_id"] == supplier["source_id"]}
        value = lambda field: supplier[field]["value"]
        result = {
            "calculation_id": f"calc_{supplier['source_id']}",
            "source_id": supplier["source_id"],
            "currency": value("currency"),
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
        if value("currency") == "$":
            warnings.append("Dollar currency is unspecified; confirm the currency code.")
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
                    if tooling is not None and value("tooling_currency") == value("currency") and not excluded_fields & {"tooling_amount", "tooling_currency", "tooling_terms"}:
                        result["extension_plus_stated_tooling"] = format(extension + Decimal(tooling), "f")
                        warnings.append("Extension plus tooling assumes one additional tooling charge in this scenario; confirm applicability.")
        if result["quantity_price_extension"] is None:
            warnings.append("No supported quantity price extension is available.")
        results.append(result)
    return results
