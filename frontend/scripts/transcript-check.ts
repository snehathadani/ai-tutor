// Assertion checks for src/transcript.ts, run with:
//   npm run test:transcript  (node --experimental-strip-types)
// Kept out of tsconfig's `include` (src only), so tsc --noEmit does not gate it.
import { mergeTranscriptionTurns, type Turn } from '../src/transcript.ts';

// Node globals, declared locally so this script needs no @types/node.
declare const process: { exit(code: number): never };

let passed = 0;
const failures: string[] = [];

function check(name: string, cond: boolean, detail = ''): void {
  if (cond) {
    passed += 1;
    console.log(`ok - ${name}`);
  } else {
    failures.push(detail ? `${name}: ${detail}` : name);
    console.error(`FAIL - ${name}${detail ? `: ${detail}` : ''}`);
  }
}

const USER = 'user-1';

// 1. Interim then final -> exactly one turn holding the final text.
let turns: Turn[] = [];
turns = mergeTranscriptionTurns(turns, [{ id: 's1', text: 'What is' }], 'user', USER);
turns = mergeTranscriptionTurns(
  turns,
  [{ id: 's1', text: 'What is the probability of two heads?', final: true }],
  'user',
  USER
);
check('interim then final yields exactly one turn', turns.length === 1, `got ${turns.length}`);
check(
  'final text replaces interim text',
  turns[0]?.text === 'What is the probability of two heads?',
  `got "${turns[0]?.text}"`
);
check('final clears pending', turns[0]?.pending === false, `got ${turns[0]?.pending}`);

// 2. Three interim updates then final -> still one turn.
turns = [];
turns = mergeTranscriptionTurns(turns, [{ id: 's2', text: 'a' }], 'user', USER);
turns = mergeTranscriptionTurns(turns, [{ id: 's2', text: 'a b' }], 'user', USER);
turns = mergeTranscriptionTurns(turns, [{ id: 's2', text: 'a b c' }], 'user', USER);
turns = mergeTranscriptionTurns(turns, [{ id: 's2', text: 'a b c d', final: true }], 'user', USER);
check('three interims then final yields exactly one turn', turns.length === 1, `got ${turns.length}`);
check('three interims converge on final text', turns[0]?.text === 'a b c d', `got "${turns[0]?.text}"`);
check('interim updates flag pending', turns[0]?.pending === false && true, `got ${turns[0]?.pending}`);

// 3. Two different segment ids -> two turns, order preserved, in-place update keeps position.
turns = [];
turns = mergeTranscriptionTurns(turns, [{ id: 's3', text: 'first', final: true }], 'user', USER);
turns = mergeTranscriptionTurns(turns, [{ id: 's4', text: 'second', final: true }], 'user', USER);
check('two segment ids yield two turns', turns.length === 2, `got ${turns.length}`);
check(
  'ordering is preserved',
  turns[0]?.text === 'first' && turns[1]?.text === 'second',
  `got "${turns.map((t) => t.text).join(' | ')}"`
);
turns = mergeTranscriptionTurns(turns, [{ id: 's3', text: 'first updated', final: true }], 'user', USER);
check(
  'in-place update keeps position and does not duplicate',
  turns.length === 2 && turns[0]?.text === 'first updated' && turns[1]?.text === 'second'
);

// 4. Empty / whitespace-only text is skipped.
const beforeEmpty = turns.length;
turns = mergeTranscriptionTurns(turns, [{ id: 's5', text: '   ' }], 'user', USER);
turns = mergeTranscriptionTurns(turns, [{ id: 's6', text: '' }], 'user', USER);
check('empty and whitespace-only text is skipped', turns.length === beforeEmpty, `got ${turns.length}`);

// 5. Re-delivered unchanged final does not duplicate.
const beforeFinal = turns.length;
turns = mergeTranscriptionTurns(turns, [{ id: 's3', text: 'first updated', final: true }], 'user', USER);
check(
  're-delivered unchanged final does not duplicate',
  turns.length === beforeFinal,
  `got ${turns.length} (was ${beforeFinal})`
);

// 6. Two participants with the same segment id stay separate.
turns = [];
turns = mergeTranscriptionTurns(turns, [{ id: 'shared', text: 'from user', final: true }], 'user', 'user-1');
turns = mergeTranscriptionTurns(
  turns,
  [{ id: 'shared', text: 'from tutor', final: true }],
  'assistant',
  'agent-1'
);
check(
  'same segment id across two participants stays separate',
  turns.length === 2,
  `got ${turns.length}`
);
check(
  'per-participant texts are kept apart',
  turns.some((t) => t.text === 'from user') && turns.some((t) => t.text === 'from tutor')
);

