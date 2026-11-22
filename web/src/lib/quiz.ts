// The quiz rules: which cards a lesson asks about, which answers each
// question offers, and whether an answer is right. No React in here,
// so it can be tested without a browser.

import { type Card, partName, partType, type PowerToughness } from './cards';
import { nearCosts } from './manaCost';
import { isDue, type Progress } from './progress';

export const LESSON_LENGTH = 10;
export const OPTION_COUNT = 4;
/** At most this many cards never seen before in a lesson, when others are waiting */
export const NEW_PER_LESSON = 3;

/**
 * What a question shows:
 *   artwork - the card's artwork alone
 *   picture - the full card, the side asked about, with its name covered
 *             (see name_box in cards.ts), or a spell's alone (see spell),
 *             or a split card's half's (see half)
 *   cost    - the full card with its mana cost covered (see cost in
 *             cards.ts), asking what it costs
 *   powerToughness - the full card with its power and toughness covered
 *             (see power_toughness in cards.ts), asking what they are
 */
export type QuestionKind = 'artwork' | 'picture' | 'cost' | 'powerToughness';

/** An answer to choose from */
export interface Option {
  card: Card;
  /**
   * The name on its button: a double-faced card's is one side's name,
   * the side asked about for the card itself, a random one for a wrong
   * answer - so a back side's name never tells the answer apart. The
   * same for a card with a spell: its spell's name or its main part's,
   * and a split card: one half's. For a question about the cost, a cost
   * as Scryfall writes it, "{1}{U}{U}", and for one about the power and
   * toughness, both as printed, "2/3": then `card` is the card asked
   * about on every answer.
   */
  name: string;
}

