"""Dependency-free contracts for model responses and evidence validation.

Evidence matching establishes traceability, not semantic correctness.
"""

import json
import re
from decimal import Decimal

BUYER_FIELDS = (
    "part", "description", "quantity", "quantity_basis", "revision",
    "material_finish", "destination", "release_schedule", "required_delivery", "priorities",
)
SUPPLIER_FIELDS = (
    "supplier", "part", "revision", "material_finish", "quoted_price",
    "price_basis_quantity", "currency", "price_qualification", "annual_volume",
    "moq", "min_release", "tooling_amount", "tooling_currency", "tooling_terms", "deposit_amount",
    "deposit_currency", "deposit_terms", "delivery_terms", "lead_time", "payment_terms", "validity",
    "price_adjustment", "other_terms",
)
NUMERIC_FIELDS = {
    "quantity", "quoted_price", "price_basis_quantity", "annual_volume", "moq",
    "min_release", "tooling_amount", "deposit_amount",
}
INTEGER_FIELDS = {"quantity", "price_basis_quantity", "annual_volume", "moq", "min_release"}
MAX_RESPONSE_CHARS = 150_000


class ValidationError(ValueError):
    """A safe, bounded description of an invalid model response."""


def _fail(message: str):
    raise ValidationError(message)


def _keys(value, expected, location):
    if not isinstance(value, dict) or set(value) != set(expected):
        _fail(f"{location}: expected exactly the documented fields.")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON contains duplicate keys.")
        result[key] = value
    return result


def load_response(text: str) -> dict:
    if not isinstance(text, str) or len(text) > MAX_RESPONSE_CHARS:
        _fail("Model response is missing or too large.")
    text = text.strip()
    if text.startswith("```json\n") and text.endswith("```"):
        text = text[8:-3].strip()
    try:
        result = json.loads(
            text, object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("Non-finite JSON values are not allowed."),
        )
    except (json.JSONDecodeError, RecursionError):
        _fail("Model response must be a JSON object, without surrounding prose.")
    if not isinstance(result, dict):
        _fail("Model response must be a JSON object.")
    return result


def _normalize(text):
    return " ".join(text.split())


def _evidence_numbers(text):
    for number, suffix in re.findall(
        r"(?<![\w.])([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*([kK]?)(?!\w)", text
    ):
        yield Decimal(number.replace(",", "")) * (1000 if suffix else 1)


def _fact(value, field, source, location):
    _keys(value, ("value", "evidence"), location)
    data, evidence = value["value"], value["evidence"]
    if data is None and evidence is None:
        return
    if not isinstance(data, str) or not data.strip() or len(data) > 2000:
        _fail(f"{location}: value must be a nonempty string or null.")
    if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 2000:
        _fail(f"{location}: known values require a short evidence excerpt.")
    if _normalize(evidence) not in _normalize(source):
        # Part identifiers can be cited directly, even if the model added a
        # nonexistent label to its excerpt. This never searches another source
        # or accepts an identifier missing from the supplier's original text.
        match = None
        if field == "part" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{3,99}", data):
            match = re.search(r"(?<![\w-])" + re.escape(data) + r"(?![\w-])", source)
        if match is None:
            _fail(f"{location}: evidence must occur in this source; copy an exact excerpt without added labels.")
        value["evidence"] = match.group()
    if field in NUMERIC_FIELDS:
        if not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,6})?", data):
            _fail(f"{location}: use an unsigned decimal string without currency or commas.")
        amount = Decimal(data)
        if field in INTEGER_FIELDS and (amount <= 0 or amount != amount.to_integral_value()):
            _fail(f"{location}: quantity must be a positive integer.")
        implicit_piece = field == "price_basis_quantity" and amount == 1 and re.search(
            r"(?:per\s+(?:piece|pc|unit)|/\s*(?:piece|pc|unit)|a\s+piece|each)",
            evidence, re.IGNORECASE,
        )
        if not implicit_piece and amount not in _evidence_numbers(evidence):
            _fail(f"{location}: numeric value must appear in its evidence.")
    if field == "quantity_basis" and data not in {"annual", "order", "unspecified"}:
        _fail(f"{location}: expected annual, order, or unspecified.")
    if field in {"currency", "tooling_currency", "deposit_currency"}:
        if not re.fullmatch(r"[A-Z]{3}|\$", data):
            _fail(f"{location}: expected a three-letter currency or ambiguous '$'.")
        markers = {"USD": ("USD", "US$"), "EUR": ("EUR", "€"), "GBP": ("GBP", "£")}
        if not any(marker in evidence for marker in markers.get(data, (data,))):
            _fail(f"{location}: currency must be explicit; bare '$' does not establish USD.")


def validate_extraction(data: dict, sources: dict[str, str]) -> dict:
    _keys(data, ("buyer", "suppliers"), "extraction")
    _keys(data["buyer"], BUYER_FIELDS, "buyer")
    errors = []

    def check_fact(value, field, source, location):
        try:
            _fact(value, field, source, location)
            return True
        except ValidationError as error:
            errors.append(str(error))
            return False

    for field in BUYER_FIELDS:
        check_fact(data["buyer"][field], field, sources["buyer"], f"buyer.{field}")
    suppliers = data["suppliers"]
    expected_ids = set(sources) - {"buyer"}
    if not isinstance(suppliers, list) or len(suppliers) != len(expected_ids):
        _fail("Include exactly one extraction per supplier source.")
    seen = set()
    for item in suppliers:
        _keys(item, ("source_id", *SUPPLIER_FIELDS), "supplier")
        source_id = item["source_id"]
        if not isinstance(source_id, str) or source_id not in expected_ids or source_id in seen:
            _fail("Supplier source IDs must be known and unique.")
        seen.add(source_id)
        valid = [check_fact(item[field], field, sources[source_id], f"{source_id}.{field}")
                 for field in SUPPLIER_FIELDS]
        if all(valid):
            known = [item[field]["value"] is not None for field in ("quoted_price", "price_basis_quantity", "currency")]
            if any(known) and not all(known):
                errors.append(f"{source_id}: price, price basis, and currency must be known together or all null.")
    if errors:
        _fail("Extraction validation failed: " + "; ".join(errors[:12]))
    data["suppliers"].sort(key=lambda item: int(item["source_id"].split("_")[1]))
    return data


def validate_analysis(data: dict, sources: dict[str, str]) -> dict:
    _keys(data, ("risks", "recommendation", "follow_up_questions"), "analysis")
    for section in ("risks", "recommendation", "follow_up_questions"):
        items = data[section]
        if not isinstance(items, list) or not 1 <= len(items) <= 40:
            _fail(f"{section}: expected 1 to 40 items.")
        for item in items:
            fields = ("text", "source_ids", "owner") if section == "follow_up_questions" else ("text", "source_ids")
            _keys(item, fields, section)
            if not isinstance(item["text"], str) or not item["text"].strip() or len(item["text"]) > 2000:
                _fail(f"{section}: text must be a nonempty, bounded string.")
            refs = item["source_ids"]
            if not isinstance(refs, list) or not refs or len(refs) > len(sources):
                _fail(f"{section}: source_ids must reference input sources.")
            if any(not isinstance(ref, str) or ref not in sources for ref in refs):
                _fail(f"{section}: unknown source reference.")
            if section == "follow_up_questions":
                if not isinstance(item["owner"], str) or item["owner"] not in sources:
                    _fail("Follow-up owner must be buyer or a supplier source ID.")
    owners = {item["owner"] for item in data["follow_up_questions"]}
    if owners != set(sources):
        _fail("Include follow-up questions for the buyer and every supplier.")
    return data
