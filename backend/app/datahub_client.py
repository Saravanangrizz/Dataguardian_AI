"""
DataHubClient is the single seam between DataGuardian AI and DataHub.

Two implementations share one interface:
  - MockDataHubClient  -> serves sample_data.py, zero setup required
  - LiveDataHubClient  -> talks to a real DataHub instance via the
                          official acryl-datahub SDK (DataHubGraph),
                          with write-back gated by DATAHUB_WRITE_ENABLED

Every route in the app depends on `get_datahub_client()`, so switching
DATAHUB_MODE in the environment is the only change needed to go from
demo data to a live instance.
"""
from __future__ import annotations
import asyncio
import copy
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app import sample_data as sd


class DataHubClient:
    """Interface both implementations satisfy."""

    async def list_entities(self) -> list[dict]:
        raise NotImplementedError

    async def get_entity(self, urn: str) -> Optional[dict]:
        raise NotImplementedError

    async def get_lineage(self, urn: str) -> dict:
        raise NotImplementedError

    async def write_owner(self, urn: str, owner: str) -> dict:
        raise NotImplementedError

    async def write_description(self, urn: str, description: str) -> dict:
        raise NotImplementedError

    async def write_tags(self, urn: str, tags: list[str]) -> dict:
        raise NotImplementedError


class MockDataHubClient(DataHubClient):
    """In-memory demo data. Mutations persist for the life of the process
    so a demo can show "before -> agent acts -> after" without a real DB."""

    def __init__(self):
        self._datasets = copy.deepcopy(sd.DATASETS)
        self._pipelines = copy.deepcopy(sd.PIPELINES)
        self._dashboards = copy.deepcopy(sd.DASHBOARDS)
        self._index = {d["urn"]: d for d in self._datasets}
        self._index.update({p["urn"]: p for p in self._pipelines})
        self._index.update({d["urn"]: d for d in self._dashboards})
        self._audit_log: list[dict] = []

    async def list_entities(self) -> list[dict]:
        return list(self._index.values())

    async def get_entity(self, urn: str) -> Optional[dict]:
        return self._index.get(urn)

    async def get_lineage(self, urn: str) -> dict:
        upstream = [u for u, d in sd.LINEAGE_EDGES if d == urn]
        downstream = [d for u, d in sd.LINEAGE_EDGES if u == urn]
        return {"urn": urn, "upstream": upstream, "downstream": downstream}

    async def _record(self, urn: str, action: str, detail: str):
        self._audit_log.append({
            "urn": urn, "action": action, "detail": detail,
            "at": datetime.now(timezone.utc).isoformat(),
        })

    async def write_owner(self, urn: str, owner: str) -> dict:
        entity = self._index.get(urn)
        if not entity:
            return {"ok": False, "error": "entity not found"}
        entity["owner"] = owner
        await self._record(urn, "assign_owner", owner)
        return {"ok": True, "urn": urn, "owner": owner}

    async def write_description(self, urn: str, description: str) -> dict:
        entity = self._index.get(urn)
        if not entity:
            return {"ok": False, "error": "entity not found"}
        entity["description"] = description
        await self._record(urn, "update_description", description)
        return {"ok": True, "urn": urn, "description": description}

    async def write_tags(self, urn: str, tags: list[str]) -> dict:
        entity = self._index.get(urn)
        if not entity:
            return {"ok": False, "error": "entity not found"}
        existing = set(entity.get("tags", []))
        existing.update(tags)
        entity["tags"] = sorted(existing)
        await self._record(urn, "add_tags", ", ".join(tags))
        return {"ok": True, "urn": urn, "tags": entity["tags"]}

    def audit_log(self) -> list[dict]:
        return self._audit_log


