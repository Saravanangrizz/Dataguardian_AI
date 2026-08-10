import type { HealthScore } from '../types';

function scoreColor(v: number) {
  if (v >= 80) return 'var(--stamp-ok)';
  if (v >= 60) return 'var(--stamp-high)';
  return 'var(--stamp-critical)';
}

const LABELS: Record<string, string> = {
  ownership: 'Ownership coverage',
  documentation: 'Documentation coverage',
  freshness: 'Freshness',
  governance: 'Governance / PII hygiene',
  reliability: 'Pipeline reliability',
};

export function HealthPanel({ health }: { health: HealthScore | null }) {
  if (!health) {
    return (
      <div className="border border-[var(--hairline)] rounded-sm p-6 font-mono text-sm text-[var(--paper-dim)]">
        reading ledger…
      </div>
    );
  }

  return (
    <div className="border border-[var(--hairline)] rounded-sm bg-[var(--surface)] p-6">
      <div className="flex items-baseline justify-between mb-5">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-[var(--paper-dim)]">
            Organization Health — Case No. 2607-24
          </div>
          <div className="font-display text-5xl mt-1" style={{ color: scoreColor(health.overall) }}>
            {health.overall}
            <span className="text-lg text-[var(--paper-dim)] font-mono"> /100</span>
          </div>
        </div>
        <div className="stamp" style={{ color: scoreColor(health.overall) }}>
          {health.overall >= 80 ? 'in order' : health.overall >= 60 ? 'needs attention' : 'at risk'}
        </div>
      </div>

      <div className="space-y-3">
        {Object.entries(health.breakdown).map(([key, val]) => (
          <div key={key} className="grid grid-cols-[180px_1fr_44px] items-center gap-3">
            <span className="text-sm text-[var(--paper-dim)]">{LABELS[key] ?? key}</span>
            <div className="h-2 bg-[var(--hairline)] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{ width: `${val}%`, background: scoreColor(val) }}
              />
            </div>
            <span className="font-mono text-sm text-right" style={{ color: scoreColor(val) }}>
              {val}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
