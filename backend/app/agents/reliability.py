"""
Reliability Engineer agent.

Observes freshness and pipeline run-health signals, computes a risk
score with rule-based evidence (so it's always explainable even without
an LLM), then asks the AI provider to turn that evidence into a plain-
language narrative + recommended action. This mirrors the "reasoning
over metadata" story the hackathon rewards: the finding itself is
grounded in real signals, and the AI adds interpretation on top of it,
it doesn't invent the risk from nothing.
"""
from __future__ import annotations
from datetime import datetime, timezone
from app.datahub_client import DataHubClient
from app.ai_provider import get_ai_provider

NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)


def _hours_since(iso_ts: str) -> float:
    ts = datetime.fromisoformat(iso_ts)
    return (NOW - ts).total_seconds() / 3600


async def analyze_reliability(client: DataHubClient) -> list[dict]:
    findings = []
    entities = await client.list_entities()

    for e in entities:
        if "expected_freshness_hours" not in e:
            continue  # not a dataset
        age = _hours_since(e["last_modified"])
        expected = e["expected_freshness_hours"]
        ratio = age / expected if expected else 0

        if ratio >= 1.0:
            severity = "critical" if ratio >= 2 else "high"
            probability = min(0.55 + 0.15 * ratio, 0.97)
            evidence = (
                f"Last modified {age:.0f}h ago; expected refresh cadence is "
                f"{expected}h ({ratio:.1f}x overdue)."
            )
            lineage = await client.get_lineage(e["urn"])

            narrative = await get_ai_provider().reason(
                system=(
                    "You are a Data Reliability Engineer. Given a stale dataset "
                    "and its downstream consumers, explain the business risk in "
                    "2-3 sentences, plain language, no jargon."
                ),
                prompt=(
                    f"Dataset: {e['name']} (criticality: {e['criticality']})\n"
                    f"Evidence: {evidence}\n"
                    f"Downstream consumers: {lineage['downstream']}\n"
                ),
            )

            findings.append({
                "type": "reliability",
                "severity": severity,
                "urn": e["urn"],
                "name": e["name"],
                "title": f"{e['name']} is {ratio:.1f}x past its expected refresh window",
                "evidence": evidence,
                "confidence": round(probability, 2),
                "downstream": lineage["downstream"],
                "reasoning": narrative,
                "reasoning_source": get_ai_provider().name,
                "suggested_action": "investigate_pipeline",
            })

    for p in [e for e in entities if "last_run_status" in e]:
        if p["last_run_status"] in ("FAILED", "DEGRADED"):
            severity = "critical" if p["last_run_status"] == "FAILED" else "high"
            findings.append({
                "type": "reliability",
                "severity": severity,
                "urn": p["urn"],
                "name": p["name"],
                "title": f"Pipeline {p['name']} is {p['last_run_status'].lower()}",
                "evidence": p["failure_reason"],
                "confidence": 0.9 if severity == "critical" else 0.7,
                "downstream": p.get("feeds", []),
                "reasoning": p["failure_reason"],
                "reasoning_source": "rule",
                "suggested_action": "review_pipeline_run",
            })

    findings.sort(key=lambda f: {"critical": 0, "high": 1, "medium": 2}.get(f["severity"], 3))
    return findings
