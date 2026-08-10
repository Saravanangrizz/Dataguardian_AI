import type {
  Finding,
  HealthScore,
  InvestigationResult,
  RemediationItem,
  RootCauseResult,
  SystemInfo
} from './types';

const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  systemInfo: () =>
    fetch(`${API_BASE_URL}/api/system-info`).then(j<SystemInfo>),

  healthScore: () =>
    fetch(`${API_BASE_URL}/api/health-score`).then(j<HealthScore>),

  findings: () =>
    fetch(`${API_BASE_URL}/api/findings`).then(
      j<{ count: number; findings: Finding[] }>
    ),

  rootCause: (urn: string) =>
    fetch(`${API_BASE_URL}/api/root-cause/${encodeURIComponent(urn)}`).then(
      j<RootCauseResult>
    ),

  query: (question: string) =>
    fetch(`${API_BASE_URL}/api/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }).then(
      j<{ question: string; matches: unknown[]; answer: string }>
    ),

  applyAction: (urn: string, action: string, value: string | string[]) =>
    fetch(`${API_BASE_URL}/api/actions/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urn, action, value }),
    }).then(
      j<{ ok: boolean; error?: string }>
    ),

  investigate: (urn: string) =>
    fetch(`${API_BASE_URL}/api/investigate/${encodeURIComponent(urn)}`).then(
      j<InvestigationResult>
    ),

  applyBatch: (items: RemediationItem[]) =>
    fetch(`${API_BASE_URL}/api/actions/apply-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items }),
    }).then(
      j<{ results: { ok: boolean; error?: string }[]; applied: number }>
    ),
};
