import { useCallback, useEffect, useRef, useState } from 'react';

import type { Tutor } from './TutorPicker';

interface Concept {
  slug: string;
  label: string;
  level: number;
  correct: number;
  total: number;
  covered: boolean;
}

interface Props {
  tutor: Tutor | null;
  /** Concept the agent is currently working on; highlighted in the grid. */
  activeConcept?: string | null;
  /** Bumped by the parent whenever the agent reports a mastery change. */
  refreshKey?: number;
}

// A failed fetch is not fatal: the mastery API may be briefly unavailable
// while the tutor session is starting. Escalate to a persistent error only
// after this many consecutive failed fetches; every success clears it.
const FAILURE_ERROR_THRESHOLD = 3;
const FETCH_INTERVAL_MS = 5000;

type ProgressState = 'covered' | 'in-progress' | 'not-started';

function progressState(concept: Concept, isActive: boolean): ProgressState {
  if (concept.covered) return 'covered';
  if (concept.total > 0 || isActive) return 'in-progress';
  return 'not-started';
}

const STATE_LABELS: Record<ProgressState, string> = {
  covered: 'Covered',
  'in-progress': 'In progress',
  'not-started': 'Not started',
};

export default function MasteryPanel({ tutor, activeConcept, refreshKey = 0 }: Props) {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [failureCount, setFailureCount] = useState(0);
  const [lastError, setLastError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  // Last refresh key that was already acted on, so the initial render does
  // not trigger a second fetch on top of the one the poll effect starts.
  const lastRefreshKeyRef = useRef(refreshKey);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const fetchMastery = useCallback(async () => {
    if (!tutor) return;
    try {
      const res = await fetch(`/api/mastery?tutor=${encodeURIComponent(tutor.id)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as { concepts: Concept[] };
      if (!mountedRef.current) return;
      // Success: refresh the data and clear any failure state.
      setConcepts(data.concepts);
      setFailureCount(0);
      setLastError(null);
    } catch (err) {
      if (!mountedRef.current) return;
      // Non-fatal: keep the last good data on screen, count the failure,
      // and retry on the normal interval.
      setFailureCount((n) => n + 1);
      setLastError(err instanceof Error ? err.message : String(err));
    }
  }, [tutor]);

  useEffect(() => {
    if (!tutor) {
      setConcepts([]);
      setFailureCount(0);
      setLastError(null);
      return;
    }
    // A new tutor starts with a clean slate; the previous tutor's data must
    // not flash in the grid while the first fetch is in flight.
    setConcepts([]);
    setFailureCount(0);
    setLastError(null);
    void fetchMastery();
    const id = setInterval(() => void fetchMastery(), FETCH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [tutor, fetchMastery]);

  // The agent pushes a mastery update over the room data channel; refetch
  // right away instead of waiting for the next poll.
  useEffect(() => {
    if (!tutor) return;
    if (lastRefreshKeyRef.current === refreshKey) return;
    lastRefreshKeyRef.current = refreshKey;
    void fetchMastery();
  }, [tutor, refreshKey, fetchMastery]);

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
          const isActive = c.slug === activeConcept;
          const state = progressState(c, isActive);
          return (
            <div
              key={c.slug}
              className={`mastery-card${isActive ? ' active' : ''}`}
            >
              <div className="ring" style={{ '--pct': pct } as React.CSSProperties} />
              <h4>{c.label}</h4>
              <span className={`mastery-state ${state}`}>{STATE_LABELS[state]}</span>
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
