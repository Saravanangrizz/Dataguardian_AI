import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { Finding, HealthScore, SystemInfo } from './types';
import { HealthPanel } from './components/HealthPanel';
import { FindingsLedger } from './components/FindingsLedger';
import { QueryConsole } from './components/QueryConsole';
import { CaseBoard } from './components/CaseBoard';
import { InvestigationBoard } from './components/InvestigationBoard';

export default function App() {
  const [health, setHealth] = useState<HealthScore | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [lineageUrn, setLineageUrn] = useState<string | null>(null);
  const [investigateUrn, setInvestigateUrn] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);
  const didInitialFetch = useRef(false);

  function refresh() {
    Promise.all([api.healthScore(), api.findings(), api.systemInfo()])
      .then(([h, f, s]) => {
        setHealth(h);
        setFindings(f.findings);
        setSystem(s);
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
  }

  useEffect(() => {
    // React 18 StrictMode intentionally double-invokes effects in dev to
    // surface side-effect bugs -- without this guard, every dev page load
    // fires the initial fetch (and everything downstream of it, including
    // AI narrative calls) twice. The backend's CachingProvider makes the
    // second call harmless for AI quota either way, but this avoids the
    // redundant DataHub reads and HTTP round-trip too.
    if (didInitialFetch.current) return;
    didInitialFetch.current = true;
    refresh();
  }, []);

  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--hairline)] px-8 py-6 flex items-center justify-between">
        <div>
          <div className="font-mono text-xs uppercase tracking-[0.2em] text-[var(--paper-dim)]">
            DataGuardian AI
          </div>
          <h1 className="font-display text-2xl mt-0.5">Metadata Reliability Ledger</h1>
        </div>
        {system && (
          <div className="font-mono text-xs text-[var(--paper-dim)] text-right leading-relaxed">
            <div>datahub: {system.datahub_mode}</div>
            <div>
              reasoning: {system.ai_provider}
              {system.ai_provider !== system.ai_provider_requested && (
                <span style={{ color: 'var(--stamp-high)' }}> (requested {system.ai_provider_requested}, fell back)</span>
              )}
            </div>
          </div>
        )}
      </header>

      {system?.ai_provider_fallback_reason && (
        <div className="mx-8 mt-6 border border-[var(--stamp-high)] text-[var(--stamp-high)] rounded-sm px-4 py-3 font-mono text-xs">
          AI provider fell back to heuristic: {system.ai_provider_fallback_reason}
        </div>
      )}

      {loadError && (
        <div className="mx-8 mt-6 border border-[var(--stamp-critical)] text-[var(--stamp-critical)] rounded-sm px-4 py-3 font-mono text-sm">
          Could not reach the backend at /api. Is `uvicorn app.main:app` running on port 8010?
        </div>
      )}

      <main className="max-w-6xl mx-auto px-8 py-8 grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-6 items-start">
        <div className="space-y-6">
          <HealthPanel health={health} />
          <FindingsLedger
            findings={findings}
            onOpenLineage={setLineageUrn}
            onInvestigate={setInvestigateUrn}
          />
        </div>
        <div className="h-[520px]">
          <QueryConsole />
        </div>
      </main>

      <footer className="perforated mx-8 mt-4" />
      <div className="text-center font-mono text-xs text-[var(--paper-dim)] py-6">
        Built for Build with DataHub: The Agent Hackathon
      </div>

      {lineageUrn && <CaseBoard urn={lineageUrn} onClose={() => setLineageUrn(null)} />}
      {investigateUrn && (
        <InvestigationBoard
          urn={investigateUrn}
          onClose={() => {
            setInvestigateUrn(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}
