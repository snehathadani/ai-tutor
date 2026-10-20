import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ConnectionState,
  Room,
  RoomEvent,
  Track,
  TranscriptionSegment,
  type Participant,
  type RemoteTrack,
} from 'livekit-client';

import ConnectPanel from './components/ConnectPanel';
import MasteryPanel from './components/MasteryPanel';
import SummaryView from './components/SummaryView';
import TranscriptPanel from './components/TranscriptPanel';
import VoicePanel from './components/VoicePanel';

interface Turn {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  ts: number;
}

interface Summary {
  summary: string;
  strengths: string[];
  next_steps: string[];
}

const TUTOR_WAKEUP_MS = 20000;

export default function App() {
  const [room, setRoom] = useState<Room | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>(ConnectionState.Disconnected);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [muted, setMuted] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [agentJoined, setAgentJoined] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [lastDispatchError, setLastDispatchError] = useState<string | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const greetedRef = useRef(false);

  const addTurn = useCallback((role: 'user' | 'assistant', text: string) => {
    setTurns((prev: Turn[]) => [
      ...prev,
      { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, role, text, ts: Date.now() },
    ]);
  }, []);

  const requestDispatch = useCallback(async (roomName: string) => {
    try {
      const res = await fetch('/api/dispatch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room: roomName }),
      });
      const data = (await res.json()) as { dispatched: boolean; error?: string };
      if (!res.ok || !data.dispatched) {
        const err = data.error || 'Dispatch request failed';
        setLastDispatchError(err);
        return err;
      }
      setLastDispatchError(null);
      return null;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLastDispatchError(msg);
      return msg;
    }
  }, []);

  const handleConnect = useCallback(async (roomName: string, identity: string) => {
    setError(null);
    setAgentError(null);
    setAgentJoined(false);
    setLastDispatchError(null);
    greetedRef.current = false;
    setSummary(null);
    setTurns([]);
    setSessionId(roomName);

    try {
      const res = await fetch('/api/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ room: roomName, identity }),
      });
      if (!res.ok) {
        throw new Error(`Could not get token: ${res.status}`);
      }
      const { token, url, dispatch_error } = (await res.json()) as {
        token: string;
        url: string;
        dispatch_error?: string;
      };
      if (dispatch_error) {
        setLastDispatchError(dispatch_error);
      }

      const newRoom = new Room({ adaptiveStream: true });

      newRoom.on(RoomEvent.Connected, () => {
        setConnectionState(ConnectionState.Connected);
      });

      newRoom.on(RoomEvent.Disconnected, () => {
        setConnectionState(ConnectionState.Disconnected);
        setRoom(null);
        setAgentJoined(false);
        setAgentError(null);
        setLastDispatchError(null);
        greetedRef.current = false;
        addTurn('assistant', 'Session ended.');
      });

      newRoom.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Audio && audioElRef.current) {
          track.attach(audioElRef.current);
        }
      });

      newRoom.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
        track.detach();
      });

      newRoom.on(
        RoomEvent.TranscriptionReceived,
        (segments: TranscriptionSegment[], participant?: Participant) => {
          for (const seg of segments) {
            const text = seg.text?.trim();
            if (!text) continue;
            const role = participant?.identity === identity ? 'user' : 'assistant';
            addTurn(role, text);
          }
        }
      );

      await newRoom.connect(url, token);
      await newRoom.localParticipant.setMicrophoneEnabled(true);
      setMuted(false);
      setRoom(newRoom);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setConnectionState(ConnectionState.Disconnected);
    }
  }, [addTurn]);

  useEffect(() => {
    if (!room) {
      setAgentJoined(false);
      return;
    }
    const checkAgent = () => {
      const joined = Array.from(room.remoteParticipants.values()).some((p) => p.isAgent);
      setAgentJoined(joined);
      if (joined) setAgentError(null);
    };
    checkAgent();
    room.on(RoomEvent.ParticipantConnected, checkAgent);
    room.on(RoomEvent.ParticipantDisconnected, checkAgent);
    return () => {
      room.off(RoomEvent.ParticipantConnected, checkAgent);
      room.off(RoomEvent.ParticipantDisconnected, checkAgent);
    };
  }, [room]);

  useEffect(() => {
    if (!room || agentJoined || agentError) return;
    const timer = setTimeout(() => {
      const extra = lastDispatchError ? ` Server dispatch error: ${lastDispatchError}` : '';
      setAgentError(
        `Your tutor is taking longer than expected to join.${extra} Try the retry button or check that the agent service is running.`
      );
    }, TUTOR_WAKEUP_MS);
    return () => clearTimeout(timer);
  }, [room, agentJoined, agentError, lastDispatchError]);

  useEffect(() => {
    if (agentJoined && !greetedRef.current) {
      greetedRef.current = true;
      addTurn('assistant', 'Hi! I am your probability tutor. What would you like to work on?');
    }
  }, [agentJoined, addTurn]);

  const retryDispatch = useCallback(async () => {
    if (!room) return;
    setAgentError(null);
    const err = await requestDispatch(room.name);
    if (err) {
      setAgentError(`Retry failed: ${err}`);
    }
  }, [room, requestDispatch]);

  const toggleMute = useCallback(async () => {
    if (!room) return;
    const enabled = !muted;
    await room.localParticipant.setMicrophoneEnabled(enabled);
    setMuted(!enabled);
  }, [room, muted]);

  const disconnect = useCallback(async () => {
    if (!room) return;
    await room.disconnect();
  }, [room]);

  useEffect(() => {
    if (!sessionId || room) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/summary`);
        if (res.ok) {
          const data = (await res.json()) as Summary;
          if (!cancelled) setSummary(data);
        }
      } catch {
        // ignore polling errors
      }
    };
    const id = setInterval(poll, 2000);
    poll();
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [sessionId, room]);

  return (
    <div className="app">
      <header className="card">
        <h1>Probability Voice Tutor</h1>
        <p className="status">A Socratic, kid-friendly tutor for chance and probability.</p>
      </header>

      {error && <div className="card error">Error: {error}</div>}

      <ConnectPanel
        onConnect={handleConnect}
        disabled={connectionState === ConnectionState.Connecting || !!room}
      />

      {room && !agentJoined && !agentError && (
        <div className="card">
          <div className="form-row" style={{ justifyContent: 'space-between' }}>
            <span className="status">Waking up your tutor…</span>
            <button type="button" className="danger" onClick={disconnect}>
              Disconnect
            </button>
          </div>
        </div>
      )}

      {room && agentError && (
        <div className="card error">
          <div className="form-row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{agentError}</span>
            <div className="form-row">
              <button type="button" className="secondary" onClick={retryDispatch}>
                Retry
              </button>
              <button type="button" className="danger" onClick={disconnect}>
                Disconnect
              </button>
            </div>
          </div>
        </div>
      )}

      {room && agentJoined && (
        <VoicePanel
          state={connectionState}
          muted={muted}
          onToggleMute={toggleMute}
          onDisconnect={disconnect}
        />
      )}

      <audio ref={audioElRef} autoPlay playsInline style={{ display: 'none' }} />

      <div className="form-row" style={{ alignItems: 'stretch' }}>
        <div style={{ flex: 2 }}>
          <TranscriptPanel turns={turns} />
        </div>
        <div style={{ flex: 1 }}>
          <MasteryPanel />
        </div>
      </div>

      {summary && (
        <SummaryView
          summary={summary}
          onClose={() => setSummary(null)}
        />
      )}
    </div>
  );
}
