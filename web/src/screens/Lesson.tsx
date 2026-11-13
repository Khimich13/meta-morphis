import { type CSSProperties, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';

import CardPicture from '../components/CardPicture';
import StandingLabel, { type PipChange } from '../components/StandingLabel';
import { type Card, isHorizontal, SIDEWAYS_ART_BOX } from '../lib/cards';
import {
  backWhen,
  type CardProgress,
  cardStanding,
  localDay,
  MASTERED_LEVEL,
  type Progress,
  shownLevel,
  type Standing,
} from '../lib/progress';
import {
  afterAnswer,
  isCorrect,
  isFinished,
  isFirstTry,
  type Segment,
  segments,
  startLesson,
} from '../lib/quiz';
import { FILL_REACH, fillName } from '../lib/nameFill';
import { playAnswerSound } from '../lib/sounds';
import './Lesson.css';

interface LessonProps {
  cards: Card[];
  /** Decides which cards the lesson asks about */
  progress: Progress;
  /** Called with the first answer to each card - repeats are not reported */
  onAnswer: (card: Card, correct: boolean) => void;
  /** Called once when the last question has been answered */
  onLessonFinished: () => void;
  /** Called when the player leaves the lesson, finished or not */
  onDone: () => void;
  /** Whether answers make a sound, see lib/sounds.ts */
  soundsOn: boolean;
}

export default function Lesson({
  cards,
  progress,
  onAnswer,
  onLessonFinished,
  onDone,
  soundsOn,
}: LessonProps) {
  // The rules for what comes next are in quiz.ts
  const [lesson, setLesson] = useState(() => startLesson(cards, progress, localDay()));
  // The answer chosen for the question on screen, or null while choosing
  const [picked, setPicked] = useState<Card | null>(null);
  // The card's record before this answer, to show how the answer changed it
  const [before, setBefore] = useState<Before | null>(null);
  // Set at the first tap on an answer, before the screen changes: the
  // buttons stay on screen until the animation swaps them out, and a
  // second tap meanwhile must not answer again
  const answered = useRef(false);

  function pick(option: Card) {
    if (answered.current) return;
    answered.current = true;
    const question = lesson.queue[0];
    const answer = () => {
      setPicked(option);
      const record = progress.cards[question.card.oracle_id];
      // A repeat in the lesson never counts: the card was answered today
      const counted = isFirstTry(lesson, question.card) && record?.last !== localDay();
      setBefore({ record, counted });
      // Saved progress counts the first answer to each card only: a right
      // answer on a repeat comes straight after seeing the answer
      if (isFirstTry(lesson, question.card)) {
        onAnswer(question.card, isCorrect(question, option));
      }
    };
    const correct = isCorrect(question, option);
    // At once, before any animation: the sound answers the tap itself
    if (soundsOn) playAnswerSound(correct);
    if (prefersLessMotion()) {
      answer();
      return;
    }
    // Once the card is there, it settles with a small pulse after a right
    // answer, and shakes its head after a wrong one
    const afterwards = correct ? pulseCard : shakeCard;
    if (!('startViewTransition' in document)) {
      flushSync(answer);
      afterwards();
      return;
    }
    // The artwork flies into the full card's art box, a view transition
    // (see Lesson.css). The browser captures the screen before and after
    // the change and morphs between the two. .answer-animating marks the
    // page meanwhile, see Lesson.css.
    const page = document.documentElement;
    page.classList.add('answer-animating');
    const transition = document.startViewTransition(async () => {
      flushSync(answer);
      await cardPictureReady();
    });
    transition.finished
      .catch(() => {
        // The animation failed: the answer is shown anyway, by flushSync
      })
      .finally(() => {
        page.classList.remove('answer-animating');
        afterwards();
      });
  }

  function next() {
    // Continue only appears after an answer, so this is just a safeguard
    if (picked === null) return;
    const after = afterAnswer(lesson, isCorrect(lesson.queue[0], picked), cards);
    if (isFinished(after)) {
      onLessonFinished();
    }
    setLesson(after);
    setPicked(null);
    answered.current = false;
  }

  function restart() {
    setLesson(startLesson(cards, progress, localDay()));
    setPicked(null);
    answered.current = false;
  }

  if (isFinished(lesson)) {
    return (
      <section className="lesson">
        <div className="lesson-done">
          <h2>Lesson complete</h2>
          <p className="score">
            {lesson.score} / {lesson.total}
          </p>
          <p>right on the first try</p>
        </div>
        <div className="lesson-actions">
          <button className="primary" onClick={restart}>
            Another lesson
          </button>
          <button onClick={onDone}>Back</button>
        </div>
      </section>
    );
  }

  const question = lesson.queue[0];
  const card = question.card;
  const repeat = !isFirstTry(lesson, card);
  // Read from the saved progress, so after an answer it includes it
  const record = progress.cards[card.oracle_id];
  // Whether the question on screen was answered right; null while choosing
  const answer = picked === null ? null : isCorrect(question, picked);
  // Cards answered right, including this one as soon as it is
  const done = lesson.done + (answer === true ? 1 : 0);
  const bar = segments(lesson, answer);

  return (
    <section className="lesson">
      <header className="lesson-bar">
        <button className="leave" onClick={onDone} aria-label="Leave the lesson">
          ✕
        </button>
        <LessonProgress bar={bar} done={done} />
        {/* Which card is on screen - on a repeat, the missed card's own number */}
        <span className="position">
          {bar.findIndex((segment) => segment.current) + 1}/{lesson.total}
        </span>
      </header>

      {picked === null ? (
        <>
          <QuestionLabel repeat={repeat} standing={cardStanding(record)} />
          <h2 className="question">
            {question.kind === 'picture' ? 'Which card is this?' : 'Which card has this artwork?'}
          </h2>
          {question.kind === 'picture' ? (
            <NameHidden key={card.oracle_id} card={card} />
          ) : (
            /* A figure ties the credit to the artwork, for screen readers too */
            <figure className="artwork">
              {/* The alt text must not give the answer away */}
              <img
                src={card.art}
                alt="Card artwork"
                crossOrigin="anonymous"
                style={{ viewTransitionName: artTransition(card) }}
              />
              {/* Scryfall asks for this whenever the artwork is shown by itself */}
              <figcaption className="credit">
                Illustrated by {card.artist} · © Wizards of the Coast
              </figcaption>
            </figure>
          )}
          <ul className="options">
            {question.options.map((option) => (
              <li key={option.oracle_id}>
                <OptionButton name={option.name} onPick={() => pick(option)} />
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          {/* After a picture question, the covered card turns into this
              one (see Lesson.css), uncovering the name */}
          <div className={question.kind === 'picture' ? 'picture after-picture' : 'picture'}>
            {/* One side at a time, which a double-faced card can turn over.
                The full card shows its own artist and copyright. */}
            <CardPicture key={card.oracle_id} card={card} speaker openOnTurn />
            {/* Where the artwork lands after an answer: the card's art box */}
            {question.kind === 'artwork' && (
              <div
                className={isHorizontal(card, false) ? 'art-target sideways' : 'art-target'}
                aria-hidden="true"
                style={artTarget(card)}
              />
            )}
          </div>
          <Feedback card={card} picked={picked} before={before} record={record} onContinue={next} />
        </>
      )}
    </section>
  );
}

/**
 * An answer button, its name always on one line: a name too long for the
 * button gets text just small enough to fit. Measured before the button is
 * first shown, and again whenever its width changes, as when the phone
 * turns.
 */
function OptionButton({ name, onPick }: { name: string; onPick: () => void }) {
  const button = useRef<HTMLButtonElement>(null);
  const text = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const box = button.current;
    const span = text.current;
    if (!box || !span) return;
    let width = -1;
    const fit = () => {
      // Only a new width can change the fit; the text's own size changes
      // the button's height, which must not measure it again
      if (box.clientWidth === width) return;
      width = box.clientWidth;
      // The size is the button's own, not the span's: a smaller span alone
      // would sit low, on the line of the full-size text
      box.style.fontSize = '';
      const style = getComputedStyle(box);
      const room = width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      const needed = span.getBoundingClientRect().width;
      if (needed > room) box.style.fontSize = `${Math.floor((room / needed) * 1000) / 1000}em`;
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  return (
    <button ref={button} onClick={onPick}>
      <span ref={text}>{name}</span>
    </button>
  );
}

/**
 * The question's full card with its name painted over by what is around
 * it (see lib/nameFill.ts): in the title bar, and wherever else it is
 * printed in the text box. Everything on the card but its name. The
 * paint is a layer over the picture, which stays as it is, and never
 * covers the artist or copyright. Until it is painted - or if the
 * picture's pixels can't be read - plain bars cover the name instead.
 */
function NameHidden({ card }: { card: Card }) {
  const boxes = [card.name_box ?? [0, 0, 0, 0], ...(card.name_text_boxes ?? [])];
  const picture = useRef<HTMLImageElement>(null);
  const canvases = useRef<(HTMLCanvasElement | null)[]>([]);
  // Where each cover sits, as shares of the card: the name's box, then,
  // once painted, the whole pixels it was painted on, so the paint lines
  // up with the picture's own pixels exactly
  const [places, setPlaces] = useState<number[][]>(boxes);
  const [painted, setPainted] = useState(false);

  function paint() {
    const image = picture.current;
    if (!image?.naturalWidth) return;
    const across = image.naturalWidth;
    const down = image.naturalHeight;
    const reach = Math.round(FILL_REACH * across);
    try {
      const painting = boxes.map((box, i) => {
        const target = canvases.current[i];
        const [x, w] = [box[0], box[2]].map((share) => Math.round(share * across));
        const [y, h] = [box[1], box[3]].map((share) => Math.round(share * down));
        // The area with a row more above and below it, and room to each side
        const around = document.createElement('canvas');
        around.width = w + 2 * reach;
        around.height = h + 2;
        const context = around.getContext('2d', { willReadFrequently: true });
        if (!context || !target) return null;
        context.drawImage(
          image,
          x - reach,
          y - 1,
          around.width,
          around.height,
          0,
          0,
          around.width,
          around.height,
        );
        const pixels = context.getImageData(0, 0, around.width, around.height).data;
        return () => {
          target.width = w;
          target.height = h;
          target
            .getContext('2d')
            ?.putImageData(
              new ImageData(fillName(pixels, around.width, reach, i ? 'text' : 'title'), w, h),
              0,
              0,
            );
          return [x / across, y / down, w / across, h / down];
        };
      });
      // All of them or none: each is read before any is painted, as the
      // paint of one could otherwise be read into another next to it
      if (painting.some((step) => step === null)) return;
      setPlaces(painting.map((step) => step!()));
      setPainted(true);
    } catch {
      // The browser won't share the picture's pixels: the plain bars stay
    }
  }

  // A picture already saved on the device may have loaded before onLoad
  // was listening. Each card gets its own NameHidden (see its key), so
  // this runs once per card.
  useEffect(() => {
    if (picture.current?.complete) paint();
  }, []);

  return (
    <div className="name-hidden">
      <div className="name-hidden-card">
        {/* The alt text must not give the answer away. crossOrigin lets
            the picture's pixels be read, and the saved copy be used. */}
        <img
          ref={picture}
          className="card-side"
          src={card.images[0]}
          alt="Card with its name hidden"
          crossOrigin="anonymous"
          onLoad={paint}
        />
        {places.map((place, i) => (
          <div
            key={i}
            className={painted ? 'name-cover painted' : 'name-cover'}
            aria-hidden="true"
            style={{
              left: `${place[0] * 100}%`,
              top: `${place[1] * 100}%`,
              width: `${place[2] * 100}%`,
              height: `${place[3] * 100}%`,
            }}
          >
            <canvas
              ref={(element) => {
                canvases.current[i] = element;
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Where the artwork lands on the card: its art box, or for a card printed
 * sideways, its art area turned. Null for a card without either.
 */
function landingBox(card: Card): number[] | null {
  return isHorizontal(card, false) ? SIDEWAYS_ART_BOX : (card.art_box ?? null);
}

/**
 * The view transition the artwork takes part in after an answer (see
 * Lesson.css): flying into the card's art, or, for a card without a known
 * place for it, shrinking towards the card's middle and fading
 */
function artTransition(card: Card): string {
  return landingBox(card) ? 'card-art' : 'card-art-soft';
}

/** Where on the card the artwork lands: its art, or the card's middle */
function artTarget(card: Card): CSSProperties {
  const [left, top, width, height] = landingBox(card) ?? [0.3, 0.3, 0.4, 0.4];
  return {
    viewTransitionName: artTransition(card),
    '--box-left': left,
    '--box-top': top,
    '--box-width': width,
    '--box-height': height,
  } as CSSProperties;
}

/** The device asks for less motion: no animations after answering */
function prefersLessMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * After a right answer: the full card grows a little and back, as if
 * settling into place. It only grows; the picture itself is untouched.
 */
function pulseCard() {
  document
    .querySelector('.picture .card-picture')
    ?.animate([{ scale: '1' }, { scale: '1.03' }, { scale: '1' }], {
      duration: 260,
      easing: 'ease-in-out',
    });
}

/**
 * After a wrong answer: the full card shakes briefly from side to side,
 * like a head saying no. It only moves; the picture itself is untouched.
 */
function shakeCard() {
  document
    .querySelector('.picture .card-picture')
    ?.animate(
      [
        { transform: 'translateX(0)' },
        { transform: 'translateX(-9px)' },
        { transform: 'translateX(8px)' },
        { transform: 'translateX(-6px)' },
        { transform: 'translateX(4px)' },
        { transform: 'translateX(-2px)' },
        { transform: 'translateX(0)' },
      ],
      { duration: 420, easing: 'ease-out' },
    );
}

/**
 * Waits until the full card's picture can be drawn, so the animation
 * doesn't capture a blank card - but at most 300ms, so a slow download
 * never holds it up
 */
function cardPictureReady(): Promise<unknown> {
  const picture = document.querySelector<HTMLImageElement>('.picture img');
  if (picture === null) return Promise.resolve();
  return Promise.race([
    picture.decode().catch(() => {}),
    new Promise((resolve) => setTimeout(resolve, 300)),
  ]);
}

const SEGMENT_NAMES = {
  todo: 'not answered yet',
  right: 'right on the first try',
  wrong: 'missed',
  fixed: 'right on a second try',
};

/**
 * The lesson's progress: one segment per card, green when answered right
 * on the first try, red while missed, amber once right on a repeat, gray
 * when not reached yet. The card on screen has a taller, outlined one.
 */
function LessonProgress({ bar, done }: { bar: Segment[]; done: number }) {
  const position = bar.findIndex((segment) => segment.current) + 1;
  const missed = bar.filter((segment) => segment.state === 'wrong').length;
  const summary =
    (position > 0 ? `Card ${position} of ${bar.length}` : `${done} of ${bar.length} done`) +
    (missed > 0 ? `, ${missed} missed` : '');
  return (
    <div
      className="lesson-progress"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={bar.length}
      aria-valuenow={done}
      aria-valuetext={summary}
    >
      {bar.map((segment, i) => (
        <span
          key={i}
          className={`segment ${segment.state}${segment.current ? ' current' : ''}`}
          title={`Card ${i + 1}: ${SEGMENT_NAMES[segment.state]}`}
        />
      ))}
    </div>
  );
}

/** A label above the artwork: a repeat, or a card never seen before */
function QuestionLabel({ repeat, standing }: { repeat: boolean; standing: Standing }) {
  if (repeat) return <p className="label again">Try again</p>;
  if (standing === 'new') return <p className="label new">New card</p>;
  return null;
}

/** A card's record before an answer */
interface Before {
  /** undefined for a card never seen before */
  record: CardProgress | undefined;
  /**
   * False when the card was already answered today, in this lesson or
   * another: only the first answer of a day counts (see recordAnswer)
   */
  counted: boolean;
}

/** How a counted answer changed the pips, to animate them */
function pipChange(before: Before, after: CardProgress | undefined, correct: boolean) {
  if (!before.counted) return null;
  const from = shownLevel(before.record);
  const to = shownLevel(after);
  if (to > from) return 'up';
  if (to < from) return 'down';
  // Wrong with no pip to take away: at ○○○, or mastered above level 3
  return correct ? null : 'miss';
}

interface FeedbackProps {
  card: Card;
  picked: Card;
  /** The card's record before this answer */
  before: Before | null;
  /** The card's saved record, with this answer counted */
  record: CardProgress | undefined;
  onContinue: () => void;
}

function Feedback({ card, picked, before, record, onContinue }: FeedbackProps) {
  const correct = picked.oracle_id === card.oracle_id;
  const change: PipChange | null = before === null ? null : pipChange(before, record, correct);
  // This answer made the card mastered: the moment to celebrate
  const justMastered = change === 'up' && cardStanding(record) === 'mastered';
  const toGo = MASTERED_LEVEL - shownLevel(record);
  return (
    <div className={correct ? 'feedback correct' : 'feedback wrong'}>
      {/* role="status" makes screen readers announce the result */}
      <div role="status" className="feedback-body">
        <p className="verdict">{correct ? 'Correct' : 'Not quite'}</p>
        {/* The card's pips, big, animating how this answer changed them */}
        <StandingLabel record={record} change={change} />
        {/* The card is in full view above, with its name, so the words
            only say what the pips can't */}
        {correct && justMastered && <p className="feedback-line">⭐ Mastered!</p>}
        {correct && change === 'up' && toGo > 0 && (
          <p className="feedback-line">
            {toGo} more {toGo === 1 ? 'day' : 'days'} to Mastered
          </p>
        )}
        {!correct && <p className="feedback-line">You picked {picked.name}</p>}
        {before !== null && !before.counted && record !== undefined && (
          <p className="practice-note">
            Counts once a day: back {backWhen(record.due, localDay())}
          </p>
        )}
      </div>
      <button className="primary" onClick={onContinue} autoFocus>
        Continue
      </button>
    </div>
  );
}
