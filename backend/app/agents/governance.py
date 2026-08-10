"""
Governance Officer agent.

Scans entities for ownership gaps, missing documentation, and PII/tag
hygiene, then drafts a concrete remediation (not just "missing owner" --
an actual owner suggestion, description draft, or tag set) that can be
written straight back into DataHub via the write-back endpoint.
"""
from __future__ import annotations
from app.datahub_client import DataHubClient
from app.ai_provider import get_ai_provider


async def analyze_governance(client: DataHubClient) -> list[dict]:
    findings = []
    entities = await client.list_entities()

    for e in entities:
        if "owner" not in e:
            continue  # only datasets carry ownership in this model

        if not e.get("owner"):
            suggested_owner = f"{e['domain'].lower().replace(' ', '-')}-team@company.com"
            findings.append({
                "type": "governance",
                "severity": "high" if e["criticality"] in ("HIGH", "CRITICAL") else "medium",
                "urn": e["urn"],
                "name": e["name"],
                "title": f"{e['name']} has no assigned owner",
                "evidence": f"Domain '{e['domain']}', criticality {e['criticality']}.",
                "confidence": 0.95,
                "reasoning": (
                    f"No owner blocks incident response: if this dataset breaks, "
                    f"nobody is paged and downstream teams find out from broken dashboards."
                ),
                "reasoning_source": "rule",
                "suggested_action": "assign_owner",
                "suggested_value": suggested_owner,
            })

        if not e.get("description"):
            draft = await get_ai_provider().reason(
                system=(
                    "You are a data governance officer. Write a one-sentence, "
                    "factual dataset description suitable for a data catalog, "
                    "based only on the fields given. Do not invent details."
                ),
                prompt=f"Dataset name: {e['name']}\nDomain: {e['domain']}\nTags: {e.get('tags')}",
            )
            findings.append({
                "type": "governance",
                "severity": "medium",
                "urn": e["urn"],
                "name": e["name"],
                "title": f"{e['name']} has no documentation",
                "evidence": "Description field is empty in the catalog.",
                "confidence": 0.9,
                "reasoning": "Undocumented datasets slow down every downstream consumer who has to guess at meaning and reliability.",
                "reasoning_source": "rule",
                "suggested_action": "update_description",
                "suggested_value": draft,
            })

        if e.get("contains_pii") and "PII" not in e.get("tags", []):
            findings.append({
                "type": "governance",
                "severity": "critical",
                "urn": e["urn"],
                "name": e["name"],
                "title": f"{e['name']} contains PII but is untagged",
                "evidence": "Schema/description indicates personal data with no PII classification tag.",
                "confidence": 0.85,
                "reasoning": "Untagged PII bypasses access-control and compliance policies that key off the PII tag.",
                "reasoning_source": "rule",
                "suggested_action": "add_tags",
                "suggested_value": ["PII"],
            })

    findings.sort(key=lambda f: {"critical": 0, "high": 1, "medium": 2}.get(f["severity"], 3))
    return findings
