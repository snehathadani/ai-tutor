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
import TutorPicker, { type Tutor } from './components/TutorPicker';
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

export function LinkCard({
  tutor,
  activeConcept,
  onClear,
}: {
  tutor: Tutor | null;
  activeConcept: string | null;
  onClear: () => void;
}) {
  if (!activeConcept || !tutor) return null;
  const concept = tutor.concepts.find((c) => c.slug === activeConcept);
  if (!concept || !concept.references || concept.references.length === 0) return null;

  return (
    <div className="card link-card">
      <div className="form-row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h3>Learn more: {concept.label}</h3>
          <ul className="link-list">
            {concept.references.map((ref, i) => (
              <li key={i}>
                <a href={ref.url} target="_blank" rel="noopener noreferrer">
                  {ref.title}
                </a>
              </li>
            ))}
          </ul>
        </div>
        <button type="button" className="secondary" onClick={onClear} aria-label="Clear references">
          ×
        </button>
      </div>
    </div>
  );
}

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
  const [tutors, setTutors] = useState<Tutor[]>([]);
  const [invalidTutors, setInvalidTutors] = useState<{ id?: string; error: string }[]>([]);
  const [selectedTutor, setSelectedTutor] = useState<Tutor | null>(null);
  const [activeConcept, setActiveConcept] = useState<string | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const greetedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const loadTutors = async () => {
      try {
        const res = await fetch('/api/tutors');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as {
          tutors: Tutor[];
          invalid: { id?: string; error: string }[];
        };
        if (cancelled) return;
        setTutors(data.tutors);
        setInvalidTutors(data.invalid);
        if (data.tutors.length > 0 && !selectedTutor) {
          setSelectedTutor(data.tutors[0]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    };
    loadTutors();
    return () => {
      cancelled = true;
    };
  }, []);

  const addTurn = useCallback((role: 'user' | 'assistant', text: string) => {
    setTurns((prev: Turn[]) => [
      ...prev,
      { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, role, text, ts: Date.now() },
    ]);
  }, []);

  const requestDispatch = useCallback(
    async (roomName: string, tutorId: string) => {
      try {
        const res = await fetch('/api/dispatch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room: roomName, tutor_id: tutorId }),
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
    },
    []
  );

  const handleConnect = useCallback(
    async (roomName: string, identity: string, tutorId: string) => {
      if (!selectedTutor || selectedTutor.id !== tutorId) return;

      const prefixedRoom = `${tutorId}-${roomName}`;
      setError(null);
      setAgentError(null);
      setAgentJoined(false);
      setLastDispatchError(null);
      greetedRef.current = false;
      setSummary(null);
      setTurns([]);
      setSessionId(prefixedRoom);
      setActiveConcept(null);

      try {
        const res = await fetch('/api/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ room: prefixedRoom, identity, tutor_id: tutorId }),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
          throw new Error(`Could not get token: ${res.status} ${JSON.stringify(body.detail)}`);
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
          setActiveConcept(null);
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

        newRoom.on(
          RoomEvent.DataReceived,
          (payload: Uint8Array, _participant?: Participant, _kind?: unknown, topic?: string) => {
            if (topic !== 'tutor:concept') return;
            try {
              const data = JSON.parse(new TextDecoder().decode(payload)) as {
                type?: string;
                slug?: string | null;
              };
              if (data.type === 'concept_active' && data.slug !== activeConcept) {
                setActiveConcept(data.slug ?? null);
              }
            } catch {
              // ignore malformed packets
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
    },
    [addTurn, activeConcept, selectedTutor]
  );

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
    if (agentJoined && !greetedRef.current && selectedTutor) {
      greetedRef.current = true;
      addTurn('assistant', `Hi! I am your ${selectedTutor.title.toLowerCase()}. What would you like to work on?`);
    }
  }, [agentJoined, addTurn, selectedTutor]);

  const retryDispatch = useCallback(async () => {
    if (!room || !selectedTutor) return;
    setAgentError(null);
    const err = await requestDispatch(room.name, selectedTutor.id);
    if (err) {
      setAgentError(`Retry failed: ${err}`);
    }
  }, [room, requestDispatch, selectedTutor]);

  const toggleMute = useCallback(async () => {
    if (!room) return;
    const enabled = !muted;
    await room.localParticipant.setMicrophoneEnabled(enabled);
    setMuted(!enabled);
  }, [room, muted]);

  const handleSelectTutor = useCallback((tutor: Tutor) => {
    setSelectedTutor(tutor);
    // A slug published by the previous tutor's session must not leak into
    // the newly selected tutor's link card.
    setActiveConcept(null);
  }, []);

  const disconnect = useCallback(async () => {
    if (!room) return;
    setActiveConcept(null);
    await room.disconnect();
  }, [room]);

  useEffect(() => {
    if (!sessionId || room || !selectedTutor) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(
          `/api/sessions/${encodeURIComponent(sessionId)}/summary?tutor=${encodeURIComponent(
            selectedTutor.id
          )}`
        );
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
  }, [sessionId, room, selectedTutor]);

  return (
    <div className="app">
      <header className="card">
        <h1>AI Tutor</h1>
        <p className="status">A Socratic, kid-friendly voice tutor.</p>
      </header>

      {error && <div className="card error">Error: {error}</div>}

      <TutorPicker
        tutors={tutors}
        invalid={invalidTutors}
        selected={selectedTutor}
        onSelect={handleSelectTutor}
      />

      <ConnectPanel
        tutorId={selectedTutor?.id ?? null}
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
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--gap)' }}>
          <LinkCard tutor={selectedTutor} activeConcept={activeConcept} onClear={() => setActiveConcept(null)} />
          <MasteryPanel tutor={selectedTutor} />
        </div>
      </div>

      {summary && <SummaryView summary={summary} onClose={() => setSummary(null)} />}
    </div>
  );
}
