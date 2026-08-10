import { useEffect, useMemo, useState } from 'react';
import ReactFlow, { Background, type Edge, type Node } from 'reactflow';
import 'reactflow/dist/style.css';
import { api } from '../api';
import type { RootCauseResult } from '../types';

function CaseNode({ data }: { data: { label: string; note: string | null; isRoot: boolean } }) {
  return (
    <div
      className="px-3 py-2 rounded-sm border-2 font-mono text-xs max-w-[220px]"
      style={{
        background: 'var(--surface-raised)',
        borderColor: data.isRoot ? 'var(--stamp-critical)' : 'var(--hairline)',
        color: 'var(--paper)',
        transform: `rotate(${data.isRoot ? '-1.5deg' : '0.5deg'})`,
        boxShadow: '2px 3px 0 rgba(0,0,0,0.35)',
      }}
    >
      <div className="font-display text-sm not-italic">{data.label}</div>
      {data.note && <div className="text-[var(--paper-dim)] mt-1">{data.note}</div>}
    </div>
  );
}

const nodeTypes = { case: CaseNode };

export function CaseBoard({ urn, onClose }: { urn: string; onClose: () => void }) {
  const [result, setResult] = useState<RootCauseResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setResult(null);
    setError(null);
    api.rootCause(urn).then(setResult).catch((e) => setError(e instanceof Error ? e.message : 'Failed to trace lineage'));
  }, [urn]);

  const { nodes, edges } = useMemo(() => {
    if (!result) return { nodes: [] as Node[], edges: [] as Edge[] };
    const nodes: Node[] = result.chain.map((hop, i) => ({
      id: hop.urn,
      type: 'case',
      position: { x: i * 260, y: (i % 2) * 60 },
      data: { label: hop.label, note: hop.note, isRoot: i === result.chain.length - 1 },
    }));
    const edges: Edge[] = result.chain.slice(0, -1).map((hop, i) => ({
      id: `${hop.urn}-${result.chain[i + 1].urn}`,
      source: hop.urn,
      target: result.chain[i + 1].urn,
      animated: true,
      style: { stroke: 'var(--thread)', strokeWidth: 1.5, strokeDasharray: '4 3' },
    }));
    return { nodes, edges };
  }, [result]);

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-6">
      <div className="bg-[var(--surface)] border border-[var(--hairline)] rounded-sm w-full max-w-4xl max-h-[85vh] flex flex-col">
        <div className="px-5 py-4 border-b border-[var(--hairline)] flex items-center justify-between">
          <h2 className="font-display text-xl">Root cause — pinned to the board</h2>
          <button onClick={onClose} className="font-mono text-xs text-[var(--paper-dim)] hover:text-[var(--paper)]">
            close ✕
          </button>
        </div>
        <div style={{ height: 220 }} className="border-b border-[var(--hairline)]">
          {nodes.length > 0 && (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              fitView
              proOptions={{ hideAttribution: true }}
              nodesDraggable={false}
              zoomOnScroll={false}
            >
              <Background color="var(--hairline)" gap={18} />
            </ReactFlow>
          )}
        </div>
        <div className="p-5 text-sm overflow-y-auto">
          {result ? (
            <>
              <div className="font-mono text-xs uppercase tracking-wider text-[var(--paper-dim)] mb-1">
                Case notes ({result.reasoning_source})
              </div>
              <p>{result.explanation}</p>
            </>
          ) : error ? (
            <p className="font-mono text-xs" style={{ color: 'var(--stamp-critical)' }}>{error}</p>
          ) : (
            <p className="text-[var(--paper-dim)] font-mono text-xs">tracing lineage…</p>
          )}
        </div>
      </div>
    </div>
  );
}
