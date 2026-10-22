"""Dependency-free contracts for model responses and evidence validation.

Evidence matching establishes traceability, not semantic correctness.
"""

import copy
import json
import re
from decimal import Decimal

from .tools.issues import CATEGORIES, SEVERITIES, question_severity

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
        "issues": {"type": "array", "items": _object_schema({
            "id": {"type": "string", "description": "Unique ID prefixed by the owner, e.g. supplier_1_currency."},
            "owner": {"type": "string", "enum": source_ids},
            "category": {"type": "string", "enum": list(CATEGORIES)},
            "severity": {"type": "string", "enum": list(SEVERITIES)},
            "basis": {"type": "string", "enum": ["missing", "unverified", "ambiguous", "conflict", "answered"]},
            "reason": {"type": "string", "description": "Explain the unresolved issue, not merely the quoted fact."},
            "fields": {"type": "array", "items": {"type": "string", "enum": list(dict.fromkeys((*BUYER_FIELDS, *SUPPLIER_FIELDS)))}},
            "evidence_fields": {"type": "array", "items": {"type": "string", "enum": list(dict.fromkeys((*BUYER_FIELDS, *SUPPLIER_FIELDS)))}},
        })},
        "risks": {"type": "array", "items": _object_schema(item)},
        "recommendation": _object_schema({
            source_id: _object_schema({
                **item, "action": {"type": "string", "enum": ["advance", "hold", "do_not_advance"]},
                "clarification_issue_ids": {"type": "array", "items": {"type": "string"}},
            }) for source_id in source_ids if source_id != "buyer"
        }),
        "follow_up_questions": {
            "type": "array", "items": _object_schema({
                **item, "owner": {"type": "string", "enum": source_ids},
                "priority": {"type": "string", "enum": ["blocking", "important", "optional"]},
                "fields": {"type": "array", "items": {"type": "string", "enum": list(dict.fromkeys((*BUYER_FIELDS, *SUPPLIER_FIELDS)))}},
                "issue_ids": {"type": "array", "items": {"type": "string"}},
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
            # Preserve the quoted symbol when the model inferred USD. The
            # calculation layer records any contextual inference separately.
            if data == "USD" and "$" in evidence and not re.search(
                r"\b(?:CAD|AUD|NZD|SGD|HKD|TWD|MXN|ARS|CLP|COP|UYU)\b", evidence
            ):
                value["value"] = "$"
                return
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
        for field in SUPPLIER_FIELDS:
            check_fact(item[field], field, sources[source_id], f"{source_id}.{field}")
    if errors and not allow_partial:
        _fail("Extraction validation failed: " + "; ".join(errors[:12]))
    data["suppliers"].sort(key=lambda item: int(item["source_id"].split("_")[1]))
    if warnings:
        data["validation_warnings"] = warnings
    return data


def _validate_issues(proposed, sources, context, extraction):
    if not isinstance(proposed, list) or len(proposed) > max(40, 12 * len(sources)):
        _fail("issues: expected a bounded list of evidence-backed unresolved issues.")
    result = {issue["id"]: copy.deepcopy(issue) for inventory in (context or {}).values()
              for issue in inventory.get("issues", [])}
    seen = set()
    for issue in proposed:
        _keys(issue, ("id", "owner", "category", "severity", "basis", "reason", "fields", "evidence_fields"), "issue")
        owner, issue_id = issue["owner"], issue["id"]
        if not isinstance(owner, str) or owner not in sources or not isinstance(issue_id, str):
            _fail("Issue owner and ID must reference this packet.")
        if not re.fullmatch(re.escape(owner) + r"_[A-Za-z0-9_]{1,70}", issue_id) or issue_id in seen:
            _fail("Issue IDs must be unique and prefixed by their owner.")
        seen.add(issue_id)
        if issue["category"] not in CATEGORIES or issue["severity"] not in SEVERITIES:
            _fail("Issue category or severity is invalid.")
        if issue["basis"] not in ("missing", "unverified", "ambiguous", "conflict", "answered"):
            _fail("Issue basis must distinguish missing, unverified, ambiguous, and conflicting terms.")
        if not isinstance(issue["reason"], str) or not issue["reason"].strip() or len(issue["reason"]) > 2000:
            _fail("Issue reason must explain a bounded, unresolved risk.")
        allowed = BUYER_FIELDS if owner == "buyer" else SUPPLIER_FIELDS
        for key in ("fields", "evidence_fields"):
            refs = issue[key]
            if not isinstance(refs, list) or not refs or any(not isinstance(f, str) or f not in allowed for f in refs):
                _fail("Issue fields and evidence_fields must reference its owner's extracted terms.")
        if issue["basis"] == "answered":
            seed = result.get(issue_id)
            if seed is None or seed["severity"] == "BLOCKER" or seed["basis"] != "ambiguous":
                _fail("Only a heuristic ambiguity can be marked answered; confirmed blockers and validation gaps remain unresolved.")
            if set(seed["fields"]) != set(issue["fields"]):
                _fail("An answered candidate must refer to the same unresolved term.")
            if extraction is None:
                _fail("Marking a candidate answered requires validated supporting facts.")
            record = extraction["buyer"] if owner == "buyer" else next(s for s in extraction["suppliers"] if s["source_id"] == owner)
            if not any(record[f]["value"] is not None for f in issue["evidence_fields"]):
                _fail("An answered candidate needs quoted evidence of the answer.")
            del result[issue_id]
            continue
        if issue_id in result:
            seed = result[issue_id]
            if set(seed["fields"]) != set(issue["fields"]):
                _fail("An issue candidate ID cannot be reused for another unresolved term.")
            # Known evidence and deterministic severity floors survive model omission/downgrade.
            if SEVERITIES.index(issue["severity"]) < SEVERITIES.index(seed["severity"]):
                seed["severity"] = issue["severity"]
                seed["reason"] += " Priority assessment: " + issue["reason"]
        else:
            if extraction is not None:
                record = extraction["buyer"] if owner == "buyer" else next(s for s in extraction["suppliers"] if s["source_id"] == owner)
                unverified = (context or {}).get(owner, {}).get("validation_fields", [])
                if issue["basis"] == "missing" and any(record[f]["value"] is not None for f in issue["fields"]):
                    _fail("A missing-information issue cannot re-ask a term already answered in the extraction.")
                if issue["basis"] == "unverified" and not set(issue["fields"]) & set(unverified):
                    _fail("An unverified issue needs an actual validation warning.")
                if issue["basis"] in ("ambiguous", "conflict") and not any(record[f]["value"] is not None for f in issue["evidence_fields"]):
                    _fail("An ambiguity or conflict needs supporting quoted evidence.")
                if owner != "buyer" and issue["basis"] == "missing" and "tooling_amount" in issue["fields"]:
                    terms = record["tooling_terms"]["value"] or ""
                    if re.search(r"\bincluded\b", terms, re.I) and not re.search(r"pending|confirm|review", terms, re.I):
                        _fail("Included tooling is already answered; identify any actual amortization ambiguity instead.")
            result[issue_id] = issue
    if extraction is not None:
        records = {"buyer": extraction["buyer"], **{s["source_id"]: s for s in extraction["suppliers"]}}
        for issue in result.values():
            owner = issue["owner"]
            warnings = (context or {}).get(owner, {}).get("validation_fields", [])
            issue["evidence"] = [{"source_id": owner, "field": field, **records[owner][field],
                                  "status": "unverified" if field in warnings else "unknown" if records[owner][field]["value"] is None else "quoted"}
                                 for field in issue["evidence_fields"]]
            if issue["basis"] == "conflict":
                buyer_terms = {"revision": "revision", "part": "part", "moq": "quantity", "lead_time": "required_delivery"}
                for field in dict.fromkeys(buyer_terms[f] for f in issue["fields"] if f in buyer_terms):
                    if records["buyer"][field]["value"] is not None:
                        issue["evidence"].append({"source_id": "buyer", "field": field, **records["buyer"][field], "status": "quoted"})
                if "revision" in issue["fields"] and records["buyer"]["revision"]["value"] is None:
                    for peer in extraction["suppliers"]:
                        if peer["source_id"] != owner and peer["revision"]["value"] is not None:
                            issue["evidence"].append({"source_id": peer["source_id"], "field": "revision", **peer["revision"], "status": "quoted"})
    return result


def _select_questions(questions, issues, sources):
    selected = []
    for owner in sources:
        ordered = sorted((q for q in questions if q["owner"] == owner), key=lambda q: SEVERITIES.index(q["severity"]))
        unique = {}
        for question in ordered:
            key = _normalize(question["text"]).casefold()
            if key not in unique:
                unique[key] = question
            else:
                kept = unique[key]
                for field in ("issue_ids", "fields", "source_ids"):
                    kept[field] = list(dict.fromkeys(kept[field] + question[field]))
                kept["severity"] = question_severity(kept, issues)
        ranked = sorted(unique.values(), key=lambda q: SEVERITIES.index(q["severity"]))
        chosen = ranked if owner == "buyer" else ranked[:3]
        covered = {ref for q in chosen for ref in q["issue_ids"]}
        missing_blockers = [i["id"] for i in issues.values() if i["owner"] == owner and i["severity"] == "BLOCKER" and i["id"] not in covered]
        if missing_blockers:
            prefix = "Missing blocking buyer follow-up questions: " if owner == "buyer" else f"Missing supplier follow-ups: {owner}: BLOCKER questions required: "
            _fail(prefix + ", ".join(missing_blockers))
        if chosen:
            last = max(SEVERITIES.index(issues[ref]["severity"]) for ref in covered)
            skipped = [i["id"] for i in issues.values() if i["owner"] == owner and i["id"] not in covered and SEVERITIES.index(i["severity"]) < last]
            if skipped:
                _fail("Higher-priority unresolved issues must be questioned before lower-priority topics: " + ", ".join(skipped))
        selected.extend(chosen)
    return selected


def validate_analysis(data: dict, sources: dict[str, str], *, follow_up_context=None, extraction=None) -> dict:
    data = copy.deepcopy(data)
    _keys(data, ("issues", "risks", "recommendation", "follow_up_questions"), "analysis")
    issues = _validate_issues(data["issues"], sources, follow_up_context, extraction)
    data["issues"] = list(issues.values())
    supplier_ids = [source_id for source_id in sources if source_id != "buyer"]
    if isinstance(data["recommendation"], dict):
        _keys(data["recommendation"], supplier_ids, "recommendation")
        records = []
        for supplier_id in supplier_ids:
            record = data["recommendation"][supplier_id]
            _keys(record, ("text", "source_ids", "action", "clarification_issue_ids"), "recommendation")
            records.append({"supplier_id": supplier_id, **record})
        data["recommendation"] = records
    for section in ("risks", "recommendation", "follow_up_questions"):
        items = data[section]
        minimum = 0 if section == "follow_up_questions" else 1
        maximum = len(supplier_ids) if section == "recommendation" else max(40, 6 * len(sources))
        if not isinstance(items, list) or not minimum <= len(items) <= maximum:
            _fail(f"{section}: expected {minimum} to {maximum} items.")
        for item in items:
            fields = {
                "risks": ("text", "source_ids"),
                "recommendation": ("text", "source_ids", "supplier_id", "action", "clarification_issue_ids"),
                "follow_up_questions": ("text", "source_ids", "owner", "priority", "fields", "issue_ids"),
            }[section]
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
                if item["priority"] not in ("blocking", "important", "optional"):
                    _fail("Follow-up priority must be blocking, important, or optional.")
                fields = item["fields"]
                if not isinstance(fields, list) or not fields or any(not isinstance(field, str) or field not in (*BUYER_FIELDS, *SUPPLIER_FIELDS) for field in fields):
                    _fail("Follow-up fields must identify the terms the question addresses.")
                refs = item["issue_ids"]
                if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or ref not in issues for ref in refs):
                    _fail("Follow-up issue_ids must identify known unresolved issues.")
                if any(issues[ref]["owner"] != item["owner"] for ref in refs):
                    _fail("Buyer-wide and supplier-specific issues must stay with their resolution owner.")
                item["severity"] = question_severity(item, issues)
                item["priority"] = "blocking" if item["severity"] == "BLOCKER" else "optional" if item["severity"] == "LOW" else "important"
            if section == "recommendation":
                if not isinstance(item["supplier_id"], str) or item["supplier_id"] not in supplier_ids:
                    _fail("Recommendation must identify a supplier from this packet.")
                if item["action"] not in ("advance", "hold", "do_not_advance"):
                    _fail("Recommendation action must be advance, hold, or do_not_advance.")
                refs = item["clarification_issue_ids"]
                if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in issues for ref in refs):
                    _fail("Recommendation clarification_issue_ids must identify known issues.")
                if any(issues[ref]["owner"] not in ("buyer", item["supplier_id"]) for ref in refs):
                    _fail("Recommendation conditions must belong to that supplier or the buyer.")
    recommendations = [item["supplier_id"] for item in data["recommendation"]]
    if len(recommendations) != len(supplier_ids) or set(recommendations) != set(supplier_ids):
        _fail("Include exactly one recommendation action for every supplier.")
    data["follow_up_questions"] = _select_questions(data["follow_up_questions"], issues, sources)
    covered_issues = {ref for q in data["follow_up_questions"] for ref in q["issue_ids"]}
    for decision in data["recommendation"]:
        missing = set(decision["clarification_issue_ids"]) - covered_issues
        if missing:
            _fail("Recommendation/follow-up inconsistency: draft questions for clarification issues " + ", ".join(sorted(missing)))
    if follow_up_context:
        required = {risk["field"] for risk in follow_up_context.get("buyer", {}).get("detected_risks", []) if risk.get("blocking")}
        covered = {field for item in data["follow_up_questions"] if item["owner"] == "buyer" and item["priority"] == "blocking" for field in item["fields"]}
        if required - covered:
            _fail("Missing blocking buyer follow-up questions for: " + ", ".join(sorted(required - covered)) + ". Ask the buyer, not a supplier, to establish these requirements.")
        missing_supplier_questions = []
        follow_up_warnings = []
        for decision in data["recommendation"]:
            owner = decision["supplier_id"]
            issue = follow_up_context.get(owner, {})
            uncertain = set(issue.get("uncertain_fields", []) + issue.get("validation_fields", []))
            questions = [item for item in data["follow_up_questions"]
                         if item["owner"] == owner and owner in item["source_ids"]
                         and item["priority"] != "optional" and set(item["fields"]) & set(SUPPLIER_FIELDS)]
            if decision["action"] == "do_not_advance":
                if owner not in decision["source_ids"] or not any(q["priority"] == "blocking" for q in questions):
                    missing_supplier_questions.append(f"{owner}: do_not_advance requires a supplier-specific blocker and a blocking question citing that supplier; shared buyer unknowns alone do not justify stopping the offer")
            elif decision["action"] == "hold" and not questions:
                missing_supplier_questions.append(f"{owner}: hold requires an actionable supplier-owned clarification question")
            elif decision["action"] == "advance" and uncertain and not any(set(q["fields"]) & uncertain for q in questions):
                # Coverage tags cannot establish whether prose resolves a term.
                # Non-blocking clarification gaps must not discard a usable report.
                follow_up_warnings.append({"source_id": owner, "fields": sorted(uncertain)})
        if missing_supplier_questions:
            _fail("Missing supplier follow-ups: " + "; ".join(missing_supplier_questions[:12]))
        if follow_up_warnings:
            data["follow_up_warnings"] = follow_up_warnings
    return data
