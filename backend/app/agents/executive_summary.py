"""
Executive Summary Generator.

Last stage in the collaboration chain: consumes what every prior agent
already decided (it does not re-analyze anything) and compresses it into
the few lines an executive would actually read.
"""
from __future__ import annotations
from app.ai_provider import get_ai_provider


async def generate_executive_summary(
    entity_name: str,
    reliability_notes: list[str],
    governance_notes: list[str],
    business_impact: str,
    remediation_labels: list[str],
) -> str:
    prompt = (
        f"Asset: {entity_name}\n"
        f"Reliability issues found: {len(reliability_notes)} -- {reliability_notes}\n"
        f"Governance issues found: {len(governance_notes)} -- {governance_notes}\n"
        f"Business impact: {business_impact}\n"
        f"Recommended actions: {remediation_labels}\n"
    )
    return await get_ai_provider().reason(
        system=(
            "You write executive briefs for a data platform incident review. "
            "In 3-4 sentences: state the overall risk level, the single most "
            "important business consequence, and the top recommended action. "
            "Write for someone who will not read past this paragraph."
        ),
        prompt=prompt,
    )
