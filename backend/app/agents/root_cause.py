"""
Root Cause agent.

Given an entity (usually a dashboard or dataset a user is worried
about), walks the lineage graph upstream hop by hop and, at each hop
that carries a known failure/change signal, appends it to a reasoning
chain. Finishes with an LLM-authored plain-language explanation and an
executive-ready summary.
"""
from __future__ import annotations
from app.datahub_client import DataHubClient
from app.ai_provider import get_ai_provider


async def trace_root_cause(client: DataHubClient, urn: str) -> dict:
    chain = []
    current = urn
    visited = set()

    for _ in range(6):  # cap hops to avoid cycles in malformed lineage
        if current in visited:
            break
        visited.add(current)

        entity = await client.get_entity(current)
        lineage = await client.get_lineage(current)

        label = entity["name"] if entity else current
        note = None
        if entity and entity.get("last_run_status") in ("FAILED", "DEGRADED"):
            note = entity["failure_reason"]
        elif entity and "last_modified" in entity:
            note = f"last modified {entity['last_modified']}"

        chain.append({"urn": current, "label": label, "note": note})

        upstream = lineage["upstream"]
        if not upstream:
            break
        current = upstream[0]  # follow the primary upstream path

    narrative = await get_ai_provider().reason(
        system=(
            "You are a data reliability engineer explaining a root cause to a "
            "non-technical stakeholder. Given a lineage chain from an affected "
            "asset back to its root cause, write a short plain-language "
            "explanation (3-4 sentences) of what happened and why it matters."
        ),
        prompt="Chain (affected -> root cause):\n" + "\n".join(
            f"- {c['label']}" + (f" ({c['note']})" if c["note"] else "") for c in chain
        ),
    )

    return {
        "urn": urn,
        "chain": chain,
        "explanation": narrative,
        "reasoning_source": get_ai_provider().name,
    }
