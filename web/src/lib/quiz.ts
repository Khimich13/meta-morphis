// The quiz rules: which cards a lesson asks about, how each question is
// made, and whether an answer is right. Each kind of question's own
// rules are in questionKinds.ts. No React in here, so it can be tested
// without a browser.

import type { Card } from './cards';
import { isDue, type Progress } from './progress';
import {
  KINDS,
  type Option,
  type Part,
  type Pools,
  QUESTION_KINDS,
  type QuestionKind,
} from './questionKinds';
import { type Random, shuffle } from './random';

export const LESSON_LENGTH = 10;
/** At most this many cards never seen before in a lesson, when others are waiting */
export const NEW_PER_LESSON = 3;

/** A question about a part of the card (see Part in questionKinds.ts) */
export interface Question extends Part {
  /** The card being asked about */
  card: Card;
  kind: QuestionKind;
  /** The answers to choose from, in the order shown: the card itself and wrong ones */
  options: Option[];
}

/**
 * A question about the card. `same` keeps the kind and part of an earlier
 * question about it; without it, both are picked at random.
 *
 * Its kind offers its own answers (see KINDS in questionKinds.ts). Wrong
 * ones come from `allCards` first, the cards being learned, then from
 * each of `moreCards` in turn: the format's other cards, then every
 * format's.
 */
export function makeQuestion(
  card: Card,
  allCards: readonly Card[],
  random: Random = Math.random,
  same?: Pick<Question, 'kind' | 'back' | 'spell' | 'half'>,
  moreCards: Pools = [],
): Question {
  // Either side, half the time each, for a card with a back to ask about,
  // either part, for a card with a spell whose name can be hidden, and
  // either half of a split card
  const back = same?.back ?? (card.back ? random() < 0.5 : false);
  const spell = same?.spell ?? (card.spell?.name_box ? random() < 0.5 : false);
  const half = same?.half ?? (card.halves ? pickHalf(random) : null);
  const part = { back, spell, half };
  // Then any kind it can be asked by there, as often each
  const kinds = QUESTION_KINDS.filter((kind) => KINDS[kind].asks(card, part));
  const kind =
    same?.kind ?? (kinds.length > 1 ? kinds[Math.floor(random() * kinds.length)] : kinds[0]);
  const options = KINDS[kind].options(card, part, [allCards, ...moreCards], random);
  return { card, kind, ...part, options };
}

/** Either half of a split card, half the time each */
function pickHalf(random: Random): number {
  return random() < 0.5 ? 1 : 0;
}

/**
 * The cards a lesson asks about, from what the player knows:
 *   1. cards due for review, the most overdue first;
 *   2. up to NEW_PER_LESSON cards never seen before;
 *   3. if there is still room, seen cards not due yet, the soonest first;
 *   4. if there is still room (the first lessons), more new cards.
 * The chosen cards are shuffled, so reviews and new cards are mixed.
 */
export function chooseLessonCards(
  allCards: readonly Card[],
  progress: Progress,
  today: string,
  random: Random = Math.random,
): Card[] {
  // Shuffled first, so cards that tie in the sorting below come in a
  // different order each time
  const cards = shuffle(allCards, random);
  const unseen = cards.filter((card) => progress.cards[card.oracle_id] === undefined);
  // Each seen card with its saved record, soonest due date first
  const seen = cards
    .flatMap((card) => {
      const record = progress.cards[card.oracle_id];
      return record === undefined ? [] : [{ card, record }];
    })
    .sort((a, b) => a.record.due.localeCompare(b.record.due));
  const due = seen.filter(({ record }) => isDue(record, today)).map(({ card }) => card);
  const ahead = seen.filter(({ record }) => !isDue(record, today)).map(({ card }) => card);

  const chosen = due.slice(0, LESSON_LENGTH);
  const fill = (from: Card[], most: number) => {
    const room = Math.min(most, LESSON_LENGTH - chosen.length);
    const add = from.filter((card) => !chosen.includes(card)).slice(0, room);
    chosen.push(...add);
  };
  fill(unseen, NEW_PER_LESSON);
  fill(ahead, LESSON_LENGTH);
  fill(unseen, LESSON_LENGTH);
  return shuffle(chosen, random);
}