export interface Question {
  /** The card being asked about */
  card: Card;
  kind: QuestionKind;
  /** Asked about a double-faced card's back side */
  back: boolean;
  /**
   * Asked about an adventure's or prepare card's spell alone, by the
   * full picture with the spell's name covered (see SpellPart in cards.ts)
   */
  spell: boolean;
  /**
   * The half of a split card asked about, 0 for the first and 1 for the
   * second: by its half of the artwork, or by the full picture with its
   * name covered and the other's in sight (see halves in cards.ts). Null
   * for every other card.
   */
  half: number | null;
  /** The answers to choose from, in the order shown: the card itself and wrong ones */
  options: Option[];
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

/**
 * A question about the card. `same` keeps the kind and side of an earlier
 * question about it; without it, both are picked at random.
 *
 * The wrong answers are of the same type as the part asked about, so the
 * shape of a name never gives the answer away - a planeswalker's "Name,
 * epithet" among three plain names. They come from `allCards` first, the
 * cards being learned, then from each of `moreCards` in turn: the
 * format's other cards, then every format's. Only when all of those run
 * out of that type do cards of other types fill in. A question about the
 * cost offers costs instead (see costOptions), and one about the power
 * and toughness offers those (see powerToughnessOptions).
 */
export function makeQuestion(
  card: Card,
  allCards: readonly Card[],
  random: Random = Math.random,
  same?: Pick<Question, 'kind' | 'back' | 'spell' | 'half'>,
  moreCards: readonly (readonly Card[])[] = [],
): Question {
  // Either side, half the time each, for a card with a back to ask about,
  // either part, for a card with a spell whose name can be hidden, and
  // either half of a split card. Any kind it can be asked by, as often
  // each: by the picture on a side or half whose name can be hidden, by
  // its cost on a card whose cost can be, and by its power and toughness
  // on a card whose power and toughness can be - a spell only by the
  // picture: the artwork is the main part's.
  const back = same?.back ?? (card.back ? random() < 0.5 : false);
  const spell = same?.spell ?? (card.spell?.name_box ? random() < 0.5 : false);
  const half = same?.half ?? (card.halves ? pickHalf(random) : null);
  const nameBox =
    card.halves && half !== null
      ? card.halves[half].name_box
      : back
        ? card.back?.name_box
        : card.name_box;
  const kinds: QuestionKind[] = spell
    ? ['picture']
    : [
        ...(nameBox ? ['picture' as const] : []),
        'artwork',
        ...(card.cost ? ['cost' as const] : []),
        ...(card.power_toughness ? ['powerToughness' as const] : []),
      ];
  const kind =
    same?.kind ?? (kinds.length > 1 ? kinds[Math.floor(random() * kinds.length)] : kinds[0]);
  if (kind === 'cost' && card.cost) {
    return {
      card,
      kind,
      back,
      spell,
      half,
      options: costOptions(card, card.cost.mana_cost, random),
    };
  }
  if (kind === 'powerToughness' && card.power_toughness) {
    return {
      card,
      kind,
      back,
      spell,
      half,
      options: powerToughnessOptions(card, card.power_toughness, random),
    };
  }
  const right = { card, name: partName(card, back, spell, half) };
  const wrong = wrongOptions(
    card,
    partType(card, back, spell, half),
    [allCards, ...moreCards],
    random,
  );
  const options = shuffle([right, ...wrong], random);
  return { card, kind, back, spell, half, options };
}

/**
 * OPTION_COUNT - 1 wrong answers for a question about the card, whose
 * part asked about is of this type: cards with a part of that type
 * first, each named by such a part, the earlier pools' before the later
 * ones', in random order within each pool. Then, if those are too few,
 * any other cards, each named by a random part. A card in more than one
 * pool counts once.
 */
function wrongOptions(
  card: Card,
  type: string,
  pools: readonly (readonly Card[])[],
  random: Random,
): Option[] {
  const seen = new Set([card.oracle_id]);
  const matching: Option[] = [];
  const others: Card[] = [];
  for (const pool of pools) {
    for (const other of shuffle(pool, random)) {
      if (seen.has(other.oracle_id)) continue;
      seen.add(other.oracle_id);
      const parts = answerParts(other).filter((part) => part.type === type);
      if (parts.length > 0) {
        matching.push({ card: other, name: parts[Math.floor(random() * parts.length)].name });
      } else {
        others.push(other);
      }
    }
    if (matching.length >= OPTION_COUNT - 1) break;
  }
  const filler = others.map((other) => ({ card: other, name: wrongName(other, random) }));
  return [...matching, ...filler].slice(0, OPTION_COUNT - 1);
}

/**
 * The answers to a question about the card's cost, in the order shown:
 * its own and OPTION_COUNT - 1 wrong ones near it (see nearCosts), the
 * nearest first, at random among those as near as each other
 */
function costOptions(card: Card, cost: string, random: Random): Option[] {
  const wrong = nearCosts(cost, OPTION_COUNT - 1)
    .flatMap((step) => shuffle(step, random))
    .slice(0, OPTION_COUNT - 1);
  return shuffle([cost, ...wrong], random).map((name) => ({ card, name }));
}

/**
 * The answers to a question about the card's power and toughness, in
 * the order shown: the four corners of a square, its own one of them -
 * with the power one more or one less, the toughness one more or one
 * less, and both. A 2/2 offers 2/2, 3/2, 2/3 and 3/3, or 1/2, 2/2, 1/3
 * and 2/3, and so on. Each answer shares a number with two others, so
 * none stands out; answers all around the card's own (2/2 among 1/2,
 * 3/2 and 2/3) would give it away as the one in the middle. Never below
 * 0, and a toughness of 0 only on a card that has it.
 */
function powerToughnessOptions(
  card: Card,
  { power, toughness }: PowerToughness,
  random: Random,
): Option[] {
  const [p, t] = [Number(power), Number(toughness)];
  const powers = [p, p === 0 || random() < 0.5 ? p + 1 : p - 1];
  const toughnesses = [t, t <= 1 || random() < 0.5 ? t + 1 : t - 1];
  const square = powers.flatMap((a) => toughnesses.map((b) => `${a}/${b}`));
  return shuffle(square, random).map((name) => ({ card, name }));
}

/** Power and toughness as cards print them: "2/3" */
function printedPowerToughness({ power, toughness }: PowerToughness): string {
  return `${power}/${toughness}`;
}

/** Either half of a split card, half the time each */
function pickHalf(random: Random): number {
  return random() < 0.5 ? 1 : 0;
}

/**
 * The parts of a card that can be asked about, each with its name, as
 * its answer button shows it, and its type: a split card's halves, an
 * adventure's or prepare card's main part and spell, a double-faced
 * card's sides, or any other card whole
 */
function answerParts(card: Card): { name: string; type: string }[] {
  const part = (back: boolean, spell: boolean, half: number | null = null) => ({
    name: partName(card, back, spell, half),
    type: partType(card, back, spell, half),
  });
  if (card.halves) return [part(false, false, 0), part(false, false, 1)];
  if (card.spell?.name_box) return [part(false, false), part(false, true)];
  if (card.images.length > 1) return [part(false, false), part(true, false)];
  return [part(false, false)];
}

/**
 * A wrong answer's name: a random side or part of its card, of those
 * that can be asked about, so the right answer's never stands out
 */
function wrongName(card: Card, random: Random): string {
  const parts = answerParts(card);
  return parts[Math.floor(random() * parts.length)].name;
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
 * The card itself was picked - or, for a question about the cost, its
 * cost, and about the power and toughness, its own
 */
export function isCorrect(question: Question, picked: Option): boolean {
  const { cost, power_toughness: powerToughness } = question.card;
  if (question.kind === 'cost') return picked.name === cost?.mana_cost;
  if (question.kind === 'powerToughness') {
    return !!powerToughness && picked.name === printedPowerToughness(powerToughness);
  }
  return picked.card.oracle_id === question.card.oracle_id;
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
