"""
Regulatory Compliance Agent
Checks airworthiness certificates, destination-specific COAs, ETOPS, RVSM, etc.
"""

import os
import logging
from datetime import date, datetime, timedelta
from typing import Any


def _parse_date(val):
    if val is None: return None
    if isinstance(val, date) and not isinstance(val, datetime): return val
    if isinstance(val, datetime): return val.date()
    try: return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except: return None

import psycopg2
import psycopg2.extras

from db import get_db

logger = logging.getLogger("agents.regulatory_compliance")

# Destination to country mapping
DESTINATION_COUNTRY = {
    "YYZ": "Canada",
    "YVR": "Canada",
    "LHR": "United Kingdom",
    "JFK": "United States",
    "SFO": "United States",
    "SIN": "Singapore",
    "DEL": "India",
    "BOM": "India",
    "BLR": "India",
    "MAA": "India",
    "CCU": "India",
    "HYD": "India",
}

# Certificate type mapping for regulatory requirements
REQ_TO_CERT = {
    "COA": {
        "Canada": "COA_CANADA",
        "United Kingdom": "COA_UK",
        "United States": "COA_USA",
    },
    "ETOPS": "ETOPS_180",
    "RVSM": "RVSM",
}




async def run(aircraft_reg: str, destination: str) -> dict[str, Any]:
    """
    Run regulatory compliance check for the aircraft and destination.

    Returns:
        dict with keys: status, findings, recommendations, details
    """
    findings = []
    recommendations = []
    status = "GREEN"
    details = {"certificates": [], "requirements": [], "compliance_gaps": []}

    country = DESTINATION_COUNTRY.get(destination, "Unknown")

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Get all certificates for this aircraft
        cur.execute(
            "SELECT * FROM aircraft_certificates WHERE aircraft_reg = %s",
            (aircraft_reg,),
        )
        certs = cur.fetchall()
        cert_map = {}
        for c in certs:
            cert_map[c["cert_type"]] = dict(c)
        details["certificates"] = [dict(c) for c in certs]

        # 2. Get regulatory requirements for destination country
        cur.execute(
            "SELECT * FROM regulatory_requirements WHERE destination_country = %s",
            (country,),
        )
        reqs = cur.fetchall()
        details["requirements"] = [dict(r) for r in reqs]

        # 3. Check each requirement
        today = date.today()

        for req in reqs:
            req_type = req["requirement_type"]
            mandatory = req["mandatory"]

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
                        "description": req["description"],
                        "issue": f"No {cert_type_needed} certificate found for {aircraft_reg}",
                    }
                    details["compliance_gaps"].append(gap)
                    findings.append(
                        f"MISSING: {req_type} certificate ({cert_type_needed}) for {country} — "
                        f"{req['description']}"
                    )
                    recommendations.append(
                        f"Cannot operate to {destination} ({country}) without {req_type} certificate. "
                        f"Swap to aircraft with valid {cert_type_needed}."
                    )
                continue

            # Check certificate status and expiry
            if cert["status"] == "EXPIRED" or _parse_date(cert["expiry_date"]) is not None and _parse_date(cert["expiry_date"]) < today:
                if mandatory:
                    status = "RED"
                    gap = {
                        "requirement": req_type,
                        "country": country,
                        "cert_number": cert["cert_number"],
                        "expiry_date": str(cert["expiry_date"]),
                        "issue": f"Certificate EXPIRED on {str(cert['expiry_date'])}",
                    }
                    details["compliance_gaps"].append(gap)
                    findings.append(
                        f"EXPIRED: {req_type} certificate ({cert['cert_number']}) "
                        f"for {country} — expired {str(cert['expiry_date'])}. "
                        f"Issued by {cert['issuing_authority']}."
                    )
                    recommendations.append(
                        f"CRITICAL: {req_type} certificate for {country} has expired. "
                        f"Aircraft {aircraft_reg} CANNOT operate to {destination}. "
                        f"Options: (1) Swap to aircraft with valid {cert_type_needed}, "
                        f"(2) Obtain emergency renewal from {cert['issuing_authority']}."
                    )
            elif cert["status"] == "EXPIRING_SOON" or (
                _parse_date(cert["expiry_date"]) - today
            ).days < 30:
                if status == "GREEN":
                    status = "AMBER"
                days_left = (_parse_date(cert["expiry_date"]) - today).days
                findings.append(
                    f"EXPIRING SOON: {req_type} certificate ({cert['cert_number']}) "
                    f"for {country} — expires in {days_left} days ({str(cert['expiry_date'])})"
                )
                recommendations.append(
                    f"Initiate renewal of {req_type} certificate with "
                    f"{cert['issuing_authority']} — {days_left} days remaining"
                )
            else:
                # Valid
                findings.append(
                    f"VALID: {req_type} for {country} — cert {cert['cert_number']}, "
                    f"expires {str(cert['expiry_date'])}"
                )

        # 4. Always check airworthiness certificate
        aw_cert = cert_map.get("AIRWORTHINESS")
        if not aw_cert:
            status = "RED"
            findings.append(
                f"MISSING: Airworthiness certificate for {aircraft_reg}"
            )
            recommendations.append("Ground aircraft — no airworthiness certificate on file")
        elif _parse_date(aw_cert["expiry_date"]) is not None and _parse_date(aw_cert["expiry_date"]) < today:
            status = "RED"
            findings.append(
                f"EXPIRED: Airworthiness certificate — expired {aw_cert['expiry_date']}"
            )
            recommendations.append("Ground aircraft immediately — expired airworthiness certificate")

        # 5. Check insurance
        ins_cert = cert_map.get("INSURANCE")
        if ins_cert and _parse_date(ins_cert["expiry_date"]) is not None and _parse_date(ins_cert["expiry_date"]) < today:
            status = "RED"
            findings.append(
                f"EXPIRED: Insurance certificate — expired {ins_cert['expiry_date']}"
            )
            recommendations.append("Cannot operate without valid insurance")

        cur.close()
        conn.close()

    except psycopg2.Error as e:
        logger.error(f"Database error in regulatory compliance agent: {e}")
        return {
            "status": "RED",
            "findings": [f"Database error: {str(e)}"],
            "recommendations": ["Check Lakebase connectivity"],
            "details": {},
        }

    return {
        "status": status,
        "findings": findings,
        "recommendations": recommendations,
        "details": details,
    }
