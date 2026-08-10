import { useState } from 'react';
import { api } from '../api';

const PROMPTS = [
  'Which finance datasets lack owners?',
  'Show stale production assets.',
  'Which pipelines are failing?',
  'Which datasets contain PII?',
];

export function QueryConsole() {
  const [question, setQuestion] = useState('');
  const [log, setLog] = useState<{ q: string; a: string }[]>([]);
  const [loading, setLoading] = useState(false);

  async function ask(q: string) {
    if (!q.trim() || loading) return;
    setLoading(true);
    setQuestion('');
    try {
      const res = await api.query(q);
      setLog((prev) => [...prev, { q, a: res.answer }]);
    } catch {
      setLog((prev) => [...prev, { q, a: 'Query failed — check the backend is running.' }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="border border-[var(--hairline)] rounded-sm bg-[var(--surface)] flex flex-col h-full">
      <div className="px-5 py-4 border-b border-[var(--hairline)]">
        <h2 className="font-display text-xl">Interrogate the graph</h2>
        <p className="text-xs text-[var(--paper-dim)] mt-1">Ask in plain language. Answers are grounded only in matching catalog rows.</p>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 min-h-[180px]">
        {log.length === 0 && (
          <div className="flex flex-wrap gap-2">
            {PROMPTS.map((p) => (
              <button
                key={p}
                onClick={() => ask(p)}
                className="text-xs font-mono border border-[var(--hairline)] rounded-sm px-3 py-1.5 hover:border-[var(--thread)] text-[var(--paper-dim)] hover:text-[var(--paper)] transition-colors"
              >
                {p}
              </button>
            ))}
          </div>
        )}
        {log.map((entry, i) => (
          <div key={i} className="space-y-1.5">
            <div className="font-mono text-xs text-[var(--thread)]">Q — {entry.q}</div>
            <div className="text-sm pl-3 border-l-2 border-[var(--hairline)]">{entry.a}</div>
          </div>
        ))}
        {loading && <div className="font-mono text-xs text-[var(--paper-dim)]">thinking…</div>}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="border-t border-[var(--hairline)] p-3 flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about the catalog…"
          className="flex-1 bg-transparent text-sm px-2 py-2 outline-none placeholder:text-[var(--paper-dim)]"
        />
        <button
          type="submit"
          className="font-mono text-xs border border-[var(--hairline)] rounded-sm px-3 py-2 hover:border-[var(--thread)] transition-colors"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
