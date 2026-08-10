from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.datahub_client import DataHubClient, get_datahub_client, MockDataHubClient
from app.agents.reliability import analyze_reliability
from app.agents.governance import analyze_governance
from app.agents.root_cause import trace_root_cause
from app.agents.nlq import answer_query
from app.agents.pipeline import investigate
from app.health_score import compute_health_score

router = APIRouter()


@router.get("/health-score")
async def health_score(client: DataHubClient = Depends(get_datahub_client)):
    return await compute_health_score(client)


@router.get("/findings")
async def findings(client: DataHubClient = Depends(get_datahub_client)):
    reliability = await analyze_reliability(client)
    governance = await analyze_governance(client)
    combined = reliability + governance
    combined.sort(key=lambda f: {"critical": 0, "high": 1, "medium": 2}.get(f["severity"], 3))
    return {"count": len(combined), "findings": combined}


@router.get("/entities")
async def entities(client: DataHubClient = Depends(get_datahub_client)):
    return {"entities": await client.list_entities()}


@router.get("/lineage/{urn:path}")
async def lineage(urn: str, client: DataHubClient = Depends(get_datahub_client)):
    return await client.get_lineage(urn)


@router.get("/root-cause/{urn:path}")
async def root_cause(urn: str, client: DataHubClient = Depends(get_datahub_client)):
    return await trace_root_cause(client, urn)


class QueryRequest(BaseModel):
    question: str


@router.post("/query")
async def query(body: QueryRequest, client: DataHubClient = Depends(get_datahub_client)):
    return await answer_query(client, body.question)


class ActionRequest(BaseModel):
    urn: str
    action: str  # assign_owner | update_description | add_tags
    value: str | list[str]


@router.post("/actions/apply")
async def apply_action(body: ActionRequest, client: DataHubClient = Depends(get_datahub_client)):
    """The write-back path: takes a finding's suggested_action/suggested_value
    and pushes it into DataHub (mock store, or real GMS in live mode)."""
    if body.action == "assign_owner":
        result = await client.write_owner(body.urn, body.value)  # type: ignore
    elif body.action == "update_description":
        result = await client.write_description(body.urn, body.value)  # type: ignore
    elif body.action == "add_tags":
        tags = body.value if isinstance(body.value, list) else [body.value]
        result = await client.write_tags(body.urn, tags)
    else:
        raise HTTPException(400, f"Unknown action: {body.action}")
    return result


@router.get("/investigate/{urn:path}")
async def investigate_entity(urn: str, client: DataHubClient = Depends(get_datahub_client)):
    """Runs the full collaborative agent chain (Reliability -> Lineage ->
    Governance -> Business Impact -> Executive Summary) for one entity."""
    return await investigate(client, urn)


class BatchActionItem(BaseModel):
    urn: str
    action: str
    value: str | list[str]


class BatchActionRequest(BaseModel):
    items: list[BatchActionItem]


@router.post("/actions/apply-batch")
async def apply_batch(body: BatchActionRequest, client: DataHubClient = Depends(get_datahub_client)):
    """Applies an approved remediation plan (one or more actions) in one call,
    so the frontend's review-then-approve step commits atomically-ish rather
    than firing N separate requests."""
    results = []
    for item in body.items:
        if item.action == "assign_owner":
            results.append(await client.write_owner(item.urn, item.value))  # type: ignore
        elif item.action == "update_description":
            results.append(await client.write_description(item.urn, item.value))  # type: ignore
        elif item.action == "add_tags":
            tags = item.value if isinstance(item.value, list) else [item.value]
            results.append(await client.write_tags(item.urn, tags))
        else:
            results.append({"ok": False, "error": f"unknown action {item.action}"})
    return {"results": results, "applied": sum(1 for r in results if r.get("ok"))}


@router.get("/audit-log")
async def audit_log(client: DataHubClient = Depends(get_datahub_client)):
    if isinstance(client, MockDataHubClient):
        return {"log": client.audit_log()}
    return {"log": [], "note": "audit log only tracked in mock mode in this MVP"}
