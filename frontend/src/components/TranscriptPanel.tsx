import { useCallback, useLayoutEffect, useRef, useState } from 'react';

import type { Turn } from '../transcript';

interface Props {
  turns: Turn[];
}

// How close to the bottom the container has to be for new turns to keep
// scrolling the view. Further up means the student is reading back and must
// not be yanked down.
const BOTTOM_THRESHOLD_PX = 80;

export default function TranscriptPanel({ turns }: Props) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [showJump, setShowJump] = useState(false);
  // True while the view is pinned to the bottom of the transcript.
  const atBottomRef = useRef(true);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    atBottomRef.current = true;
    setShowJump(false);
  }, []);

  // A layout effect runs after the new turns are in the DOM but before the
  // browser paints, so the scroll happens in the same frame as the update.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (atBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    atBottomRef.current = distance <= BOTTOM_THRESHOLD_PX;
    setShowJump(!atBottomRef.current);
  }, [turns]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    atBottomRef.current = distance <= BOTTOM_THRESHOLD_PX;
    setShowJump(!atBottomRef.current);
  }, []);

  return (
    <div className="card">
      <h2>Transcript</h2>
      <div
        className="transcript"
        style={{ marginTop: '0.75rem' }}
        ref={scrollRef}
        onScroll={handleScroll}
      >
        {turns.length === 0 && (
          <div className="status">No messages yet. Connect to start talking.</div>
        )}
        {turns.map((turn) => (
          <div
            key={turn.id}
            className={`turn ${turn.role}`}
            style={{ opacity: turn.pending ? 0.6 : undefined }}
          >
            <strong>{turn.role === 'user' ? 'You' : 'Tutor'}</strong>
            <p style={{ margin: '0.25rem 0 0 0' }}>{turn.text}</p>
          </div>
        ))}
      </div>
      {showJump && (
        <button type="button" className="secondary jump-latest" onClick={scrollToBottom}>
          Jump to latest
        </button>
      )}
    </div>
  );
}
