// What the app remembers about the player, and how it changes.
// No React and no browser storage in here, so it can be tested alone.
// Every function returns a new Progress and leaves the old one as it was.

export interface CardProgress {
  /** How many times this card was answered right */
  right: number;
  wrong: number;
  /** How well the card is known, from 0 (just missed) to 5 - see BOX_WAIT_DAYS */
  box: number;
  /** The day (YYYY-MM-DD) from which the card should be asked again */
  due: string;
}

/**
 * How many days a card waits before it is asked again, by box. A right
 * first answer moves the card up a box, so it waits longer each time;
 * a wrong one drops it to box 0, so it comes back in the next lesson.
 */
export const BOX_WAIT_DAYS = [0, 1, 3, 7, 16, 35];
const TOP_BOX = BOX_WAIT_DAYS.length - 1;
/** From this box on, a card counts as known */
export const KNOWN_BOX = 3;

/** How well a card is known, as shown to the player */
export type Knowledge = 'new' | 'learning' | 'known';

export interface CardStatus {
  knowledge: Knowledge;
  /** Often answered wrongly - shown as an extra warning */
  tricky: boolean;
  /** First answers given to the card so far, and how many were wrong */
  answers: number;
  wrong: number;
}

/** A card counts as tricky once it has this many answers... */
export const TRICKY_MIN_ANSWERS = 3;
/** ...and at least this share of them were wrong */
export const TRICKY_WRONG_SHARE = 0.4;

/** Turns a card's saved record (undefined if never asked) into its labels */
export function cardStatus(record: CardProgress | undefined): CardStatus {
  if (record === undefined) {
    return { knowledge: 'new', tricky: false, answers: 0, wrong: 0 };
  }
  const answers = record.right + record.wrong;
  return {
    knowledge: record.box >= KNOWN_BOX ? 'known' : 'learning',
    tricky: answers >= TRICKY_MIN_ANSWERS && record.wrong / answers >= TRICKY_WRONG_SHARE,
    answers,
    wrong: record.wrong,
  };
}

export interface Progress {
  /** Raise this when the shape changes, so old saved data can be recognized */
  version: 2;
  /** Keyed by oracle_id. A card that was never asked has no entry. */
  cards: Record<string, CardProgress>;
  /** The days (YYYY-MM-DD) on which at least one lesson was finished, oldest first */
  lessonDays: string[];
}

export const EMPTY_PROGRESS: Progress = { version: 2, cards: {}, lessonDays: [] };

/** A date as YYYY-MM-DD on the device's own calendar, not UTC */
export function localDay(date: Date = new Date()): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/** The day `count` days after `day` (or before it, for a negative count) */
export function addDays(day: string, count: number): string {
  const [year, month, date] = day.split('-').map(Number);
  // The Date constructor rolls over month and year ends by itself:
  // day 0 of a month is the last day of the month before
  return localDay(new Date(year, month - 1, date + count));
}

export function previousDay(day: string): string {
  return addDays(day, -1);
}

/** True when a seen card's waiting time is over. YYYY-MM-DD compares as text. */
export function isDue(card: CardProgress, today: string): boolean {
  return card.due <= today;
}

/** How many of these cards have been seen and are due today */
export function dueCount(progress: Progress, oracleIds: readonly string[], today: string): number {
  return oracleIds.filter((id) => {
    const card = progress.cards[id];
    return card !== undefined && isDue(card, today);
  }).length;
}

/** Records the first answer to a card in a lesson, and moves it between boxes */
export function recordAnswer(
  progress: Progress,
  oracleId: string,
  correct: boolean,
  today: string,
): Progress {
  const before = progress.cards[oracleId] ?? { right: 0, wrong: 0, box: 0, due: today };
  let after: CardProgress;
  if (!correct) {
    after = { ...before, wrong: before.wrong + 1, box: 0, due: today };
  } else if (isDue(before, today)) {
    const box = Math.min(before.box + 1, TOP_BOX);
    after = { ...before, right: before.right + 1, box, due: addDays(today, BOX_WAIT_DAYS[box]) };
  } else {
    // Practised before its time: right, but not promoted, or a few
    // lessons in one evening would push every card to the top box
    after = { ...before, right: before.right + 1 };
  }
  return { ...progress, cards: { ...progress.cards, [oracleId]: after } };
}

export function recordLesson(progress: Progress, today: string): Progress {
  if (progress.lessonDays.includes(today)) return progress;
  return { ...progress, lessonDays: [...progress.lessonDays, today].sort() };
}

/**
 * How many days in a row had a finished lesson, ending today.
 * Before today's first lesson the run that ended yesterday still counts,
 * so the streak doesn't drop to zero at midnight.
 */
export function streak(progress: Progress, today: string): number {
  const days = new Set(progress.lessonDays);
  let day = days.has(today) ? today : previousDay(today);
  let count = 0;
  while (days.has(day)) {
    count += 1;
    day = previousDay(day);
  }
  return count;
}

/**
 * Reads saved progress. Missing or damaged text gives empty progress.
 * Progress saved by an older version of the app is upgraded.
 */
export function parseProgress(text: string | null, today: string = localDay()): Progress {
  if (text === null) return EMPTY_PROGRESS;
  try {
    const saved = JSON.parse(text);
    const valid =
      typeof saved?.cards === 'object' &&
      saved.cards !== null &&
      Array.isArray(saved.lessonDays);
    if (valid && saved.version === 2) {
      return saved as Progress;
    }
    if (valid && saved.version === 1) {
      return upgradeFromVersion1(saved, today);
    }
  } catch {
    // Not JSON at all - fall through to empty progress
  }
  return EMPTY_PROGRESS;
}

/**
 * Version 1 had no boxes. Each seen card starts in box 1 if it was
 * answered right more often than wrong, otherwise in box 0, and every
 * one is due today.
 */
function upgradeFromVersion1(
  saved: { cards: Record<string, { right: number; wrong: number }>; lessonDays: string[] },
  today: string,
): Progress {
  const cards: Record<string, CardProgress> = {};
  for (const [id, { right, wrong }] of Object.entries(saved.cards)) {
    cards[id] = { right, wrong, box: right > wrong ? 1 : 0, due: today };
  }
  return { version: 2, cards, lessonDays: saved.lessonDays };
}
