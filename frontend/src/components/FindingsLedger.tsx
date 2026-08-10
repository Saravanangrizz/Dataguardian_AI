import { useState } from 'react';
import type { Finding } from '../types';
import { api } from '../api';

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'var(--stamp-critical)',
  high: 'var(--stamp-high)',
  medium: 'var(--stamp-medium)',
};

const ACTION_LABEL: Record<string, string> = {
  assign_owner: 'Assign owner',
  update_description: 'Write description',
  add_tags: 'Apply tags',
  investigate_pipeline: 'Flag for investigation',
  review_pipeline_run: 'Flag for investigation',
};

function FindingRow({
  finding,
  onOpenLineage,
  onInvestigate,
}: {
  finding: Finding;
  onOpenLineage: (urn: string) => void;
  onInvestigate: (urn: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [applyState, setApplyState] = useState<'idle' | 'applying' | 'applied' | 'error'>('idle');
  const [applyError, setApplyError] = useState<string | null>(null);
  const color = SEVERITY_COLOR[finding.severity];
  const canWriteBack = ['assign_owner', 'update_description', 'add_tags'].includes(
    finding.suggested_action
  );

  async function apply() {
    if (!finding.suggested_value) return;
    setApplyState('applying');
    setApplyError(null);
    try {
      const result = await api.applyAction(finding.urn, finding.suggested_action, finding.suggested_value);
      if (result.ok) {
        setApplyState('applied');
      } else {
        setApplyState('error');
        setApplyError((result as { error?: string }).error ?? 'DataHub rejected the write');
      }
    } catch (e) {
      setApplyState('error');
      setApplyError(e instanceof Error ? e.message : 'Request failed');
    }
  }

  return (
    <div className="border-b border-[var(--hairline)]">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left px-5 py-4 flex items-start gap-4 hover:bg-[var(--surface-raised)] transition-colors"
      >
        <span className="stamp shrink-0 mt-0.5" style={{ color }}>
          {finding.severity}
        </span>
        <div className="flex-1 min-w-0">
          <div className="font-display text-lg leading-snug">{finding.title}</div>
          <div className="font-mono text-xs text-[var(--paper-dim)] mt-1 truncate">
            {finding.urn} · confidence {(finding.confidence * 100).toFixed(0)}%
          </div>
        </div>
        <span className="font-mono text-xs text-[var(--paper-dim)] mt-1">{open ? '−' : '+'}</span>
      </button>

      {open && (
        <div className="px-5 pb-5 pl-[3.25rem] space-y-4 text-sm">
          <div>
            <div className="font-mono text-xs uppercase tracking-wider text-[var(--paper-dim)] mb-1">
              Evidence
            </div>
            <p className="text-[var(--paper)]">{finding.evidence}</p>
          </div>
          <div>
            <div className="font-mono text-xs uppercase tracking-wider text-[var(--paper-dim)] mb-1">
              Reasoning ({finding.reasoning_source})
            </div>
            <p className="text-[var(--paper)]">{finding.reasoning}</p>
          </div>
          <div className="flex flex-wrap gap-3 pt-1">
            <button
              onClick={() => onInvestigate(finding.urn)}
              className="text-xs font-mono border rounded-sm px-3 py-1.5 transition-colors"
              style={{ borderColor: color, color }}
            >
              Run full investigation
            </button>
            {finding.downstream && finding.downstream.length > 0 && (
              <button
                onClick={() => onOpenLineage(finding.urn)}
                className="text-xs font-mono border border-[var(--hairline)] rounded-sm px-3 py-1.5 hover:border-[var(--thread)] transition-colors"
              >
                Trace downstream ({finding.downstream.length})
              </button>
            )}
            {canWriteBack && (
              <div className="flex items-center gap-2">
                <button
                  onClick={apply}
                  disabled={applyState === 'applying' || applyState === 'applied'}
                  className="text-xs font-mono rounded-sm px-3 py-1.5 border transition-colors disabled:opacity-60"
                  style={{
                    borderColor: applyState === 'applied' ? 'var(--stamp-ok)' : applyState === 'error' ? 'var(--stamp-critical)' : color,
                    color: applyState === 'applied' ? 'var(--stamp-ok)' : applyState === 'error' ? 'var(--stamp-critical)' : color,
                  }}
                >
                  {applyState === 'applied'
                    ? 'Written to DataHub ✓'
                    : applyState === 'applying'
                    ? 'Writing…'
                    : applyState === 'error'
                    ? 'Failed — retry'
                    : `${ACTION_LABEL[finding.suggested_action]} → DataHub`}
                </button>
                {applyState === 'error' && applyError && (
                  <span className="text-xs font-mono" style={{ color: 'var(--stamp-critical)' }}>
                    {applyError}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function FindingsLedger({
  findings,
  onOpenLineage,
  onInvestigate,
}: {
  findings: Finding[];
  onOpenLineage: (urn: string) => void;
  onInvestigate: (urn: string) => void;
}) {
  return (
    <div className="border border-[var(--hairline)] rounded-sm bg-[var(--surface)]">
      <div className="px-5 py-4 border-b border-[var(--hairline)] flex items-center justify-between">
        <h2 className="font-display text-xl">Findings ledger</h2>
        <span className="font-mono text-xs text-[var(--paper-dim)]">{findings.length} open entries</span>
      </div>
      {findings.length === 0 ? (
        <div className="px-5 py-10 text-center text-[var(--paper-dim)] font-mono text-sm">
          No open findings. The ledger is clean.
        </div>
      ) : (
        findings.map((f) => (
          <FindingRow key={`${f.urn}-${f.title}`} finding={f} onOpenLineage={onOpenLineage} onInvestigate={onInvestigate} />
        ))
      )}
    </div>
  );
}
