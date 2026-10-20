import { useState } from 'react';

interface Props {
  onConnect: (room: string, identity: string) => void;
  disabled?: boolean;
}

export default function ConnectPanel({ onConnect, disabled }: Props) {
  const [room, setRoom] = useState('probability-room');
  const [identity, setIdentity] = useState('student');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (room.trim() && identity.trim()) {
      onConnect(room.trim(), identity.trim());
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
          disabled={disabled}
          aria-label="Room name"
        />
        <input
          value={identity}
          onChange={(e) => setIdentity(e.target.value)}
          placeholder="Your name"
          disabled={disabled}
          aria-label="Your name"
        />
        <button type="submit" disabled={disabled}>
          Connect
        </button>
      </div>
    </form>
  );
}
