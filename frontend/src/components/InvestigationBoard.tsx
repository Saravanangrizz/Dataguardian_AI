import { useEffect, useState } from 'react';
import { api } from '../api';
import type { InvestigationResult, RemediationItem } from '../types';

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'var(--stamp-critical)',
  high: 'var(--stamp-high)',
  ok: 'var(--stamp-ok)',
};

function AgentStageRow({ stage, index }: { stage: InvestigationResult['stages'][number]; index: number }) {
  const color = stage.severity ? SEVERITY_COLOR[stage.severity] ?? 'var(--paper-dim)' : 'var(--paper-dim)';
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <span
          className="w-6 h-6 rounded-full border-2 flex items-center justify-center font-mono text-[0.65rem] shrink-0"
          style={{ borderColor: color, color }}
        >
          {index + 1}
        </span>
        <span className="flex-1 w-px my-1" style={{ background: 'var(--hairline)' }} />
      </div>
      <div className="pb-5">
        <div className="font-display text-base">{stage.agent}</div>
        <p className="text-sm text-[var(--paper)] mt-0.5">{stage.summary}</p>
      </div>
    </div>
  );
}

function Timeline({ events }: { events: InvestigationResult['timeline'] }) {
  return (
    <div className="space-y-2">
      {events.map((e, i) => (
        <div key={i} className="flex items-center gap-3 text-sm">
          <span className="font-mono text-xs text-[var(--paper-dim)] w-20 shrink-0 text-right">
            {e.when_hours_ago === null ? '' : e.when_hours_ago === 0 ? 'now' : `${Math.round(e.when_hours_ago)}h ago`}
          </span>
          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: 'var(--thread)' }} />
          <span>{e.label}</span>
        </div>
      ))}
    </div>
  );
}

function RemediationReview({
  urn,
  plan,
  onApplied,
}: {
  urn: string;
  plan: RemediationItem[];
  onApplied: () => void;
}) {
  const [checked, setChecked] = useState<Set<number>>(new Set(plan.map((_, i) => i)));
  const [applyState, setApplyState] = useState<'idle' | 'applying' | 'applied' | 'partial' | 'error'>('idle');
  const [itemErrors, setItemErrors] = useState<Record<number, string>>({});

  if (plan.length === 0) {
    return <p className="text-sm text-[var(--paper-dim)] font-mono">No remediation needed — nothing to approve.</p>;
  }

  async function approve() {
    setApplyState('applying');
    setItemErrors({});
    const indices = [...checked];
    const items = indices.map((i) => plan[i]);
    try {
      const res = await api.applyBatch(items);
      const failed: Record<number, string> = {};
      res.results.forEach((r, j) => {
        if (!r.ok) failed[indices[j]] = r.error ?? 'failed';
      });
      setItemErrors(failed);
      if (Object.keys(failed).length === 0) {
        setApplyState('applied');
      } else if (Object.keys(failed).length < items.length) {
        setApplyState('partial');
      } else {
        setApplyState('error');
      }
      onApplied();
    } catch (e) {
      setApplyState('error');
      setItemErrors(Object.fromEntries(indices.map((i) => [i, e instanceof Error ? e.message : 'Request failed'])));
    }
  }

  const done = applyState === 'applied' || applyState === 'partial' || applyState === 'error';

  return (
    <div>
      <div className="space-y-2 mb-4">
        {plan.map((item, i) => {
          const failed = itemErrors[i];
          const succeeded = done && checked.has(i) && !failed;
          return (
            <label key={i} className="flex items-center gap-3 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={checked.has(i)}
                disabled={done}
                onChange={() =>
                  setChecked((prev) => {
                    const next = new Set(prev);
                    next.has(i) ? next.delete(i) : next.add(i);
                    return next;
                  })
                }
                className="accent-[var(--stamp-ok)]"
              />
              <span className={succeeded ? 'text-[var(--paper-dim)] line-through' : ''}>{item.label}</span>
              <span className="font-mono text-xs text-[var(--paper-dim)] truncate">
                {Array.isArray(item.value) ? item.value.join(', ') : item.value}
              </span>
              {failed && (
                <span className="font-mono text-xs" style={{ color: 'var(--stamp-critical)' }}>
                  failed: {failed}
                </span>
              )}
            </label>
          );
        })}
      </div>
      <button
        onClick={approve}
        disabled={applyState === 'applying' || applyState === 'applied' || checked.size === 0}
        className="font-mono text-xs rounded-sm px-4 py-2 border transition-colors disabled:opacity-60"
        style={{
          borderColor: applyState === 'applied' ? 'var(--stamp-ok)' : applyState === 'error' || applyState === 'partial' ? 'var(--stamp-critical)' : 'var(--thread)',
          color: applyState === 'applied' ? 'var(--stamp-ok)' : applyState === 'error' || applyState === 'partial' ? 'var(--stamp-critical)' : 'var(--paper)',
        }}
      >
        {applyState === 'applied'
          ? `Applied to DataHub ✓ (${urn.split(',').pop()?.replace(')', '')})`
          : applyState === 'partial'
          ? 'Some updates failed — see above'
          : applyState === 'error'
          ? 'Failed — see errors above, retry?'
          : applyState === 'applying'
          ? 'Writing to DataHub…'
          : `Approve ${checked.size} update${checked.size === 1 ? '' : 's'} → DataHub`}
      </button>
    </div>
  );
}

