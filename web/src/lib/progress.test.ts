import { expect, test } from 'vitest';

import {
  addDays,
  BOX_WAIT_DAYS,
  dueCount,
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

const TODAY = '2026-10-15';

test('addDays counts forward and back across month ends', () => {
  expect(addDays('2026-10-15', 1)).toBe('2026-10-16');
  expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
  expect(addDays('2026-12-30', 35)).toBe('2027-02-03');
  expect(addDays('2026-10-01', -1)).toBe('2026-09-30');
});

test('recordAnswer counts right and wrong answers per card', () => {
  let progress = EMPTY_PROGRESS;
  progress = recordAnswer(progress, 'hydroblast', true, TODAY);
  progress = recordAnswer(progress, 'hydroblast', false, TODAY);
  progress = recordAnswer(progress, 'pyroblast', false, TODAY);

  expect(progress.cards.hydroblast).toMatchObject({ right: 1, wrong: 1 });
  expect(progress.cards.pyroblast).toMatchObject({ right: 0, wrong: 1 });
});

test('a new card answered right goes to box 1, due tomorrow', () => {
  const progress = recordAnswer(EMPTY_PROGRESS, 'hydroblast', true, TODAY);
  expect(progress.cards.hydroblast).toEqual({
    right: 1, wrong: 0, box: 1, due: '2026-10-16',
  });
});

test('each right answer on the due day moves a card up a box and waits longer', () => {
  let progress = EMPTY_PROGRESS;
  let day = TODAY;
  for (let box = 1; box <= 5; box++) {
    progress = recordAnswer(progress, 'hydroblast', true, day);
    expect(progress.cards.hydroblast.box).toBe(box);
    expect(progress.cards.hydroblast.due).toBe(addDays(day, BOX_WAIT_DAYS[box]));
    day = progress.cards.hydroblast.due;
  }
  // The top box is as high as it goes
  progress = recordAnswer(progress, 'hydroblast', true, day);
  expect(progress.cards.hydroblast.box).toBe(5);
});

test('a wrong answer drops a card to box 0, due today', () => {
  let progress = EMPTY_PROGRESS;
  progress = recordAnswer(progress, 'hydroblast', true, '2026-10-01');
  progress = recordAnswer(progress, 'hydroblast', true, '2026-10-02');
  progress = recordAnswer(progress, 'hydroblast', false, TODAY);
  expect(progress.cards.hydroblast).toMatchObject({ box: 0, due: TODAY });
});

test('a right answer before the due day does not move the card up', () => {
  let progress = recordAnswer(EMPTY_PROGRESS, 'hydroblast', true, TODAY);
  // Due tomorrow, practised again today
  progress = recordAnswer(progress, 'hydroblast', true, TODAY);
  expect(progress.cards.hydroblast).toEqual({
    right: 2, wrong: 0, box: 1, due: '2026-10-16',
  });
});

test('a wrong answer before the due day still drops the card', () => {
  let progress = recordAnswer(EMPTY_PROGRESS, 'hydroblast', true, TODAY);
  progress = recordAnswer(progress, 'hydroblast', false, TODAY);
  expect(progress.cards.hydroblast).toMatchObject({ box: 0, due: TODAY });
});

test('dueCount counts seen cards whose day has come', () => {
  let progress = recordAnswer(EMPTY_PROGRESS, 'due-today', false, TODAY);
  progress = recordAnswer(progress, 'due-tomorrow', true, TODAY);
  const ids = ['due-today', 'due-tomorrow', 'never-seen'];
  expect(dueCount(progress, ids, TODAY)).toBe(1);
  expect(dueCount(progress, ids, '2026-10-16')).toBe(2);
});

test('recording does not change the progress it was given', () => {
  const before = recordAnswer(EMPTY_PROGRESS, 'hydroblast', true, TODAY);
  recordAnswer(before, 'hydroblast', false, TODAY);
  recordLesson(before, '2026-10-13');

  expect(before.cards).toEqual({
    hydroblast: { right: 1, wrong: 0, box: 1, due: '2026-10-16' },
  });
  expect(before.lessonDays).toEqual([]);
  expect(EMPTY_PROGRESS).toEqual({ version: 2, cards: {}, lessonDays: [] });
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
  let progress = recordAnswer(EMPTY_PROGRESS, 'hydroblast', true, TODAY);
  progress = recordLesson(progress, '2026-10-13');

  expect(parseProgress(JSON.stringify(progress), TODAY)).toEqual(progress);
});

test('parseProgress upgrades progress saved by the first version', () => {
  const saved = {
    version: 1,
    cards: {
      mostly_right: { right: 3, wrong: 1 },
      mostly_wrong: { right: 1, wrong: 2 },
      even: { right: 1, wrong: 1 },
    },
    lessonDays: ['2026-10-13', '2026-10-14'],
  };

  expect(parseProgress(JSON.stringify(saved), TODAY)).toEqual({
    version: 2,
    cards: {
      mostly_right: { right: 3, wrong: 1, box: 1, due: TODAY },
      mostly_wrong: { right: 1, wrong: 2, box: 0, due: TODAY },
      even: { right: 1, wrong: 1, box: 0, due: TODAY },
    },
    lessonDays: ['2026-10-13', '2026-10-14'],
  });
});

test('parseProgress gives empty progress for missing or damaged text', () => {
  expect(parseProgress(null, TODAY)).toEqual(EMPTY_PROGRESS);
  expect(parseProgress('not json', TODAY)).toEqual(EMPTY_PROGRESS);
  expect(parseProgress('null', TODAY)).toEqual(EMPTY_PROGRESS);
  expect(parseProgress('{"version": 2}', TODAY)).toEqual(EMPTY_PROGRESS);
  expect(parseProgress('{"version": 3, "cards": {}, "lessonDays": []}', TODAY)).toEqual(
    EMPTY_PROGRESS,
  );
  expect(parseProgress('{"version": 1, "cards": null}', TODAY)).toEqual(EMPTY_PROGRESS);
});
