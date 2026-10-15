// What the app remembers about the player, and how it changes.
// No React and no browser storage in here, so it can be tested alone.
// Every function returns a new Progress and leaves the old one as it was.

export interface CardProgress {
  /** How many times this card was answered right */
  right: number;
  wrong: number;
}

export interface Progress {
  /** Raise this when the shape changes, so old saved data can be recognized */
  version: 1;
  /** Keyed by oracle_id. A card that was never asked has no entry. */
  cards: Record<string, CardProgress>;
  /** The days (YYYY-MM-DD) on which at least one lesson was finished, oldest first */
  lessonDays: string[];
}

export const EMPTY_PROGRESS: Progress = { version: 1, cards: {}, lessonDays: [] };

/** A date as YYYY-MM-DD on the device's own calendar, not UTC */
export function localDay(date: Date = new Date()): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

export function previousDay(day: string): string {
  const [year, month, date] = day.split('-').map(Number);
  // Day 0 of a month is the last day of the month before, so this
  // steps back across month and year ends correctly
  return localDay(new Date(year, month - 1, date - 1));
}

export function recordAnswer(
  progress: Progress,
  oracleId: string,
  correct: boolean,
): Progress {
  const before = progress.cards[oracleId] ?? { right: 0, wrong: 0 };
  const after = correct
    ? { ...before, right: before.right + 1 }
    : { ...before, wrong: before.wrong + 1 };
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

/** Reads saved progress. Missing or damaged text gives empty progress. */
export function parseProgress(text: string | null): Progress {
  if (text === null) return EMPTY_PROGRESS;
  try {
    const saved = JSON.parse(text);
    if (
      saved?.version === 1 &&
      typeof saved.cards === 'object' &&
      saved.cards !== null &&
      Array.isArray(saved.lessonDays)
    ) {
      return saved as Progress;
    }
  } catch {
    // Not JSON at all - fall through to empty progress
  }
  return EMPTY_PROGRESS;
}