class LiveDataHubClient(DataHubClient):
    """Talks to a real DataHub instance via the official `acryl-datahub`
    Python SDK (`DataHubGraph`) rather than hand-rolled GraphQL.

    Why the SDK instead of raw HTTP: DataHubGraph's methods (get_ownership,
    get_tags, get_aspect, emit_mcp, ...) are typed against DataHub's actual
    generated schema classes (OwnershipClass, GlobalTagsClass, ...), so the
    shapes below were copied from `inspect.signature()` on the installed
    package, not guessed from docs that can drift between versions. This
    is the same approach DataHub's own tutorials use for programmatic
    metadata management.

    DataHubGraph's calls are synchronous (blocking HTTP under the hood),
    so every method here runs the real work via `asyncio.to_thread` to
    avoid blocking the FastAPI event loop while still satisfying the
    async DataHubClient interface every route depends on.

    Scope: only Dataset entities are mapped (matches sample_data.py's
    model). Pipelines/dashboards read fine via get_lineage for tracing,
    but aren't hydrated into the reliability/governance field shape --
    same gap called out in the previous httpx-based version, carried
    forward rather than silently dropped.

    Concepts DataGuardian AI invented that DataHub has no native field
    for -- `criticality`, `expected_freshness_hours`, `last_run_status`
    -- are defaulted conservatively (see `_map_dataset_sync`) rather than
    guessed at. Wire these to DataHub Structured Properties or your
    ingestion pipeline's own signals for real values; until then, live
    findings lean on ownership/documentation/tag gaps, which ARE real
    DataHub fields read directly off your instance.
    """

    def __init__(self):
        settings = get_settings()
        from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig

        self._graph = DataHubGraph(
            DatahubClientConfig(
                server=settings.datahub_gms_url,
                token=settings.datahub_token or None,
                # The SDK's defaults for these are None, which in practice
                # means "retry indefinitely" -- confirmed by testing this
                # against an unreachable host, which hung for 15+ seconds
                # rather than failing. Set explicit fail-fast values so a
                # DataHub outage surfaces as a quick error, not a frozen UI.
                timeout_sec=10,
                retry_max_times=1,
            )
        )
        self.write_enabled = settings.datahub_write_enabled

    # ---- read path -----------------------------------------------------

    def _map_dataset_sync(self, urn: str) -> Optional[dict]:
        from datahub.metadata.schema_classes import DatasetPropertiesClass, EditableDatasetPropertiesClass

        props = self._graph.get_aspect(urn, DatasetPropertiesClass)
        if props is None:
            return None  # not a dataset, or doesn't exist

        editable = self._graph.get_aspect(urn, EditableDatasetPropertiesClass)
        ownership = self._graph.get_ownership(urn)
        tags_aspect = self._graph.get_tags(urn)

        owner = ownership.owners[0].owner if ownership and ownership.owners else None
        tags = [t.tag.split(":")[-1] for t in (tags_aspect.tags if tags_aspect else [])]
        description = (editable.description if editable and editable.description else None) or props.description or ""

        return {
            "urn": urn,
            "name": props.name or urn,
            "domain": "Unclassified",  # TODO: resolve via graph.get_aspect(urn, DomainsClass) once assets have domains
            "owner": owner,
            "description": description,
            "tags": tags,
            "criticality": "MEDIUM",  # no native DataHub field -- map to a Structured Property if you have one
            "glossary_terms": [],
            "contains_pii": any("pii" in t.lower() for t in tags),
        }

    async def list_entities(self) -> list[dict]:
        def _sync():
            # list_all_entity_urns swallows connection/auth errors internally
            # and returns None on failure (confirmed by reading the installed
            # SDK's source) rather than raising. Left unchecked, that would
            # silently present "0 datasets" as if the catalog were simply
            # empty and healthy, instead of surfacing that DataHub is
            # actually unreachable/misconfigured.
            urns = self._graph.list_all_entity_urns("dataset", 0, 200)
            if urns is None:
                raise RuntimeError(
                    "DataHub returned no entity list. This usually means the "
                    "connection or auth failed silently -- check DATAHUB_GMS_URL "
                    "and DATAHUB_TOKEN, and run scripts/check_live_connection.py."
                )
            entities = [self._map_dataset_sync(u) for u in urns]
            return [e for e in entities if e is not None]

        return await asyncio.to_thread(_sync)

    async def get_entity(self, urn: str) -> Optional[dict]:
        return await asyncio.to_thread(self._map_dataset_sync, urn)

    # searchAcrossLineage GraphQL query, confirmed against DataHub's own
    # docs (docs.datahub.com/docs/api/graphql/graphql-best-practices) --
    # NOT the newer OpenAPI v3 `scroll_lineage()` SDK method, which 404'd
    # against a real instance (confirmed by the user hitting exactly that:
    # `POST /openapi/v3/lineage/scroll` -> 404 Not Found). GraphQL's
    # searchAcrossLineage has been part of DataHub's API surface far
    # longer and is much more likely to exist on whatever version is
    # actually running. degree=1 restricts to immediate neighbors, which
    # matches how this client's callers (root_cause.py's hop-by-hop walk,
    # lineage_investigator.py) already expect get_lineage to behave --
    # one hop per call, not a transitive closure.
    _LINEAGE_QUERY = """
    query getLineage($urn: String!, $direction: LineageDirection!) {
      searchAcrossLineage(
        input: {
          urn: $urn
          query: "*"
          count: 50
          start: 0
          direction: $direction
          orFilters: [{ and: [{ field: "degree", condition: EQUAL, values: ["1"] }] }]
        }
      ) {
        searchResults {
          entity { urn }
        }
      }
    }
    """

    async def get_lineage(self, urn: str) -> dict:
        def _one_direction(direction: str) -> list[str]:
            # strip_unsupported_fields=True: defensive against exactly the
            # class of bug that broke scroll_lineage -- if this server's
            # schema is missing something the query asks for, drop it and
            # still return what's available rather than hard-failing.
            data = self._graph.execute_graphql(
                self._LINEAGE_QUERY,
                {"urn": urn, "direction": direction},
                strip_unsupported_fields=True,
            )
            results = (data.get("searchAcrossLineage") or {}).get("searchResults") or []
            return [r["entity"]["urn"] for r in results if r.get("entity", {}).get("urn")]

        def _sync():
            upstream = _one_direction("UPSTREAM")
            downstream = _one_direction("DOWNSTREAM")
            return {"urn": urn, "upstream": upstream, "downstream": downstream}

        return await asyncio.to_thread(_sync)

    # ---- write-back path -------------------------------------------------
    # Each write reads the existing aspect first and merges into it, rather
    # than emitting a bare new one -- MCP aspect emission replaces the whole
    # aspect, so a naive write would silently wipe out any owners/tags a
    # human already set in the DataHub UI.

    @staticmethod
    def _owner_urn(owner: str) -> str:
        if owner.startswith("urn:li:"):
            return owner
        local_part = owner.split("@")[0]
        return f"urn:li:corpuser:{local_part}"

    async def write_owner(self, urn: str, owner: str) -> dict:
        if not self.write_enabled:
            return {"ok": False, "error": "DATAHUB_WRITE_ENABLED is false"}

        def _sync():
            from datahub.metadata.schema_classes import OwnershipClass, OwnerClass, OwnershipTypeClass
            from datahub.emitter.mcp import MetadataChangeProposalWrapper

            owner_urn = self._owner_urn(owner)
            existing = self._graph.get_ownership(urn)
            owners = list(existing.owners) if existing and existing.owners else []
            if not any(o.owner == owner_urn for o in owners):
                owners.append(OwnerClass(owner=owner_urn, type=OwnershipTypeClass.TECHNICAL_OWNER))
            self._graph.emit_mcp(
                MetadataChangeProposalWrapper(entityUrn=urn, aspect=OwnershipClass(owners=owners))
            )

        try:
            await asyncio.to_thread(_sync)
            return {"ok": True, "urn": urn, "owner": owner}
        except Exception as e:  # surface the real DataHub error instead of a stack trace
            return {"ok": False, "error": str(e)}

    async def write_description(self, urn: str, description: str) -> dict:
        if not self.write_enabled:
            return {"ok": False, "error": "DATAHUB_WRITE_ENABLED is false"}

        def _sync():
            from datahub.metadata.schema_classes import EditableDatasetPropertiesClass
            from datahub.emitter.mcp import MetadataChangeProposalWrapper

            existing = self._graph.get_aspect(urn, EditableDatasetPropertiesClass)
            aspect = EditableDatasetPropertiesClass(
                description=description,
                name=existing.name if existing else None,
            )
            self._graph.emit_mcp(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))

        try:
            await asyncio.to_thread(_sync)
            return {"ok": True, "urn": urn, "description": description}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def write_tags(self, urn: str, tags: list[str]) -> dict:
        if not self.write_enabled:
            return {"ok": False, "error": "DATAHUB_WRITE_ENABLED is false"}

        def _sync():
            from datahub.metadata.schema_classes import GlobalTagsClass, TagAssociationClass
            from datahub.emitter.mcp import MetadataChangeProposalWrapper

            existing = self._graph.get_tags(urn)
            current = list(existing.tags) if existing and existing.tags else []
            current_urns = {t.tag for t in current}
            for t in tags:
                tag_urn = t if t.startswith("urn:li:tag:") else f"urn:li:tag:{t}"
                if tag_urn not in current_urns:
                    current.append(TagAssociationClass(tag=tag_urn))
            self._graph.emit_mcp(MetadataChangeProposalWrapper(entityUrn=urn, aspect=GlobalTagsClass(tags=current)))

        try:
            await asyncio.to_thread(_sync)
            return {"ok": True, "urn": urn, "tags": tags}
        except Exception as e:
            return {"ok": False, "error": str(e)}


_client_singleton: Optional[DataHubClient] = None


def get_datahub_client() -> DataHubClient:
    global _client_singleton
    if _client_singleton is None:
        settings = get_settings()
        _client_singleton = (
            LiveDataHubClient() if settings.datahub_mode == "live" else MockDataHubClient()
        )
    return _client_singleton