export function InvestigationBoard({ urn, onClose }: { urn: string; onClose: () => void }) {
  const [result, setResult] = useState<InvestigationResult | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    setResult(null);
    api.investigate(urn).then(setResult).catch(() => setResult({ urn, entity_name: urn, stages: [], timeline: [], remediation_plan: [], business_impact: '', executive_summary: '', error: 'failed to load' }));
  }, [urn, refreshTick]);

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-6">
      <div className="bg-[var(--surface)] border border-[var(--hairline)] rounded-sm w-full max-w-3xl max-h-[88vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-[var(--hairline)] flex items-center justify-between sticky top-0 bg-[var(--surface)]">
          <div>
            <div className="font-mono text-xs uppercase tracking-widest text-[var(--paper-dim)]">Investigation</div>
            <h2 className="font-display text-xl mt-0.5">{result?.entity_name ?? urn}</h2>
          </div>
          <button onClick={onClose} className="font-mono text-xs text-[var(--paper-dim)] hover:text-[var(--paper)]">
            close ✕
          </button>
        </div>

        {!result ? (
          <div className="px-6 py-10 font-mono text-xs text-[var(--paper-dim)]">
            running Reliability Engineer → Lineage Investigator → Governance Officer → Business Impact Advisor → Executive Summary…
          </div>
        ) : result.error ? (
          <div className="px-6 py-10 text-sm" style={{ color: 'var(--stamp-critical)' }}>{result.error}</div>
        ) : (
          <div className="px-6 py-6 space-y-8">
            <section>
              <h3 className="font-mono text-xs uppercase tracking-widest text-[var(--paper-dim)] mb-4">
                Agent collaboration chain
              </h3>
              {result.stages.map((s, i) => (
                <AgentStageRow key={s.agent} stage={s} index={i} />
              ))}
            </section>

            <section>
              <h3 className="font-mono text-xs uppercase tracking-widest text-[var(--paper-dim)] mb-3">
                Incident timeline
              </h3>
              <Timeline events={result.timeline} />
            </section>

            <section className="border-l-2 pl-4" style={{ borderColor: 'var(--stamp-high)' }}>
              <h3 className="font-mono text-xs uppercase tracking-widest text-[var(--paper-dim)] mb-2">
                Business impact
              </h3>
              <p className="text-sm">{result.business_impact}</p>
            </section>

            <section className="border-l-2 pl-4" style={{ borderColor: 'var(--thread)' }}>
              <h3 className="font-mono text-xs uppercase tracking-widest text-[var(--paper-dim)] mb-2">
                Executive summary
              </h3>
              <p className="text-sm">{result.executive_summary}</p>
            </section>

            <section>
              <h3 className="font-mono text-xs uppercase tracking-widest text-[var(--paper-dim)] mb-3">
                Suggested updates — review before writing to DataHub
              </h3>
              <RemediationReview urn={urn} plan={result.remediation_plan} onApplied={() => setRefreshTick((t) => t + 1)} />
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
