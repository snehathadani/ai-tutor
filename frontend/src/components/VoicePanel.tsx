import { ConnectionState } from 'livekit-client';

interface Props {
  state: ConnectionState;
  muted: boolean;
  onToggleMute: () => void;
  onDisconnect: () => void;
}

function stateLabel(state: ConnectionState) {
  switch (state) {
    case ConnectionState.Connected:
      return 'Connected';
    case ConnectionState.Connecting:
      return 'Connecting...';
    case ConnectionState.Reconnecting:
      return 'Reconnecting...';
    default:
      return 'Disconnected';
  }
}

export default function VoicePanel({ state, muted, onToggleMute, onDisconnect }: Props) {
  return (
    <div className="card">
      <div className="form-row" style={{ justifyContent: 'space-between' }}>
        <span className="status">{stateLabel(state)}</span>
        <div className="form-row">
          <button type="button" className="secondary" onClick={onToggleMute}>
            {muted ? 'Unmute' : 'Mute'}
          </button>
          <button type="button" className="danger" onClick={onDisconnect}>
            Disconnect
          </button>
        </div>
      </div>
    </div>
  );
}
