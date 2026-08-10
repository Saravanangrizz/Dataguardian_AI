"""
Investigation pipeline orchestrator.

This is the piece that turns five separate agents into one collaborating
chain instead of five independent reports:

    Reliability Engineer
          |  (staleness / pipeline evidence)
          v
    Lineage Investigator
          |  (resolves which dashboards actually depend on this asset)
          v
    Governance Officer
          |  (ownership / doc / PII gaps on this asset)
          v
    Business Impact Advisor
          |  (translates the above into stakeholder language --
          |   it is only allowed to use facts the earlier stages produced)
          v
    Executive Summary

Each function below takes the previous stage's *output*, not just the
raw entity -- e.g. the Business Impact Advisor never touches DataHub
directly, it only sees what Reliability + Lineage + Governance already
decided. That's what makes this a pipeline rather than five agents
re-reading the same table independently.
"""
from __future__ import annotations
from datetime import datetime, timezone
from app.datahub_client import DataHubClient
from app.agents.reliability import _hours_since
from app.agents.lineage_investigator import investigate_lineage
from app.agents.business_impact import assess_business_impact
from app.agents.executive_summary import generate_executive_summary

NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)


async def _reliability_stage(client: DataHubClient, entity: dict, lineage: dict) -> dict:
    notes = []
    severity = "ok"

    if "expected_freshness_hours" in entity:
        age = _hours_since(entity["last_modified"])
        ratio = age / entity["expected_freshness_hours"] if entity["expected_freshness_hours"] else 0
        if ratio >= 1:
            severity = "critical" if ratio >= 2 else "high"
            notes.append(f"stale for {age:.0f}h ({ratio:.1f}x expected refresh window)")

    # look one hop upstream for a pipeline that feeds this entity
    for up_urn in lineage.get("upstream", []) if lineage else []:
        up_entity = await client.get_entity(up_urn) if isinstance(up_urn, str) else None
        if up_entity and up_entity.get("last_run_status") in ("FAILED", "DEGRADED"):
            severity = "critical" if up_entity["last_run_status"] == "FAILED" else max(severity, "high")
            notes.append(f"upstream pipeline '{up_entity['name']}' is {up_entity['last_run_status'].lower()}: {up_entity['failure_reason']}")

    return {"severity": severity, "notes": notes}


async def _governance_stage(entity: dict) -> dict:
    notes = []
    if "owner" in entity and not entity.get("owner"):
        notes.append("no assigned owner")
    if "owner" in entity and not entity.get("description"):
        notes.append("no documentation")
    if entity.get("contains_pii") and "PII" not in entity.get("tags", []):
        notes.append("contains PII but is untagged")
    return {"notes": notes}


def _build_remediation_plan(urn: str, entity: dict, governance_notes: list[str]) -> list[dict]:
    plan = []
    if "no assigned owner" in governance_notes:
        domain = entity.get("domain", "data").lower().replace(" ", "-")
        plan.append({
            "action": "assign_owner",
            "label": "Assign owner",
            "value": f"{domain}-team@company.com",
            "urn": urn,
        })
    if "no documentation" in governance_notes:
        plan.append({
            "action": "update_description",
            "label": "Add documentation",
            "value": f"{entity['name']} — auto-drafted description pending review.",
            "urn": urn,
        })
    if "contains PII but is untagged" in governance_notes:
        plan.append({
            "action": "add_tags",
            "label": "Apply governance tag",
            "value": ["PII"],
            "urn": urn,
        })
    return plan


def _build_timeline(entity: dict, lineage: dict, reliability_notes: list[str]) -> list[dict]:
    events = []
    if "last_modified" in entity:
        age = _hours_since(entity["last_modified"])
        events.append({"when_hours_ago": age, "label": f"'{entity['name']}' last modified"})
    for up in lineage.get("upstream", []):
        events.append({"when_hours_ago": None, "label": f"Depends on upstream: {up.get('name', up) if isinstance(up, dict) else up}"})
    for note in reliability_notes:
        events.append({"when_hours_ago": None, "label": note.capitalize()})
    events.append({"when_hours_ago": 0, "label": "AI investigation completed"})
    # sort what we can chronologically (unknown-time entries stay in encounter order)
    timed = sorted([e for e in events if e["when_hours_ago"] is not None], key=lambda e: -e["when_hours_ago"])
    untimed = [e for e in events if e["when_hours_ago"] is None]
    return timed[:-1] + untimed + timed[-1:] if timed else untimed


async def investigate(client: DataHubClient, urn: str) -> dict:
    entity = await client.get_entity(urn)
    if not entity:
        return {"urn": urn, "error": "entity not found"}

    # Stage 1: Reliability Engineer needs lineage to check upstream pipeline
    # health, so we fetch raw lineage once and hand it to both stage 1 and
    # the full Lineage Investigator stage that follows.
    raw_lineage = await client.get_lineage(urn)
    reliability = await _reliability_stage(client, entity, raw_lineage)

    # Stage 2: Lineage Investigator enriches raw urns into named, typed entities
    lineage = await investigate_lineage(client, urn)

    # Stage 3: Governance Officer
    governance = await _governance_stage(entity)

    # Stage 4: Business Impact Advisor -- only sees stage 1-3 outputs
    business_impact = await assess_business_impact(
        entity["name"], reliability["notes"], governance["notes"], lineage["downstream_dashboards"]
    )

    remediation_plan = _build_remediation_plan(urn, entity, governance["notes"])
    timeline = _build_timeline(entity, lineage, reliability["notes"])

    # Stage 5: Executive Summary -- only sees stage 1-4 outputs
    executive_summary = await generate_executive_summary(
        entity["name"], reliability["notes"], governance["notes"], business_impact,
        [p["label"] for p in remediation_plan],
    )

    return {
        "urn": urn,
        "entity_name": entity["name"],
        "stages": [
            {
                "agent": "Reliability Engineer",
                "summary": "; ".join(reliability["notes"]) or "No reliability issues found.",
                "severity": reliability["severity"],
            },
            {
                "agent": "Lineage Investigator",
                "summary": (
                    f"{len(lineage['downstream'])} downstream, {len(lineage['upstream'])} upstream dependencies resolved"
                    + (f"; {len(lineage['hidden_dependencies'])} unresolved" if lineage["hidden_dependencies"] else "")
                ),
                "downstream": lineage["downstream"],
                "upstream": lineage["upstream"],
            },
            {
                "agent": "Governance Officer",
                "summary": "; ".join(governance["notes"]) or "No governance issues found.",
            },
            {
                "agent": "Business Impact Advisor",
                "summary": business_impact,
            },
            {
                "agent": "Executive Summary",
                "summary": executive_summary,
            },
        ],
        "timeline": timeline,
        "remediation_plan": remediation_plan,
        "business_impact": business_impact,
        "executive_summary": executive_summary,
    }
