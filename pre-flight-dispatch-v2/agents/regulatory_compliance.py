"""
Regulatory Compliance Agent (V2)
Checks airworthiness certificates, COAs, ETOPS, RVSM, insurance,
and RAGs against ALL regulatory document types for comprehensive compliance.
"""

import logging
from datetime import date, datetime
from typing import Any

from tools.sql_tools import query_table
from tools.vector_search_tools import search_regulations
from tools.llm_tools import llm_call

logger = logging.getLogger("agents.regulatory_compliance")


def _parse_date(val) -> date | None:
    """Parse a date value that may be a string, date, or None."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


DESTINATION_COUNTRY = {
    "YYZ": "Canada", "YVR": "Canada",
    "LHR": "United Kingdom",
    "JFK": "United States", "SFO": "United States",
    "SIN": "Singapore",
    "DEL": "India", "BOM": "India", "BLR": "India",
    "MAA": "India", "CCU": "India", "HYD": "India",
}

REQ_TO_CERT = {
    "COA": {
        "Canada": "COA_CANADA",
        "United Kingdom": "COA_UK",
        "United States": "COA_USA",
    },
    "ETOPS": "ETOPS_180",
    "RVSM": "RVSM",
}


def run(aircraft_reg: str, destination: str) -> dict[str, Any]:
    """
    Run regulatory compliance check for the aircraft and destination.

    Returns:
        dict with keys: status, findings, recommendations, compliance_gaps,
                        regulatory_references, details
    """
    findings: list[str] = []
    recommendations: list[str] = []
    compliance_gaps: list[dict] = []
    regulatory_references: list[str] = []
    status = "GREEN"
    details: dict[str, Any] = {"certificates": [], "requirements": []}

    country = DESTINATION_COUNTRY.get(destination, "Unknown")
    today = date.today()

    try:
        # ── 1. Aircraft certificates ───────────────────────────────────────
        certs = query_table(
            "aircraft_certificates",
            where_clause=f"aircraft_reg = '{aircraft_reg}'",
        )
        cert_map: dict[str, dict] = {}
        for c in certs:
            cert_map[c.get("cert_type", "")] = c
        details["certificates"] = certs

        # ── 2. Regulatory requirements for destination ─────────────────────
        reqs = query_table(
            "regulatory_requirements",
            where_clause=f"destination_country = '{country}'",
        )
        details["requirements"] = reqs

        # ── 3. Check each requirement ──────────────────────────────────────
        for req in reqs:
            req_type = req.get("requirement_type", "")
            mandatory = req.get("mandatory", False)
            # Handle string booleans from SQL
            if isinstance(mandatory, str):
                mandatory = mandatory.lower() == "true"

            # Map requirement to certificate type
            if req_type == "COA":
                cert_type_needed = REQ_TO_CERT.get("COA", {}).get(country)
            elif req_type == "ETOPS":
                cert_type_needed = REQ_TO_CERT.get("ETOPS")
            elif req_type == "RVSM":
                cert_type_needed = REQ_TO_CERT.get("RVSM")
            else:
                cert_type_needed = req_type

            if not cert_type_needed:
                continue

            cert = cert_map.get(cert_type_needed)

            if not cert:
                if mandatory:
                    status = "RED"
                    gap = {
                        "requirement": req_type,
                        "country": country,
                        "description": req.get("description", ""),
                        "issue": f"No {cert_type_needed} certificate found for {aircraft_reg}",
                    }
                    compliance_gaps.append(gap)
                    findings.append(
                        f"MISSING: {req_type} certificate ({cert_type_needed}) for {country} - "
                        f"{req.get('description', '')}"
                    )
                    recommendations.append(
                        f"Cannot operate to {destination} ({country}) without {req_type} certificate. "
                        f"Swap to aircraft with valid {cert_type_needed}."
                    )
                continue

            expiry = _parse_date(cert.get("expiry_date"))
            cert_status = cert.get("status", "")

            if cert_status == "EXPIRED" or (expiry and expiry < today):
                if mandatory:
                    status = "RED"
                    gap = {
                        "requirement": req_type,
                        "country": country,
                        "cert_number": cert.get("cert_number", ""),
                        "expiry_date": str(cert.get("expiry_date", "")),
                        "issue": f"Certificate EXPIRED on {cert.get('expiry_date', '')}",
                    }
                    compliance_gaps.append(gap)
                    findings.append(
                        f"EXPIRED: {req_type} certificate ({cert.get('cert_number', '')}) "
                        f"for {country} - expired {cert.get('expiry_date', '')}. "
                        f"Issued by {cert.get('issuing_authority', 'N/A')}."
                    )
                    recommendations.append(
                        f"CRITICAL: {req_type} certificate for {country} has expired. "
                        f"Aircraft {aircraft_reg} CANNOT operate to {destination}. "
                        f"Options: (1) Swap to aircraft with valid {cert_type_needed}, "
                        f"(2) Obtain emergency renewal from {cert.get('issuing_authority', 'authority')}."
                    )
            elif expiry and (expiry - today).days < 30:
                if status == "GREEN":
                    status = "AMBER"
                days_left = (expiry - today).days
                findings.append(
                    f"EXPIRING SOON: {req_type} certificate ({cert.get('cert_number', '')}) "
                    f"for {country} - expires in {days_left} days ({cert.get('expiry_date', '')})"
                )
                recommendations.append(
                    f"Initiate renewal of {req_type} certificate with "
                    f"{cert.get('issuing_authority', 'authority')} - {days_left} days remaining"
                )
            else:
                findings.append(
                    f"VALID: {req_type} for {country} - cert {cert.get('cert_number', '')}, "
                    f"expires {cert.get('expiry_date', 'N/A')}"
                )

        # ── 4. Airworthiness certificate (always required) ────────────────
        aw_cert = cert_map.get("AIRWORTHINESS")
        if not aw_cert:
            status = "RED"
            findings.append(f"MISSING: Airworthiness certificate for {aircraft_reg}")
            recommendations.append("Ground aircraft - no airworthiness certificate on file")
            compliance_gaps.append({
                "requirement": "AIRWORTHINESS",
                "country": "ALL",
                "issue": "No airworthiness certificate found",
            })
        else:
            aw_expiry = _parse_date(aw_cert.get("expiry_date"))
            if aw_expiry and aw_expiry < today:
                status = "RED"
                findings.append(
                    f"EXPIRED: Airworthiness certificate - expired {aw_cert.get('expiry_date', '')}"
                )
                recommendations.append(
                    "Ground aircraft immediately - expired airworthiness certificate"
                )
                compliance_gaps.append({
                    "requirement": "AIRWORTHINESS",
                    "country": "ALL",
                    "expiry_date": str(aw_cert.get("expiry_date", "")),
                    "issue": "Airworthiness certificate expired",
                })

        # ── 5. Insurance certificate ──────────────────────────────────────
        ins_cert = cert_map.get("INSURANCE")
        if ins_cert:
            ins_expiry = _parse_date(ins_cert.get("expiry_date"))
            if ins_expiry and ins_expiry < today:
                status = "RED"
                findings.append(
                    f"EXPIRED: Insurance certificate - expired {ins_cert.get('expiry_date', '')}"
                )
                recommendations.append("Cannot operate without valid insurance")
                compliance_gaps.append({
                    "requirement": "INSURANCE",
                    "country": "ALL",
                    "issue": "Insurance expired",
                })

        # ── 6. RAG: Regulatory documents ──────────────────────────────────
        if compliance_gaps or status != "GREEN":
            gap_summary = " ".join(
                g.get("issue", "") for g in compliance_gaps[:3]
            )
            rag_query = (
                f"Regulatory compliance requirements for {destination} {country} "
                f"aircraft certificates COA ETOPS RVSM airworthiness {gap_summary}"
            )

            # Search ALL document types for comprehensive compliance
            reg_docs = search_regulations(rag_query, doc_type=None, num_results=5)

            if reg_docs:
                doc_context = "\n".join(
                    f"- {d.get('doc_id', 'N/A')} ({d.get('doc_type', '')}): "
                    f"{str(d.get('content', ''))[:250]}"
                    for d in reg_docs
                )

                compliance_assessment = llm_call(
                    system_prompt=(
                        "You are an aviation regulatory compliance expert for Indian airlines "
                        "operating international routes. Given the compliance findings and regulatory "
                        "documents, provide specific regulatory citations and remediation steps. "
                        "Be precise with regulation numbers. Keep under 250 words."
                    ),
                    user_prompt=(
                        f"Aircraft: {aircraft_reg}, Destination: {destination} ({country})\n"
                        f"Compliance gaps: {compliance_gaps}\n"
                        f"Findings: {findings}\n\n"
                        f"Relevant regulatory documents:\n{doc_context}\n\n"
                        f"Provide regulatory citations and remediation guidance."
                    ),
                    max_tokens=500,
                )

                if compliance_assessment:
                    regulatory_references.append(
                        f"Regulatory Analysis: {compliance_assessment}"
                    )

                for d in reg_docs:
                    regulatory_references.append(
                        f"Ref: {d.get('doc_id', 'N/A')} ({d.get('doc_type', '')}) - "
                        f"{d.get('title', d.get('section', ''))}"
                    )

    except Exception as e:
        logger.error("Regulatory compliance agent error: %s", e, exc_info=True)
        return {
            "status": "RED",
            "findings": [f"Agent error: {str(e)}"],
            "recommendations": ["Manual regulatory compliance check required"],
            "compliance_gaps": [],
            "regulatory_references": [],
            "details": {},
        }

    # Deduplicate
    regulatory_references = list(dict.fromkeys(regulatory_references))

    return {
        "status": status,
        "findings": findings,
        "recommendations": recommendations,
        "compliance_gaps": compliance_gaps,
        "regulatory_references": regulatory_references,
        "details": details,
    }