/**
 * The asked card's own answer was picked: the card itself, or for a
 * question about its cost, its power and toughness or its creature
 * types, its own (see each kind's answer in questionKinds.ts)
 */
export function isCorrect(question: Question, picked: Option): boolean {
  return (
    picked.card.oracle_id === question.card.oracle_id &&
    picked.name === KINDS[question.kind].answer(question.card, question)
  );
}

/**
 * Where a lesson stands. A missed card goes to the back of the queue as
 * a new question, again and again until it is answered right, so the
 * lesson ends with every card answered right at least once.
 */
export interface LessonState {
  /** The questions still to answer, the one on screen first */
  queue: Question[];
  /** How many different cards the lesson is about */
  total: number;
  /** Their oracle_ids in the order first asked: one progress bar segment each */
  order: string[];
  /** How many of them have been answered right */
  done: number;
  /** oracle_ids of the cards answered wrongly at least once */
  missed: string[];
  /** Cards answered right on the first try */
  score: number;
}

export function startLesson(
  allCards: readonly Card[],
  progress: Progress,
  today: string,
  random: Random = Math.random,
  /** Where wrong answers come from beyond allCards, see makeQuestion */
  moreCards: readonly (readonly Card[])[] = [],
): LessonState {
  const queue = chooseLessonCards(allCards, progress, today, random).map((card) =>
    makeQuestion(card, allCards, random, undefined, moreCards),
  );
  return {
    queue,
    total: queue.length,
    order: queue.map((question) => question.card.oracle_id),
    done: 0,
    missed: [],
    score: 0,
  };
}

/** True the first time a card is asked in this lesson - not on a repeat */
export function isFirstTry(lesson: LessonState, card: Card): boolean {
  return !lesson.missed.includes(card.oracle_id);
}

/** The lesson after the question on screen was answered */
export function afterAnswer(
  lesson: LessonState,
  correct: boolean,
  allCards: readonly Card[],
  random: Random = Math.random,
  /** Where wrong answers come from beyond allCards, see makeQuestion */
  moreCards: readonly (readonly Card[])[] = [],
): LessonState {
  const [current, ...rest] = lesson.queue;
  const card = current.card;

  if (correct) {
    return {
      ...lesson,
      queue: rest,
      done: lesson.done + 1,
      score: lesson.score + (isFirstTry(lesson, card) ? 1 : 0),
    };
  }

  // Back of the queue, as a new question: new wrong options in a new
  // order, so the answer can't be remembered by its place. The kind and
  // side stay, so the card is asked the same way it was missed
  return {
    ...lesson,
    queue: [...rest, makeQuestion(card, allCards, random, current, moreCards)],
    missed: isFirstTry(lesson, card) ? [...lesson.missed, card.oracle_id] : lesson.missed,
  };
}

export function isFinished(lesson: LessonState): boolean {
  return lesson.queue.length === 0;
}

/**
 * How a card of the lesson is doing, for its progress bar segment:
 *   todo  - not answered yet
 *   right - answered right on the first try
 *   wrong - answered wrongly, and not yet right on a repeat
 *   fixed - answered wrongly, then right on a repeat
 */
export type SegmentState = 'todo' | 'right' | 'wrong' | 'fixed';

export interface Segment {
  state: SegmentState;
  /** The card of the question on screen */
  current: boolean;
}

/**
 * One segment per card, in the order first asked. `answer` is whether
 * the question on screen was just answered right (null while choosing),
 * so the bar changes as soon as the answer shows.
 */
export function segments(lesson: LessonState, answer: boolean | null): Segment[] {
  const onScreen = lesson.queue[0]?.card.oracle_id;
  // A card with a question still to come isn't answered right yet
  const waiting = new Set(lesson.queue.map((question) => question.card.oracle_id));
  return lesson.order.map((id) => {
    const current = id === onScreen;
    const missedBefore = lesson.missed.includes(id);
    let right = !waiting.has(id);
    let missed = missedBefore;
    if (current && answer !== null) {
      right = answer;
      missed = missedBefore || !answer;
    }
    const state: SegmentState = right ? (missed ? 'fixed' : 'right') : missed ? 'wrong' : 'todo';
    return { state, current };
  });
}
