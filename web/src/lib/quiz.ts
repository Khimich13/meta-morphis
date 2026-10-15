// The quiz rules: which cards a lesson asks about, which answers each
// question offers, and whether an answer is right. No React in here,
// so it can be tested without a browser.

import type { Card } from './cards';

export const LESSON_LENGTH = 10;
export const OPTION_COUNT = 4;

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

export function makeLesson(
  allCards: readonly Card[],
  random: Random = Math.random,
): Question[] {
  return shuffle(allCards, random)
    .slice(0, LESSON_LENGTH)
    .map((card) => makeQuestion(card, allCards, random));
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
  /** How many of them have been answered right */
  done: number;
  /** oracle_ids of the cards answered wrongly at least once */
  missed: string[];
  /** Cards answered right on the first try */
  score: number;
}

export function startLesson(
  allCards: readonly Card[],
  random: Random = Math.random,
): LessonState {
  const queue = makeLesson(allCards, random);
  return { queue, total: queue.length, done: 0, missed: [], score: 0 };
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
