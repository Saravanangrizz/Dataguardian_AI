export type Severity = 'critical' | 'high' | 'medium';

export interface Finding {
  type: 'reliability' | 'governance';
  severity: Severity;
  urn: string;
  name: string;
  title: string;
  evidence: string;
  confidence: number;
  downstream?: string[];
  reasoning: string;
  reasoning_source: string;
  suggested_action: 'assign_owner' | 'update_description' | 'add_tags' | 'investigate_pipeline' | 'review_pipeline_run';
  suggested_value?: string | string[];
}

export interface HealthScore {
  overall: number;
  breakdown: Record<string, number>;
}

export interface RootCauseHop {
  urn: string;
  label: string;
  note: string | null;
}

export interface RootCauseResult {
  urn: string;
  chain: RootCauseHop[];
  explanation: string;
  reasoning_source: string;
}

export interface AgentStage {
  agent: string;
  summary: string;
  severity?: string;
  downstream?: { urn: string; name: string; kind: string; resolved: boolean; viewers_last_30d?: number }[];
  upstream?: { urn: string; name: string; kind: string; resolved: boolean }[];
}

export interface TimelineEvent {
  when_hours_ago: number | null;
  label: string;
}

export interface RemediationItem {
  action: string;
  label: string;
  value: string | string[];
  urn: string;
}

export interface InvestigationResult {
  urn: string;
  entity_name: string;
  stages: AgentStage[];
  timeline: TimelineEvent[];
  remediation_plan: RemediationItem[];
  business_impact: string;
  executive_summary: string;
  error?: string;
}

export interface SystemInfo {
  datahub_mode: string;
  ai_provider_requested: string;
  ai_provider: string;
  write_enabled: boolean;
  ai_provider_fallback_reason?: string;
}
