// The quiz rules: which cards a lesson asks about, which answers each
// question offers, and whether an answer is right. No React in here,
// so it can be tested without a browser.

import type { Card } from './cards';
import { isDue, type Progress } from './progress';

export const LESSON_LENGTH = 10;
export const OPTION_COUNT = 4;
/** At most this many cards never seen before in a lesson, when others are waiting */
export const NEW_PER_LESSON = 3;

export interface Question {
  /** The card being asked about */
  card: Card;
  /** The answers to choose from, in the order shown: the card itself and wrong ones */
  options: Card[];
}

/** Returns a number from 0 up to, but not including, 1 - like Math.random */
export type Random = () => number;

/** A shuffled copy of the list. The original is left as it was. */
export function shuffle<T>(items: readonly T[], random: Random = Math.random): T[] {
  const result = [...items];
  // Fisher-Yates: walk from the end, swapping each item with a random earlier one
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

export function makeQuestion(
  card: Card,
  allCards: readonly Card[],
  random: Random = Math.random,
): Question {
  const others = allCards.filter((other) => other.oracle_id !== card.oracle_id);
  const wrong = shuffle(others, random).slice(0, OPTION_COUNT - 1);
  return { card, options: shuffle([card, ...wrong], random) };
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

export function isCorrect(question: Question, picked: Card): boolean {
  return picked.oracle_id === question.card.oracle_id;
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
): LessonState {
  const queue = chooseLessonCards(allCards, progress, today, random).map((card) =>
    makeQuestion(card, allCards, random),
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
  // order, so the answer can't be remembered by its place
  return {
    ...lesson,
    queue: [...rest, makeQuestion(card, allCards, random)],
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
