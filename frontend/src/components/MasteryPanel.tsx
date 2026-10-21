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

// A failed fetch is not fatal: the mastery API may be briefly unavailable
// while the tutor session is starting. Escalate to a persistent error only
// after this many consecutive failed fetches; every success clears it.
const FAILURE_ERROR_THRESHOLD = 3;
const FETCH_INTERVAL_MS = 5000;

export default function MasteryPanel({ tutor }: Props) {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [failureCount, setFailureCount] = useState(0);
  const [lastError, setLastError] = useState<string | null>(null);

  useEffect(() => {
    if (!tutor) {
      setConcepts([]);
      setFailureCount(0);
      setLastError(null);
      return;
    }
    let cancelled = false;
    // A new tutor starts with a clean slate; the previous tutor's data must
    // not flash in the grid while the first fetch is in flight.
    setConcepts([]);
    setFailureCount(0);
    setLastError(null);
    const fetchMastery = async () => {
      try {
        const res = await fetch(`/api/mastery?tutor=${encodeURIComponent(tutor.id)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as { concepts: Concept[] };
        if (cancelled) return;
        // Success: refresh the data and clear any failure state.
        setConcepts(data.concepts);
        setFailureCount(0);
        setLastError(null);
      } catch (err) {
        if (cancelled) return;
        // Non-fatal: keep the last good data on screen, count the failure,
        // and retry on the normal interval.
        setFailureCount((n) => n + 1);
        setLastError(err instanceof Error ? err.message : String(err));
      }
    };
    fetchMastery();
    const id = setInterval(fetchMastery, FETCH_INTERVAL_MS);
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

  const persistentError = failureCount >= FAILURE_ERROR_THRESHOLD;

  return (
    <div className="card">
      <h2>Mastery</h2>
      {persistentError ? (
        <div className="error">
          Could not load mastery after {failureCount} attempts ({lastError}).
          Retrying every {FETCH_INTERVAL_MS / 1000}s.
        </div>
      ) : (
        concepts.length === 0 && (
          <div className="status" style={{ marginTop: '0.75rem' }}>
            Waiting for the tutor…
          </div>
        )
      )}
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
