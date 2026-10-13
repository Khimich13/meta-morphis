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
