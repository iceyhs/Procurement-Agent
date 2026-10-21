"""Dependency-free contracts for model responses and evidence validation.

Evidence matching establishes traceability, not semantic correctness.
"""

import copy
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


def _object_schema(properties):
    return {
        "type": "object", "properties": properties,
        "required": list(properties), "additionalProperties": False,
    }


def _structured_format(name, schema):
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}


def extraction_format(source_ids: list[str]) -> dict:
    """Named supplier properties enforce exactly one record per source."""
    fact = _object_schema({
        "value": {"type": ["string", "null"], "minLength": 1, "description": "Extracted value; numeric values are decimal strings. Null when unknown."},
        "evidence": {
            "type": ["string", "null"], "pattern": r"^L[1-9][0-9]*(?:-L[1-9][0-9]*)?$",
            "description": "Supporting source lines, e.g. L3 or L3-L5, within this record's own source. Null when unknown.",
        },
    })
    schema = _object_schema({
        "buyer": _object_schema({field: {"$ref": "#/$defs/fact"} for field in BUYER_FIELDS}),
        "suppliers": _object_schema({source_id: {"$ref": "#/$defs/supplier"} for source_id in source_ids}),
    })
    schema["$defs"] = {
        "fact": fact,
        "supplier": _object_schema({field: {"$ref": "#/$defs/fact"} for field in SUPPLIER_FIELDS}),
    }
    return _structured_format("procurement_extraction", schema)


def analysis_format(source_ids: list[str]) -> dict:
    item = {
        "text": {"type": "string", "description": "Plain-prose assessment grounded in the referenced facts and calculations."},
        "source_ids": {"type": "array", "items": {"type": "string", "enum": source_ids}},
    }
    return _structured_format("procurement_analysis", _object_schema({
        "risks": {"type": "array", "items": _object_schema(item)},
        "recommendation": {"type": "array", "items": _object_schema(item)},
        "follow_up_questions": {
            "type": "array", "items": _object_schema({
                **item, "owner": {"type": "string", "enum": source_ids},
            }),
        },
    }))


class ValidationError(ValueError):
    """A safe, bounded description of an invalid model response."""


def _fail(message: str):
    raise ValidationError(message)


def _keys(value, expected, location):
    fields = ", ".join(expected)
    if not isinstance(value, dict):
        _fail(f"{location}: expected an object with fields [{fields}]; got {type(value).__name__}.")
    if set(value) != set(expected):
        # Report shape only, never field values or an unbounded model-supplied key.
        keys = [key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,40}", key)
                else "<nonstandard key>" for key in list(value)[:8]]
        _fail(f"{location}: expected fields [{fields}]; got fields [{', '.join(keys)}].")


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
    if not isinstance(evidence, str) or not evidence.strip():
        _fail(f"{location}: known values require a short evidence excerpt.")
    citation = re.fullmatch(r"L([1-9][0-9]*)(?:-L([1-9][0-9]*))?", evidence)
    if citation:
        if len(evidence) > 64:
            _fail(f"{location}: evidence line range is too long.")
        start, end = int(citation[1]), int(citation[2] or citation[1])
        lines = source.splitlines()
        if not 1 <= start <= end <= len(lines):
            _fail(f"{location}: evidence line range is outside this source.")
        evidence = "\n".join(lines[start - 1:end])
        value["evidence"] = evidence
    if not evidence.strip():
        _fail(f"{location}: evidence must cite nonempty source text.")
    if len(evidence) > 2000:
        _fail(f"{location}: evidence must be at most 2000 characters; cite a shorter line range.")
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
    if field == "moq" and not re.search(r"\bMOQ\b|\bminimum\s+(?:order|purchase|quantity|qty)\b", evidence, re.IGNORECASE):
        _fail(f"{location}: an MOQ needs explicit minimum-order evidence; minimum releases are a separate field.")
    if field in {"currency", "tooling_currency", "deposit_currency"}:
        if not re.fullmatch(r"[A-Z]{3}|\$", data):
            _fail(f"{location}: expected a three-letter currency or ambiguous '$'.")
        markers = {"USD": ("USD", "US$"), "EUR": ("EUR", "€"), "GBP": ("GBP", "£")}
        if not any(marker in evidence for marker in markers.get(data, (data,))):
            _fail(f"{location}: currency must be explicit; bare '$' does not establish USD.")


def validate_extraction(data: dict, sources: dict[str, str], *, allow_partial=False) -> dict:
    data = copy.deepcopy(data)
    _keys(data, ("buyer", "suppliers"), "extraction")
    _keys(data["buyer"], BUYER_FIELDS, "buyer")
    errors = []
    warnings = []
    expected_ids = list(sources)[1:]
    if isinstance(data["suppliers"], dict):
        _keys(data["suppliers"], expected_ids, "suppliers")
        suppliers = []
        for source_id in expected_ids:
            record = data["suppliers"][source_id]
            _keys(record, SUPPLIER_FIELDS, source_id)
            suppliers.append({"source_id": source_id, **record})
        data["suppliers"] = suppliers

    def check_fact(value, field, source, location):
        try:
            _fact(value, field, source, location)
            return True
        except ValidationError as error:
            errors.append(str(error))
            if allow_partial:
                source_id = location.split(".")[0]
                replacement = {"value": None, "evidence": None}
                record = data["buyer"] if source_id == "buyer" else next(
                    item for item in data["suppliers"] if item["source_id"] == source_id
                )
                record[field] = replacement
                warnings.append({"source_id": source_id, "field": field, "reason": str(error)})
            return False

    for field in BUYER_FIELDS:
        check_fact(data["buyer"][field], field, sources["buyer"], f"buyer.{field}")
    suppliers = data["suppliers"]
    expected_ids = set(expected_ids)
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
        if all(valid) or allow_partial:
            known = [item[field]["value"] is not None for field in ("quoted_price", "price_basis_quantity", "currency")]
            if any(known) and not all(known):
                errors.append(f"{source_id}: price, price basis, and currency must be known together or all null.")
                if allow_partial:
                    for field in ("quoted_price", "price_basis_quantity", "currency"):
                        item[field] = {"value": None, "evidence": None}
                    warnings.append({"source_id": source_id, "field": "price", "reason": "Price calculation inputs are incomplete or unverified; all price calculations withheld."})
    if errors and not allow_partial:
        _fail("Extraction validation failed: " + "; ".join(errors[:12]))
    data["suppliers"].sort(key=lambda item: int(item["source_id"].split("_")[1]))
    if warnings:
        data["validation_warnings"] = warnings
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
