"""
Business Impact Advisor agent.

Takes what the Reliability Engineer and Governance Officer already found,
plus the resolved downstream dashboards from the Lineage Investigator stage,
and translates it into a sentence a non-technical stakeholder would
actually understand and act on. This agent never re-derives evidence --
it only translates what upstream agents already established, which is
what keeps the collaboration chain honest (no stage invents new facts).
"""
from __future__ import annotations
from app.ai_provider import get_ai_provider


async def assess_business_impact(
    entity_name: str,
    reliability_notes: list[str],
    governance_notes: list[str],
    downstream_dashboards: list[dict],
) -> str:
    if not reliability_notes and not governance_notes:
        return f"No material business impact detected for {entity_name} at this time."

    dashboard_desc = ", ".join(
        f"{d['name']} ({d.get('viewers_last_30d', '?')} viewers/30d)" for d in downstream_dashboards
    ) or "no directly consuming dashboards found in the graph"

    prompt = (
        f"Dataset: {entity_name}\n"
        f"Reliability findings: {reliability_notes or 'none'}\n"
        f"Governance findings: {governance_notes or 'none'}\n"
        f"Downstream dashboards: {dashboard_desc}\n"
    )

    return await get_ai_provider().reason(
        system=(
            "You are the Business Impact Advisor on a data governance team. "
            "Translate the technical findings below into ONE or TWO sentences "
            "a non-technical business stakeholder would understand -- name the "
            "affected dashboard/report and the concrete consequence (e.g. stale "
            "numbers, wrong totals, delayed reporting). No jargon like 'schema' "
            "or 'lineage'. If no dashboards are affected, say so plainly."
        ),
        prompt=prompt,
    )
