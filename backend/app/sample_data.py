"""
Deterministic sample metadata that mirrors the shape of what DataHub's
GraphQL API / MCP server returns (entities, ownership, lineage, freshness).
Used when DATAHUB_MODE=mock so the whole app runs with zero setup.

Swap `datahub_client.py`'s LiveDataHubClient in for MockDataHubClient once
a real GMS instance + token are available; both expose the same interface.
"""
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)


def _hours_ago(h: int) -> str:
    return (NOW - timedelta(hours=h)).isoformat()


DATASETS = [
    {
        "urn": "urn:li:dataset:(finance.quarterly_revenue)",
        "name": "finance.quarterly_revenue",
        "domain": "Finance",
        "owner": None,
        "description": "",
        "tags": [],
        "criticality": "HIGH",
        "last_modified": _hours_ago(58),
        "expected_freshness_hours": 24,
        "glossary_terms": ["Revenue"],
        "contains_pii": False,
    },
    {
        "urn": "urn:li:dataset:(finance.customer_billing)",
        "name": "finance.customer_billing",
        "domain": "Finance",
        "owner": "finance-team@company.com",
        "description": "Monthly billing records per customer account.",
        "tags": ["PII"],
        "criticality": "CRITICAL",
        "last_modified": _hours_ago(3),
        "expected_freshness_hours": 24,
        "glossary_terms": ["Billing", "PII"],
        "contains_pii": True,
    },
    {
        "urn": "urn:li:dataset:(marketing.campaign_events)",
        "name": "marketing.campaign_events",
        "domain": "Marketing",
        "owner": "growth-team@company.com",
        "description": "Raw campaign click/impression events.",
        "tags": [],
        "criticality": "MEDIUM",
        "last_modified": _hours_ago(2),
        "expected_freshness_hours": 6,
        "glossary_terms": [],
        "contains_pii": False,
    },
    {
        "urn": "urn:li:dataset:(ml.churn_features)",
        "name": "ml.churn_features",
        "domain": "ML Platform",
        "owner": None,
        "description": "Feature table feeding the churn prediction model.",
        "tags": [],
        "criticality": "HIGH",
        "last_modified": _hours_ago(30),
        "expected_freshness_hours": 12,
        "glossary_terms": [],
        "contains_pii": False,
    },
]

PIPELINES = [
    {
        "urn": "urn:li:dataFlow:(airflow,revenue_etl)",
        "name": "revenue_etl",
        "feeds": ["urn:li:dataset:(finance.quarterly_revenue)"],
        "last_run_status": "FAILED",
        "last_run_time": _hours_ago(58),
        "failure_reason": "Upstream schema change: column 'region_code' dropped from source.",
    },
    {
        "urn": "urn:li:dataFlow:(airflow,churn_feature_pipeline)",
        "name": "churn_feature_pipeline",
        "feeds": ["urn:li:dataset:(ml.churn_features)"],
        "last_run_status": "DEGRADED",
        "last_run_time": _hours_ago(30),
        "failure_reason": "Run time increased 4x over 7-day baseline; likely resource contention.",
    },
]

DASHBOARDS = [
    {
        "urn": "urn:li:dashboard:(looker,exec_revenue_dashboard)",
        "name": "Executive Revenue Dashboard",
        "consumes": ["urn:li:dataset:(finance.quarterly_revenue)"],
        "viewers_last_30d": 142,
    },
    {
        "urn": "urn:li:dashboard:(looker,churn_risk_dashboard)",
        "name": "Churn Risk Dashboard",
        "consumes": ["urn:li:dataset:(ml.churn_features)"],
        "viewers_last_30d": 34,
    },
]

# upstream -> downstream lineage edges (dataset/pipeline/dashboard urns)
LINEAGE_EDGES = [
    ("urn:li:dataset:(raw.sales_transactions)", "urn:li:dataFlow:(airflow,revenue_etl)"),
    ("urn:li:dataFlow:(airflow,revenue_etl)", "urn:li:dataset:(finance.quarterly_revenue)"),
    ("urn:li:dataset:(finance.quarterly_revenue)", "urn:li:dashboard:(looker,exec_revenue_dashboard)"),
    ("urn:li:dataset:(raw.user_events)", "urn:li:dataFlow:(airflow,churn_feature_pipeline)"),
    ("urn:li:dataFlow:(airflow,churn_feature_pipeline)", "urn:li:dataset:(ml.churn_features)"),
    ("urn:li:dataset:(ml.churn_features)", "urn:li:dashboard:(looker,churn_risk_dashboard)"),
]

ENTITY_INDEX = {d["urn"]: d for d in DATASETS}
ENTITY_INDEX.update({p["urn"]: p for p in PIPELINES})
ENTITY_INDEX.update({d["urn"]: d for d in DASHBOARDS})
