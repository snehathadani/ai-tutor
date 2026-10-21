// LiveKit re-delivers the same transcription segment id while the STT result
// evolves (interim -> final). Turns are therefore keyed by
// `${participantId}:${segmentId}` so every re-delivery replaces the existing
// turn in place instead of appending a new chat bubble per update, and so two
// participants that happen to use the same segment ids cannot collide.
export interface Turn {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  ts: number;
  /** True while the turn holds an interim STT result; cleared once final. */
  pending?: boolean;
}

export function mergeTranscriptionTurns(
  prev: Turn[],
  segments: ReadonlyArray<{ id: string; text: string; final?: boolean }>,
  role: 'user' | 'assistant',
  participantId: string
): Turn[] {
  let next = prev;
  for (const segment of segments) {
    const text = (segment.text ?? '').trim();
    if (!text) continue;
    const key = `${participantId}:${segment.id}`;
    const index = next.findIndex((turn) => turn.id === key);
    if (index >= 0) {
      const existing = next[index];
      // A re-delivered final whose text is unchanged carries no new information.
      if (!existing.pending && existing.text === text) continue;
      if (next === prev) next = [...prev];
      next[index] = { ...existing, text, pending: !segment.final };
    } else {
      if (next === prev) next = [...prev];
      next.push({ id: key, role, text, ts: Date.now(), pending: !segment.final });
    }
  }
  return next;
}
