import { useEffect, useState } from 'react';

interface Concept {
  slug: string;
  label: string;
  level: number;
  correct: number;
  total: number;
}

export default function MasteryPanel() {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchMastery = async () => {
      try {
        const res = await fetch('/api/mastery');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as { concepts: Concept[] };
        if (!cancelled) setConcepts(data.concepts);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    };
    fetchMastery();
    const id = setInterval(fetchMastery, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="card">
      <h2>Mastery</h2>
      {error && <div className="error">{error}</div>}
      <div className="mastery-grid" style={{ marginTop: '0.75rem' }}>
        {concepts.map((c) => {
          const pct = (c.level / 3) * 100;
          return (
            <div key={c.slug} className="mastery-card">
              <div className="ring" style={{ '--pct': pct } as React.CSSProperties} />
              <h4>{c.label}</h4>
              <span>
                Lvl {c.level}/3 · {c.correct}/{c.total} correct
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
