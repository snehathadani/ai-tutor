import { useState } from 'react';

interface Props {
  tutorId: string | null;
  identity: string;
  onIdentityChange: (value: string) => void;
  onConnect: (room: string, identity: string, tutorId: string) => void;
  disabled?: boolean;
}

export default function ConnectPanel({
  tutorId,
  identity,
  onIdentityChange,
  onConnect,
  disabled,
}: Props) {
  const [room, setRoom] = useState('room');
  const isDisabled = disabled || !tutorId;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (room.trim() && identity.trim() && tutorId) {
      onConnect(room.trim(), identity.trim(), tutorId);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="card">
      <h2>Join a session</h2>
      <div className="form-row" style={{ marginTop: '0.75rem' }}>
        <input
          value={room}
          onChange={(e) => setRoom(e.target.value)}
          placeholder="Room name"
          disabled={isDisabled}
          aria-label="Room name"
        />
        <input
          value={identity}
          onChange={(e) => onIdentityChange(e.target.value)}
          placeholder="Your name"
          disabled={isDisabled}
          aria-label="Your name"
        />
        <button type="submit" disabled={isDisabled}>
          Connect
        </button>
      </div>
      {!tutorId && (
        <div className="status" style={{ marginTop: '0.5rem' }}>
          Select a tutor above to connect.
        </div>
      )}
    </form>
  );
}
