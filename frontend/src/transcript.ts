// LiveKit re-delivers the same transcription segment id while the STT result
// evolves (interim -> final). Turns are therefore keyed by
// `${participantId}:${segmentId}` so every re-delivery replaces the existing
// turn in place instead of appending a new chat bubble per update, and so two
// participants that happen to use the same segment ids cannot collide.
//
// TTS transcription is different: it emits one *new* id per phrase or sentence,
// all final, which would render the tutor as a stack of fragments. Consecutive
// final assistant segments are therefore joined into the preceding assistant
// turn. A user turn in between breaks the run, so separate replies never merge.
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
      continue;
    }

    const last = next[next.length - 1];
    if (
      role === 'assistant' &&
      segment.final &&
      last !== undefined &&
      last.role === 'assistant' &&
      !last.pending
    ) {
      if (next === prev) next = [...prev];
      const joined = `${last.text} ${text}`.replace(/\s+/g, ' ').trim();
      next[next.length - 1] = { ...last, text: joined, ts: Date.now() };
      continue;
    }

    if (next === prev) next = [...prev];
    next.push({ id: key, role, text, ts: Date.now(), pending: !segment.final });
  }
  return next;
}
