"""
Natural language query agent.

Two paths, chosen by what the question actually needs:

1. Named-entity path: if the question mentions a specific asset by name
   (e.g. "what happens if invalid ages enter raw_patients"), resolve
   that entity and fetch its LINEAGE, then let the model reason about
   downstream impact using real upstream/downstream urns -- not just
   flat metadata fields. This is the path the original version was
   missing entirely: it filtered rows by keyword but never included
   lineage in what got sent to the model, so any "what happens
   downstream" question was unanswerable no matter how well it matched.

2. Catalog-aggregate path: for questions like "which finance datasets
   lack owners", keyword-filter across all entities as before -- this
   part worked fine and is unchanged.

Both paths stay grounded: the model is told what IS and ISN'T recorded,
and asked to reason about consequences using lineage/metadata that
exists, rather than either inventing specifics or flatly refusing to
engage just because no literal keyword matched.
"""
from __future__ import annotations
from app.datahub_client import DataHubClient
from app.ai_provider import get_ai_provider


def _find_named_entities(entities: list[dict], question: str) -> list[dict]:
    q = question.lower()
    found = []
    for e in entities:
        name = e.get("name", "")
        if not name:
            continue
        # Match on full name, and on the short/base segment (handles
        # "raw_patients" matching a urn like "healthcare.raw_patients"
        # or "raw.patients", not just an exact full-name match).
        short = name.split(".")[-1].lower()
        if name.lower() in q or (short and len(short) > 3 and short in q):
            found.append(e)
    return found


async def answer_query(client: DataHubClient, question: str) -> dict:
    entities = await client.list_entities()
    q = question.lower()

    named = _find_named_entities(entities, question)

    if named:
        # Named-entity path: pull real lineage for each mentioned asset
        # so the model can reason about actual downstream consequences.
        asset_context = []
        for e in named[:3]:  # cap -- a question shouldn't name more than a couple assets
            lineage = await client.get_lineage(e["urn"])
            asset_context.append({
                "name": e.get("name"),
                "domain": e.get("domain"),
                "owner": e.get("owner"),
                "description": e.get("description") or "(no description recorded)",
                "tags": e.get("tags", []),
                "upstream": lineage.get("upstream", []),
                "downstream": lineage.get("downstream", []),
            })

        answer = await get_ai_provider().reason(
            system=(
                "You are a data reliability engineer answering a question about "
                "specific data asset(s) using their real catalog metadata and "
                "lineage, given below. The catalog does NOT record data-quality "
                "validation rules, constraints, or business logic -- if the "
                "question asks about something like that, say plainly that it "
                "isn't recorded, then reason about the likely consequence using "
                "what IS known: name the actual downstream datasets/dashboards "
                "from the lineage given and explain how bad data would propagate "
                "to them. Be concise (2-4 sentences). Clearly distinguish catalog "
                "fact from your own reasoning -- don't invent specific rules, "
                "owners, or figures that aren't in the data given."
            ),
            prompt=f"Question: {question}\n\nAsset(s) and their metadata + lineage:\n{asset_context}",
        )
        return {"question": question, "matches": asset_context, "answer": answer}

    # Catalog-aggregate path (unchanged behavior for "which X lack Y" style questions)
    matches = entities
    if "owner" in q and ("no owner" in q or "lack" in q or "missing" in q or "without" in q):
        matches = [e for e in matches if "owner" in e and not e.get("owner")]
    if "pii" in q:
        matches = [e for e in matches if e.get("contains_pii") or "PII" in e.get("tags", [])]
    if "stale" in q or "fresh" in q:
        matches = [e for e in matches if "expected_freshness_hours" in e]
    if "fail" in q or "broken" in q:
        matches = [e for e in matches if e.get("last_run_status") in ("FAILED", "DEGRADED")]
    for domain in ("finance", "marketing", "ml platform", "ml"):
        if domain in q:
            matches = [e for e in matches if e.get("domain", "").lower().startswith(domain[:2])]

    summary_rows = [
        {k: e.get(k) for k in ("name", "domain", "owner", "criticality", "last_run_status") if k in e}
        for e in matches
    ]

    answer = await get_ai_provider().reason(
        system=(
            "You answer questions about an organization's data catalog using "
            "only the rows provided. Be concise (2-4 sentences), name specific "
            "assets, and say 'none found' plainly if the list is empty. Never "
            "invent dataset names not in the provided rows."
        ),
        prompt=f"Question: {question}\nMatching rows: {summary_rows}",
    )

    return {"question": question, "matches": summary_rows, "answer": answer}
