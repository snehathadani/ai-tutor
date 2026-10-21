import type { Turn } from '../transcript';

interface Props {
  turns: Turn[];
}

export default function TranscriptPanel({ turns }: Props) {
  return (
    <div className="card">
      <h2>Transcript</h2>
      <div className="transcript" style={{ marginTop: '0.75rem' }}>
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
    </div>
  );
}
