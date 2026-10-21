import { useEffect, useState } from 'react';

import type { Tutor } from './TutorPicker';

interface Concept {
  slug: string;
  label: string;
  level: number;
  correct: number;
  total: number;
}

interface Props {
  tutor: Tutor | null;
}

export default function MasteryPanel({ tutor }: Props) {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tutor) {
      setConcepts([]);
      return;
    }
    let cancelled = false;
    const fetchMastery = async () => {
      try {
        const res = await fetch(`/api/mastery?tutor=${encodeURIComponent(tutor.id)}`);
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
  }, [tutor]);

  if (!tutor) {
    return (
      <div className="card">
        <h2>Mastery</h2>
        <div className="status" style={{ marginTop: '0.75rem' }}>
          Select a tutor to see mastery.
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>Mastery</h2>
      {error && <div className="error">{error}</div>}
      <div className="mastery-grid" style={{ marginTop: '0.75rem' }}>
        {concepts.map((c) => {
          const pct = (c.level / 3) * 100;
          const levelLabel = tutor.level_labels?.[c.level];
          return (
            <div key={c.slug} className="mastery-card">
              <div className="ring" style={{ '--pct': pct } as React.CSSProperties} />
              <h4>{c.label}</h4>
              <span>
                {levelLabel ? levelLabel : `Lvl ${c.level}/3`} · {c.correct}/{c.total} correct
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
