import type { Finding, HealthScore, InvestigationResult, RemediationItem, RootCauseResult, SystemInfo } from './types';

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  systemInfo: () => fetch('/api/system-info').then(j<SystemInfo>),
  healthScore: () => fetch('/api/health-score').then(j<HealthScore>),
  findings: () => fetch('/api/findings').then(j<{ count: number; findings: Finding[] }>),
  rootCause: (urn: string) =>
    fetch(`/api/root-cause/${encodeURIComponent(urn)}`).then(j<RootCauseResult>),
  query: (question: string) =>
    fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }).then(j<{ question: string; matches: unknown[]; answer: string }>),
  applyAction: (urn: string, action: string, value: string | string[]) =>
    fetch('/api/actions/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urn, action, value }),
    }).then(j<{ ok: boolean; error?: string }>),
  investigate: (urn: string) =>
    fetch(`/api/investigate/${encodeURIComponent(urn)}`).then(j<InvestigationResult>),
  applyBatch: (items: RemediationItem[]) =>
    fetch('/api/actions/apply-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items }),
    }).then(j<{ results: { ok: boolean; error?: string }[]; applied: number }>),
};
