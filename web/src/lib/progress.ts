// What the app remembers about the player, and how it changes.
// No React and no browser storage in here, so it can be tested alone.
// Every function returns a new Progress and leaves the old one as it was.

export interface CardProgress {
  /** How many times this card was answered right - one answer a day at most */
  right: number;
  wrong: number;
  /**
   * The card's level, from 0 to TOP_LEVEL: how well it is known. It
   * decides when the card comes back (see BOX_WAIT_DAYS) and is shown to
   * the player as pips. Called a box in spaced repetition, after the
   * boxes of flash cards it imitates.
   */
  box: number;
  /** The day (YYYY-MM-DD) from which the card should be asked again */
  due: string;
  /**
   * The day (YYYY-MM-DD) of the answer that counted last. Missing in
   * progress saved before the app remembered it.
   */
  last?: string;
}

/**
 * How many days a card waits before it is asked again, by level. A right
 * answer moves the card up a level, so it waits longer each time; a wrong
 * one drops it WRONG_DROP levels, and it comes back the next day. (It is
 * also asked again at the end of the same lesson.)
 */
export const BOX_WAIT_DAYS = [0, 1, 3, 7, 16, 35];
/** The highest level */
export const TOP_LEVEL = BOX_WAIT_DAYS.length - 1;
/** How many levels a wrong answer costs */
export const WRONG_DROP = 1;
/** From this level a card is mastered: answered right on at least this many days */
export const MASTERED_LEVEL = 3;

/**
 * How a card is doing:
 *   new      - never answered, marked "New card" when a lesson asks it
 *   learning - below MASTERED_LEVEL, shown by its pips alone
 *   mastered - MASTERED_LEVEL or higher, labelled "Mastered"
 */
export type Standing = 'new' | 'learning' | 'mastered';

/** A card's standing from its saved record (undefined if never asked) */
export function cardStanding(record: CardProgress | undefined): Standing {
  if (record === undefined) return 'new';
  return record.box >= MASTERED_LEVEL ? 'mastered' : 'learning';
}

/**
 * The level the player sees, from 0 to MASTERED_LEVEL: the steps to
 * mastered. The levels above it only make a mastered card wait longer
 * between reviews, so they aren't shown.
 */
export function shownLevel(record: CardProgress | undefined): number {
  return Math.min(record?.box ?? 0, MASTERED_LEVEL);
}

/**
 * A standing in full, e.g. "Level 2 of 3" - shown when a mouse hovers
 * over the label, and read by screen readers
 */
export function standingDetails(record: CardProgress | undefined): string {
  if (record === undefined) return 'Never answered';
  return `Level ${shownLevel(record)} of ${MASTERED_LEVEL}`;
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

/** How many of these cards are mastered */
export function masteredCount(progress: Progress, oracleIds: readonly string[]): number {
  return oracleIds.filter((id) => cardStanding(progress.cards[id]) === 'mastered').length;
}

/** How many of these cards have been seen and are due today */
export function dueCount(progress: Progress, oracleIds: readonly string[], today: string): number {
  return oracleIds.filter((id) => {
    const card = progress.cards[id];
    return card !== undefined && isDue(card, today);
  }).length;
}

/**
 * Records the first answer to a card in a lesson: a right one moves it up
 * a level, a wrong one down. Only the first answer of each day counts:
 * the ones after it are practice, or a few lessons in one evening could
 * master any card.
 */
export function recordAnswer(
  progress: Progress,
  oracleId: string,
  correct: boolean,
  today: string,
): Progress {
  const before = progress.cards[oracleId] ?? { right: 0, wrong: 0, box: 0, due: today };
  if (before.last === today) return progress;
  let after: CardProgress;
  if (!correct) {
    const box = Math.max(before.box - WRONG_DROP, 0);
    // Due tomorrow, not today: another lesson today couldn't count it
    const due = addDays(today, 1);
    after = { ...before, wrong: before.wrong + 1, box, due, last: today };
  } else {
    // Up a level even when asked before its waiting time was over (a
    // lesson with room to spare): it still counts once a day at most
    const box = Math.min(before.box + 1, TOP_LEVEL);
    const due = addDays(today, BOX_WAIT_DAYS[box]);
    after = { ...before, right: before.right + 1, box, due, last: today };
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
