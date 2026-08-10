"""
Lineage Investigator agent.

Sits between the Reliability Engineer and the Governance Officer in the
collaboration chain: takes the urn under investigation, walks its
lineage, and resolves raw urns into named, typed entities (dataset /
pipeline / dashboard) so downstream agents (Business Impact Advisor,
Executive Summary) can talk about "the Executive Revenue Dashboard"
instead of a urn string. Also flags dependencies that resolve to nothing
in the graph -- a real signal DataHub surfaces as broken lineage.
"""
from __future__ import annotations
from app.datahub_client import DataHubClient


def _entity_kind(entity: dict | None) -> str:
    if entity is None:
        return "unresolved"
    if "expected_freshness_hours" in entity:
        return "dataset"
    if "last_run_status" in entity:
        return "pipeline"
    if "viewers_last_30d" in entity:
        return "dashboard"
    return "unknown"


async def investigate_lineage(client: DataHubClient, urn: str) -> dict:
    lineage = await client.get_lineage(urn)

    async def resolve(urns: list[str]) -> list[dict]:
        resolved = []
        for u in urns:
            entity = await client.get_entity(u)
            resolved.append({
                "urn": u,
                "name": entity["name"] if entity else u,
                "kind": _entity_kind(entity),
                "resolved": entity is not None,
                **({"viewers_last_30d": entity.get("viewers_last_30d")} if entity and "viewers_last_30d" in entity else {}),
            })
        return resolved

    upstream = await resolve(lineage["upstream"])
    downstream = await resolve(lineage["downstream"])
    downstream_dashboards = [d for d in downstream if d["kind"] == "dashboard"]
    orphaned = [d for d in (upstream + downstream) if not d["resolved"]]

    return {
        "urn": urn,
        "upstream": upstream,
        "downstream": downstream,
        "downstream_dashboards": downstream_dashboards,
        "hidden_dependencies": orphaned,
    }
