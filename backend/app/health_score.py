"""
Deterministic health score. This is intentionally NOT an LLM call --
scores need to be stable, auditable, and cheap to recompute, so they're
plain ratios over the metadata graph. The AI layer explains and acts on
these numbers (see agents/*.py); it doesn't compute them, which keeps
"why is the score 71" always answerable without re-prompting a model.

Ownership/documentation/governance are computed over every dataset-shaped
entity (identified by the presence of an "owner" key, which every
DataHubClient implementation -- mock or live -- always sets). Freshness
and reliability are computed only over the subset of entities that
actually carry the signal they need (expected_freshness_hours+
last_modified, or last_run_status) -- in live mode without those signals
wired up yet, those two metrics are omitted from the breakdown rather
than silently scored as 0, which would misrepresent real data as broken.
"""
from __future__ import annotations
from app.datahub_client import DataHubClient
from app.agents.reliability import _hours_since


async def compute_health_score(client: DataHubClient) -> dict:
    entities = await client.list_entities()
    datasets = [e for e in entities if "owner" in e]
    fresh_datasets = [e for e in datasets if "expected_freshness_hours" in e and e.get("last_modified")]
    pipelines = [e for e in entities if "last_run_status" in e]

    if not datasets:
        return {"overall": 0, "breakdown": {}}

    breakdown = {
        "ownership": round(sum(1 for d in datasets if d.get("owner")) / len(datasets) * 100),
        "documentation": round(sum(1 for d in datasets if d.get("description")) / len(datasets) * 100),
        "governance": round(
            sum(1 for d in datasets if not d.get("contains_pii") or "PII" in d.get("tags", [])) / len(datasets) * 100
        ),
    }

    if fresh_datasets:
        breakdown["freshness"] = round(
            sum(1 for d in fresh_datasets if _hours_since(d["last_modified"]) <= d["expected_freshness_hours"])
            / len(fresh_datasets) * 100
        )
    if pipelines:
        breakdown["reliability"] = round(
            sum(1 for p in pipelines if p["last_run_status"] == "OK") / len(pipelines) * 100
        )

    overall = round(sum(breakdown.values()) / len(breakdown))
    return {"overall": overall, "breakdown": breakdown}
