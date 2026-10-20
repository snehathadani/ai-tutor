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

export default function App() {
  const [room, setRoom] = useState<Room | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>(ConnectionState.Disconnected);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [muted, setMuted] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);

  const addTurn = useCallback((role: 'user' | 'assistant', text: string) => {
    setTurns((prev: Turn[]) => [
      ...prev,
      { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, role, text, ts: Date.now() },
    ]);
  }, []);

  const handleConnect = useCallback(async (roomName: string, identity: string) => {
    setError(null);
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
      const { token, url } = (await res.json()) as { token: string; url: string };

      const newRoom = new Room({ adaptiveStream: true });

      newRoom.on(RoomEvent.Connected, () => {
        setConnectionState(ConnectionState.Connected);
        addTurn('assistant', 'Hi! I am your probability tutor. What would you like to work on?');
      });

      newRoom.on(RoomEvent.Disconnected, () => {
        setConnectionState(ConnectionState.Disconnected);
        setRoom(null);
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

      {room && (
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
