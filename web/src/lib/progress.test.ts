import { expect, test } from 'vitest';

import {
  EMPTY_PROGRESS,
  localDay,
  parseProgress,
  previousDay,
  type Progress,
  recordAnswer,
  recordLesson,
  streak,
} from './progress';

function withLessonsOn(...days: string[]): Progress {
  return { ...EMPTY_PROGRESS, lessonDays: days };
}

test('localDay uses the local calendar and pads month and day', () => {
  expect(localDay(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05');
  expect(localDay(new Date(2026, 9, 13, 0, 1))).toBe('2026-10-13');
});

test('previousDay steps back across month and year ends', () => {
  expect(previousDay('2026-10-13')).toBe('2026-10-12');
  expect(previousDay('2026-10-01')).toBe('2026-09-30');
  expect(previousDay('2026-03-01')).toBe('2026-02-28');
  expect(previousDay('2028-03-01')).toBe('2028-02-29');
  expect(previousDay('2026-01-01')).toBe('2025-12-31');
});

test('recordAnswer counts right and wrong answers per card', () => {
  let progress = EMPTY_PROGRESS;
  progress = recordAnswer(progress, 'hydroblast', true);
  progress = recordAnswer(progress, 'hydroblast', false);
  progress = recordAnswer(progress, 'hydroblast', true);
  progress = recordAnswer(progress, 'pyroblast', false);

  expect(progress.cards).toEqual({
    hydroblast: { right: 2, wrong: 1 },
    pyroblast: { right: 0, wrong: 1 },
  });
});

test('recording does not change the progress it was given', () => {
  const before = recordAnswer(EMPTY_PROGRESS, 'hydroblast', true);
  recordAnswer(before, 'hydroblast', true);
  recordLesson(before, '2026-10-13');

  expect(before.cards).toEqual({ hydroblast: { right: 1, wrong: 0 } });
  expect(before.lessonDays).toEqual([]);
  expect(EMPTY_PROGRESS).toEqual({ version: 1, cards: {}, lessonDays: [] });
});

test('recordLesson keeps one entry per day', () => {
  let progress = recordLesson(EMPTY_PROGRESS, '2026-10-13');
  progress = recordLesson(progress, '2026-10-13');
  progress = recordLesson(progress, '2026-10-14');

  expect(progress.lessonDays).toEqual(['2026-10-13', '2026-10-14']);
});

test('streak is zero with no lessons', () => {
  expect(streak(EMPTY_PROGRESS, '2026-10-13')).toBe(0);
});

test('streak counts the days in a row ending today', () => {
  const progress = withLessonsOn('2026-10-11', '2026-10-12', '2026-10-13');
  expect(streak(progress, '2026-10-13')).toBe(3);
});

test('streak still shows before the first lesson of today', () => {
  const progress = withLessonsOn('2026-10-11', '2026-10-12');
  expect(streak(progress, '2026-10-13')).toBe(2);
});

test('streak is lost after a full day without a lesson', () => {
  const progress = withLessonsOn('2026-10-10', '2026-10-11');
  expect(streak(progress, '2026-10-13')).toBe(0);
});

test('streak only counts the latest run of days', () => {
  const progress = withLessonsOn('2026-10-01', '2026-10-02', '2026-10-12', '2026-10-13');
  expect(streak(progress, '2026-10-13')).toBe(2);
});

test('streak runs across a change of month', () => {
  const progress = withLessonsOn('2026-09-29', '2026-09-30', '2026-10-01');
  expect(streak(progress, '2026-10-01')).toBe(3);
});

test('parseProgress reads back what was saved', () => {
  let progress = recordAnswer(EMPTY_PROGRESS, 'hydroblast', true);
  progress = recordLesson(progress, '2026-10-13');

  expect(parseProgress(JSON.stringify(progress))).toEqual(progress);
});

test('parseProgress gives empty progress for missing or damaged text', () => {
  expect(parseProgress(null)).toEqual(EMPTY_PROGRESS);
  expect(parseProgress('not json')).toEqual(EMPTY_PROGRESS);
  expect(parseProgress('null')).toEqual(EMPTY_PROGRESS);
  expect(parseProgress('{"version": 2}')).toEqual(EMPTY_PROGRESS);
  expect(parseProgress('{"version": 1, "cards": null}')).toEqual(EMPTY_PROGRESS);
});