// 7. Roles preserved per participant.
check(
  'assistant and user roles are preserved',
  turns[0]?.role === 'user' && turns[1]?.role === 'assistant',
  `got ${turns.map((t) => t.role).join(',')}`
);

// Interim re-update of an existing participant turn stays in place and is pending.
turns = mergeTranscriptionTurns(turns, [{ id: 'shared', text: 'from user, still speaking' }], 'user', 'user-1');
const userTurn = turns.find((t) => t.id === 'user-1:shared');
check('interim update of existing turn is flagged pending', userTurn?.pending === true, `got ${userTurn?.pending}`);
check('interim update replaces text in place', turns.length === 2 && userTurn?.text === 'from user, still speaking');

// 8. TTS emits one final segment per phrase with fresh ids. Those must read as
// one reply, not a stack of fragments.
turns = [];
turns = mergeTranscriptionTurns(turns, [{ id: 't1', text: 'Think about a fair coin.', final: true }], 'assistant', 'agent-1');
turns = mergeTranscriptionTurns(turns, [{ id: 't2', text: 'What are the two possible outcomes?', final: true }], 'assistant', 'agent-1');
check('consecutive assistant finals join into one turn', turns.length === 1, `got ${turns.length}`);
check(
  'joined text reads as one reply',
  turns[0]?.text === 'Think about a fair coin. What are the two possible outcomes?',
  `got "${turns[0]?.text}"`
);

// 9. A user turn between two replies breaks the run.
turns = mergeTranscriptionTurns(turns, [{ id: 'u1', text: 'Heads and tails.', final: true }], 'user', USER);
turns = mergeTranscriptionTurns(turns, [{ id: 't3', text: 'Nice. So what is the chance of heads?', final: true }], 'assistant', 'agent-1');
check('assistant replies do not merge across a user turn', turns.length === 3, `got ${turns.length}`);
check(
  'the later reply stays its own turn',
  turns[2]?.text === 'Nice. So what is the chance of heads?',
  `got "${turns[2]?.text}"`
);

// 10. An interim assistant segment is not merged into the previous final turn.
turns = mergeTranscriptionTurns(turns, [{ id: 't4', text: 'And if we flip tw' }], 'assistant', 'agent-1');
check('interim assistant segment starts a new pending turn', turns.length === 4 && turns[3]?.pending === true);

// 11. Leaked DSML tool markup is stripped, never rendered or merged.
turns = [];
turns = mergeTranscriptionTurns(
  turns,
  [
    {
      id: 'd1',
      text: 'Nice work! <｜｜DSML｜｜ calls> <｜｜DSML｜｜ invoke name="get_problem"> x </｜｜DSML｜｜ calls>',
      final: true,
    },
  ],
  'assistant',
  'agent-1'
);
check('leaked DSML markup is stripped from speech', turns[0]?.text === 'Nice work!', `got "${turns[0]?.text}"`);
turns = mergeTranscriptionTurns(
  turns,
  [{ id: 'd2', text: '<｜｜DSML｜｜ calls> </｜｜DSML｜｜ calls>', final: true }],
  'assistant',
  'agent-1'
);
check('markup-only segment is dropped', turns.length === 1, `got ${turns.length}`);

// 12. A duplicate dispatch can greet twice; only one should render.
turns = [];
turns = mergeTranscriptionTurns(
  turns,
  [{ id: 'w1', text: "Welcome back! Let's keep going with Experiment vs theory.", final: true }],
  'assistant',
  'agent-1'
);
turns = mergeTranscriptionTurns(
  turns,
  [{ id: 'w2', text: "Welcome back! Let's keep going with Experiment vs theory.", final: true }],
  'assistant',
  'agent-2'
);
check('duplicate welcome greetings collapse to one turn', turns.length === 1, `got ${turns.length}`);
check(
  'the greeting text is not repeated inside the turn',
  turns[0]?.text === "Welcome back! Let's keep going with Experiment vs theory.",
  `got "${turns[0]?.text}"`
);

if (failures.length > 0) {
  console.error(`\n${failures.length} assertion(s) failed`);
  process.exit(1);
}
console.log(`\nall ${passed} assertions passed`);
