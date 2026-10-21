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

// DeepSeek sometimes emits its internal tool syntax as plain text:
//   <｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="get_problem"> ... </｜｜DSML｜｜ calls>
// That is not speech, so it must never render. The block always runs to the end
// of the turn, so dropping from the marker onwards is safe.
const DSML_MARKER = /<[｜|]{2}\s*DSML/i;

export function sanitizeModelText(text: string): string {
  const match = text.search(DSML_MARKER);
  return (match === -1 ? text : text.slice(0, match)).trim();
}

export function mergeTranscriptionTurns(
  prev: Turn[],
  segments: ReadonlyArray<{ id: string; text: string; final?: boolean }>,
  role: 'user' | 'assistant',
  participantId: string
): Turn[] {
  let next = prev;
  for (const segment of segments) {
    const text = sanitizeModelText(segment.text ?? '');
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
    // Duplicate dispatches can make two jobs greet the same room; keep one.
    if (
      role === 'assistant' &&
      /^welcome back!/i.test(text) &&
      last !== undefined &&
      last.role === 'assistant' &&
      /^welcome back!/i.test(last.text)
    ) {
      continue;
    }
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
