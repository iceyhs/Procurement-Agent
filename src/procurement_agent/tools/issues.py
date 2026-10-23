"""Evidence-backed issue candidates and follow-up ordering; no question templates."""

import re
from decimal import Decimal

SEVERITIES = ("BLOCKER", "HIGH", "MEDIUM", "LOW")
CATEGORIES = ("technical", "cost", "delivery", "quantity", "payment", "validity", "other")


def issue_candidates(extraction, calculations, context):
    result = {owner: [] for owner in context}

    def add(owner, field, category, severity, reason, *support, basis="ambiguous"):
        issue = {"id": f"{owner}_{field}", "owner": owner, "category": category,
                 "severity": severity, "basis": basis, "reason": reason, "fields": [field],
                 "evidence_fields": list(dict.fromkeys((field, *support)))}
        previous = next((i for i in result[owner] if i["id"] == issue["id"]), None)
        if previous is None:
            result[owner].append(issue)
        elif SEVERITIES.index(severity) < SEVERITIES.index(previous["severity"]) or (
            severity == previous["severity"] and basis == "unverified" and previous["basis"] != "unverified"
        ):
            result[owner].remove(previous)
            result[owner].append(issue)

    for risk in context["buyer"]["detected_risks"]:
        add("buyer", risk["field"], "technical" if risk["field"] == "revision" else "delivery",
            "BLOCKER", risk["detail"], "quantity", basis="missing")
    amounts = {c["source_id"]: c for c in calculations}
    for supplier in extraction["suppliers"]:
        owner = supplier["source_id"]
        calc = amounts[owner]

        def text(field):
            fact = supplier[field]
            return " ".join(str(fact[key] or "") for key in ("value", "evidence"))

        for field in context[owner]["uncertain_fields"]:
            if field not in {"currency", "tooling_currency"}:
                continue  # Qualitative pricing clauses need model judgment below.
            add(owner, field, "cost", "MEDIUM", "Currency or pricing qualification needs confirmation; conditional shortlisting remains possible.",
                "quoted_price" if field != "tooling_currency" else "tooling_amount",
                basis="missing" if supplier[field]["value"] is None else "ambiguous")
        for field in context[owner]["validation_fields"]:
            severity = "HIGH" if field in {"quoted_price", "price_basis_quantity", "annual_volume", "moq", "min_release", "tooling_amount"} else "MEDIUM"
            add(owner, field, "other", severity,
                "This extracted term failed evidence validation and remains unverified; verify the original quote without assuming it was omitted.", basis="unverified")
        if calc["revision_blocker"]:
            add(owner, "revision", "technical", "BLOCKER", calc["revision_blocker"], basis="conflict")
        elif calc["revision_comparability_gap"]:
            add(owner, "revision", "technical", "HIGH",
                "Quoted revision bases differ. After the buyer establishes the required revision, this supplier must confirm compliance or re-quote.", basis="conflict")
        if re.search(r"around|approx|indicative|estimat|provisional|pending|to be confirmed", text("price_qualification") + " " + text("quoted_price"), re.I):
            add(owner, "price_qualification", "cost", "HIGH", "The price is provisional; a firm price and its conditions are unresolved.", "quoted_price")
        if supplier["tooling_amount"]["value"] is None and re.search(r"pending|\bTBD\b|\bto be (?:confirmed|determined)\b|\bneed\b.{0,30}\bconfirm\b", text("tooling_terms"), re.I):
            add(owner, "tooling_amount", "cost", "HIGH", "Tooling is explicitly pending; its cost must be established before firm cost comparison.", "tooling_terms", basis="missing")
        delivery = text("delivery_terms") + " " + text("other_terms")
        if re.search(r"\bFOB\b|\bEXW\b|freight.{0,25}dut(?:y|ies).{0,25}(?:not included|excluded)", delivery, re.I):
            add(owner, "delivery_terms", "cost", "HIGH", "The quoted scope does not establish delivered cost; obtain the remaining logistics costs after buyer destination confirmation.", "other_terms")
        lead = text("lead_time")
        if re.search(r"production|once we.re running|after.{0,30}approval", lead, re.I):
            add(owner, "lead_time", "delivery", "HIGH", "The quoted duration has a production, startup or approval condition; full delivery timing needs clarification.")
        buyer = extraction["buyer"]
        if buyer["quantity_basis"]["value"] == "order" and buyer["quantity"]["value"] and supplier["moq"]["value"]:
            if Decimal(buyer["quantity"]["value"]) < Decimal(supplier["moq"]["value"]):
                add(owner, "moq", "quantity", "BLOCKER", "The quoted MOQ exceeds the buyer's stated order quantity; an exception or revised offer is required.", basis="conflict")
    return result


def question_severity(question, issues):
    return min((issues[i]["severity"] for i in question["issue_ids"]), key=SEVERITIES.index)
