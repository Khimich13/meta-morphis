import {
  type CSSProperties,
  type ReactNode,
  type RefObject,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { flushSync } from 'react-dom';

import CardPicture, { standsIn, TurningLargeView, useOpenOnTurn } from '../components/CardPicture';
import ManaCost from '../components/ManaCost';
import NameCovers, { type NameCover } from '../components/NameCovers';
import StandingLabel, { type PipChange } from '../components/StandingLabel';
import {
  type ArtFrom,
  type Card,
  halfArt,
  isHorizontal,
  partType,
  SIDEWAYS_ART_BOX,
  SIDEWAYS_HALF_ART_BOXES,
} from '../lib/cards';
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
  type Question,
  type Segment,
  segments,
  startLesson,
} from '../lib/quiz';
import { useLargeView } from '../lib/largeView';
import { type Option, type QuestionKind } from '../lib/questionKinds';
import { FILL_REACH, fillName } from '../lib/nameFill';
import { playAnswerSound } from '../lib/sounds';
import './Lesson.css';

interface LessonProps {
  cards: Card[];
  /** Where wrong answers come from beyond `cards`, see makeQuestion in quiz.ts */
  moreCards: readonly (readonly Card[])[];
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
  moreCards,
  progress,
  onAnswer,
  onLessonFinished,
  onDone,
  soundsOn,
}: LessonProps) {
  // The rules for what comes next are in quiz.ts
  const [lesson, setLesson] = useState(() =>
    startLesson(cards, progress, localDay(), Math.random, moreCards),
  );
  // The answer chosen for the question on screen, or null while choosing
  const [picked, setPicked] = useState<Option | null>(null);
  // The card's record before this answer, to show how the answer changed it
  const [before, setBefore] = useState<Before | null>(null);
  // Set at the first tap on an answer, before the screen changes: the
  // buttons stay on screen until the animation swaps them out, and a
  // second tap meanwhile must not answer again
  const answered = useRef(false);
  // The box the full card shows in after an answer, and the card's width
  // in it, so the feedback below can be just as wide
  const pictureBox = useRef<HTMLDivElement>(null);
  const cardWidth = useCardWidth(pictureBox, picked !== null);

  function pick(option: Option) {
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
    const after = afterAnswer(
      lesson,
      isCorrect(lesson.queue[0], picked),
      cards,
      Math.random,
      moreCards,
    );
    if (isFinished(after)) {
      onLessonFinished();
    }
    setLesson(after);
    setPicked(null);
    answered.current = false;
  }

  function restart() {
    setLesson(startLesson(cards, progress, localDay(), Math.random, moreCards));
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
  // The side or half asked about: its artwork, and where on its picture it lands
  const back = question.back && card.back ? card.back : null;
  const art = question.half !== null ? halfArt(card, question.half) : (back ?? card);
  // Cards answered right, including this one as soon as it is
  const done = lesson.done + (answer === true ? 1 : 0);
  const bar = segments(lesson, answer);

  return (
    <section className="lesson">
      <header className="lesson-bar">
        <button className="leave" onClick={onDone} aria-label="Leave the lesson">
          {/* Drawn, not the ✕ character: the system font doesn't have it,
              so it came from a fallback font that sat it higher or lower
              than the card number, differently on each device */}
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 6 18 18M18 6 6 18" />
          </svg>
        </button>
        <LessonProgress bar={bar} done={done} />
        {/* Which card is on screen - on a repeat, the missed card's own number */}
        <span className="position">
          {bar.findIndex((segment) => segment.current) + 1}/{lesson.total}
        </span>
      </header>

      {picked === null ? (
        <>
          {/* The question and what it asks about, together, so the line
              can span exactly the card's width (see Lesson.css) */}
          <div className={`question-body ${question.kind}-question`}>
            {/* The question over the left edge, its label over the right */}
            <div className="question-line">
              <h2 className="question">
                {question.kind === 'picture'
                  ? `Name the ${partType(card, question.back, question.spell, question.half)}`
                  : question.kind === 'cost'
                    ? 'Name the cost'
                    : question.kind === 'powerToughness'
                      ? 'Power and toughness?'
                      : question.kind === 'creatureType'
                        ? 'Creature type?'
                        : 'What is this art from?'}
              </h2>
              <QuestionLabel repeat={repeat} standing={cardStanding(record)} />
            </div>
            {question.kind !== 'artwork' ? (
              <NameHidden
                key={`${card.oracle_id}-${question.kind}-${question.back}-${question.spell}-${question.half}`}
                card={card}
                back={question.back}
                spell={question.spell}
                half={question.half}
                kind={question.kind}
              />
            ) : (
              /* A figure ties the credit to the artwork, for screen readers too */
              <figure className="artwork">
                <Artwork
                  // Its own for each question, so a cut never shows on another
                  key={`${card.oracle_id}-${question.back}-${question.half}`}
                  side={art}
                  transition={artTransition(card, question.back, question.half)}
                />
                {/* Scryfall asks for this whenever the artwork is shown by itself */}
                <figcaption className="credit">
                  Illustrated by {art.artist} · © Wizards of the Coast
                </figcaption>
              </figure>
            )}
          </div>
          <ul className="options">
            {question.options.map((option) => (
              // The answers to a question about the cost are all the same card
              <li key={`${option.card.oracle_id}-${option.name}`}>
                <OptionButton onPick={() => pick(option)}>
                  <AnswerLabel question={question} option={option} />
                </OptionButton>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          {/* After a question about the full card, the covered card turns
              into this one (see Lesson.css), uncovering what it asked for */}
          <div
            ref={pictureBox}
            className={question.kind !== 'artwork' ? 'picture after-picture' : 'picture'}
          >
            {/* One side at a time, which a double-faced card can turn over:
                first the side asked about. The full card shows its own
                artist and copyright. */}
            <CardPicture
              key={card.oracle_id}
              card={card}
              speaker
              openOnTurn
              startOnBack={question.back}
            />
            {/* Where the artwork lands after an answer: the side's art box */}
            {question.kind === 'artwork' && (
              <div
                className={isHorizontal(card, question.back) ? 'art-target sideways' : 'art-target'}
                aria-hidden="true"
                style={artTarget(card, question.back, question.half)}
              />
            )}
          </div>
          <Feedback
            question={question}
            picked={picked}
            before={before}
            record={record}
            cardWidth={cardWidth}
            onContinue={next}
          />
        </>
      )}
    </section>
  );
}

/**
 * An answer button, its name or cost always on one line: one too long
 * for the button gets text just small enough to fit. Measured before the
 * button is first shown, and again whenever its width changes, as when
 * the phone turns.
 */
function OptionButton({ children, onPick }: { children: ReactNode; onPick: () => void }) {
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
      <span ref={text}>{children}</span>
    </button>
  );
}

/** What an answer shows: a card's name, a cost's symbols, or a power and toughness */
function AnswerLabel({ question, option }: { question: Question; option: Option }) {
  return question.kind === 'cost' ? <ManaCost cost={option.name} /> : option.name;
}

/**
 * The artwork asked about: Scryfall's, or for a side whose artwork from
 * Scryfall catches text around it, its art box cut from the side's large
 * picture (see art_from in cards.ts). Nothing shows until the cut is
 * made; if the picture's pixels can't be read, Scryfall's shows instead.
 */
function Artwork({
  side,
  transition,
}: {
  side: { art: string; art_from?: ArtFrom | null };
  transition: string;
}) {
  const from = side.art_from ?? null;
  const [src, setSrc] = useState<string | null>(from ? null : side.art);

  useEffect(() => {
    if (!from) return;
    let cancelled = false;
    let cut: string | null = null;
    const fallBack = () => {
      if (!cancelled) setSrc(side.art);
    };
    const picture = new Image();
    // Lets its pixels be read, and the copy saved on the device be used
    picture.crossOrigin = 'anonymous';
    picture.onerror = fallBack;
    picture.onload = () => {
      const [left, top, width, height] = from.box;
      const across = picture.naturalWidth;
      const down = picture.naturalHeight;
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(width * across);
      canvas.height = Math.round(height * down);
      const context = canvas.getContext('2d');
      if (!context) return fallBack();
      context.drawImage(
        picture,
        Math.round(left * across),
        Math.round(top * down),
        canvas.width,
        canvas.height,
        0,
        0,
        canvas.width,
        canvas.height,
      );
      try {
        canvas.toBlob((blob) => {
          if (cancelled || !blob) return fallBack();
          cut = URL.createObjectURL(blob);
          setSrc(cut);
        });
      } catch {
        // The browser won't share the picture's pixels
        fallBack();
      }
    };
    picture.src = from.picture;
    return () => {
      cancelled = true;
      if (cut) URL.revokeObjectURL(cut);
    };
  }, [from, side.art]);

  if (src === null) return null;
  return (
    /* The alt text must not give the answer away */
    <img
      src={src}
      alt="Card artwork"
      crossOrigin="anonymous"
      style={{ viewTransitionName: transition }}
    />
  );
}

/**
 * The question's full card with its name hidden: in the title bar, it is
 * painted over by the bar around it (see lib/nameFill.ts); wherever else
 * it is printed in the text box, a plain bar covers it (see NameCovers).
 * Everything on the card but its name. The paint is a layer over the
 * picture, which stays as it is, and never covers the artist or
 * copyright. Until it is painted - or if the picture's pixels can't be
 * read - a plain bar covers the title too. `back` shows a transform
 * card's back, with its own name hidden, and `spell` the card with its
 * spell's name hidden instead of its own, and `half` a split card with
 * that half's name hidden. A name printed sideways is painted along its
 * own line, as it reads. `kind` "cost" paints over the mana cost in the
 * title bar instead, the same way, "powerToughness" the power and
 * toughness in their box, and "creatureType" the type line up to its set
 * symbol, all leaving the name in sight.
 *
 * A card printed sideways opens in the large view when the phone turns
 * sideways, the right way up and its name still hidden, as the answer
 * card does (see useOpenOnTurn in CardPicture.tsx).
 */
function NameHidden({
  card,
  back,
  spell,
  half,
  kind,
}: {
  card: Card;
  back: boolean;
  spell: boolean;
  half: number | null;
  /**
   * What the question asks for, which is covered: the name ("picture"),
   * the mana cost, the power and toughness, or the type line
   */
  kind: Exclude<QuestionKind, 'artwork'>;
}) {
  const side =
    half !== null && card.halves
      ? card.halves[half]
      : spell && card.spell
        ? card.spell
        : back && card.back
          ? card.back
          : card;
  const boxes =
    kind === 'cost' && card.cost
      ? [card.cost.box]
      : kind === 'powerToughness' && card.power_toughness
        ? [card.power_toughness.box]
        : kind === 'creatureType' && card.creature_type
          ? [card.creature_type.box]
          : [
              side.name_box ?? [0, 0, 0, 0],
              ...(('name_text_boxes' in side && side.name_text_boxes) || []),
            ];
  const sideways = isHorizontal(card, back);
  const picture = useRef<HTMLImageElement>(null);
  const cardBox = useRef<HTMLDivElement>(null);
  // Where each cover sits, as shares of the card: the name's box, then,
  // once the title is painted, the whole pixels it was painted on, so the
  // paint lines up with the picture's own pixels exactly
  const [cover, setCover] = useState<NameCover>({ places: boxes, painted: null });
  const large = useLargeView();
  const turn = useOpenOnTurn(sideways, cardBox, large);

  function paint() {
    const image = picture.current;
    if (!image?.naturalWidth) return;
    const across = image.naturalWidth;
    const down = image.naturalHeight;
    const reach = Math.round(FILL_REACH * across);
    const box = boxes[0];
    const [x, w] = [box[0], box[2]].map((share) => Math.round(share * across));
    const [y, h] = [box[1], box[3]].map((share) => Math.round(share * down));
    // Along the name and across it: a name printed sideways runs up the
    // picture, and is painted turned a quarter clockwise, as it reads
    const [along, crosswise] = sideways ? [h, w] : [w, h];
    try {
      // The area with a row more above and below it, and room to each side
      const around = document.createElement('canvas');
      around.width = along + 2 * reach;
      around.height = crosswise + 2;
      const context = around.getContext('2d', { willReadFrequently: true });
      if (!context) return;
      if (sideways) {
        context.translate(around.width, 0);
        context.rotate(Math.PI / 2);
      }
      // The same area of the picture either way, turned or not
      const [fromX, fromY] = sideways ? [x - 1, y - reach] : [x - reach, y - 1];
      const [fromW, fromH] = sideways
        ? [around.height, around.width]
        : [around.width, around.height];
      context.drawImage(image, fromX, fromY, fromW, fromH, 0, 0, fromW, fromH);
      const pixels = context.getImageData(0, 0, around.width, around.height).data;
      // A mana cost ends where the title bar does, and a type line a few
      // pixels before its set symbol (see RightSide)
      const rightSide =
        kind === 'cost' ? 'barEnd' : kind === 'creatureType' ? 'beforeSymbol' : 'past';
      const filled = new ImageData(
        fillName(pixels, around.width, reach, Math.random, rightSide),
        along,
        crosswise,
      );
      // The paint, kept as a picture: the large view lays it over its own
      // copy of the card too
      const target = document.createElement('canvas');
      target.width = w;
      target.height = h;
      const out = target.getContext('2d');
      if (!out) return;
      if (sideways) {
        // Turned back: putImageData ignores turning, drawImage doesn't
        const flat = document.createElement('canvas');
        flat.width = along;
        flat.height = crosswise;
        flat.getContext('2d')?.putImageData(filled, 0, 0);
        out.translate(0, h);
        out.rotate(-Math.PI / 2);
        out.drawImage(flat, 0, 0);
      } else {
        out.putImageData(filled, 0, 0);
      }
      setCover({
        places: [[x / across, y / down, w / across, h / down], ...boxes.slice(1)],
        painted: target.toDataURL(),
      });
    } catch {
      // The browser won't share the picture's pixels: the plain bar stays
    }
  }

  // A picture already saved on the device may have loaded before onLoad
  // was listening. Each card gets its own NameHidden (see its key), so
  // this runs once per card.
  useEffect(() => {
    if (picture.current?.complete) paint();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once on purpose
  }, []);

  return (
    <div className="name-hidden">
      <div
        ref={cardBox}
        className="name-hidden-card"
        // The large view's copy stands in for it as it eases back
        style={{ visibility: standsIn(turn, large) ? 'hidden' : undefined }}
      >
        {/* The alt text must not give the answer away. crossOrigin lets
            the picture's pixels be read, and the saved copy be used. */}
        <img
          ref={picture}
          className="card-side"
          src={card.images[back ? 1 : 0]}
          alt={
            kind === 'cost'
              ? 'Card with its mana cost hidden'
              : kind === 'powerToughness'
                ? 'Card with its power and toughness hidden'
                : kind === 'creatureType'
                  ? 'Card with its type line hidden'
                  : 'Card with its name hidden'
          }
          crossOrigin="anonymous"
          onLoad={paint}
        />
        <NameCovers cover={cover} />
      </div>
      <TurningLargeView
        card={card}
        showingBack={back}
        onFlip={() => {}}
        large={large}
        turn={turn}
        cover={cover}
      />
    </div>
  );
}

/**
 * Where the artwork lands on the side asked about: its art box, or for a
 * side printed sideways, its art area turned - a split card's half's
 * alone, when one half is asked about. Null for a side without either.
 */
function landingBox(card: Card, back: boolean, half: number | null): number[] | null {
  if (half !== null && isHorizontal(card, back)) return SIDEWAYS_HALF_ART_BOXES[half];
  if (isHorizontal(card, back)) return SIDEWAYS_ART_BOX;
  return (back ? card.back?.art_box : card.art_box) ?? null;
}

/**
 * The view transition the artwork takes part in after an answer (see
 * Lesson.css): flying into the card's art, or, for a card without a known
 * place for it, shrinking towards the card's middle and fading
 */
function artTransition(card: Card, back: boolean, half: number | null): string {
  return landingBox(card, back, half) ? 'card-art' : 'card-art-soft';
}

/** Where on the card the artwork lands: its art, or the card's middle */
function artTarget(card: Card, back: boolean, half: number | null): CSSProperties {
  const [left, top, width, height] = landingBox(card, back, half) ?? [0.3, 0.3, 0.4, 0.4];
  return {
    viewTransitionName: artTransition(card, back, half),
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

/** A label beside the question: a card missed earlier in the lesson, or a
 *  card never seen before. It names the card's state, not an action, so it
 *  doesn't read as a button. */
function QuestionLabel({ repeat, standing }: { repeat: boolean; standing: Standing }) {
  if (repeat) return <p className="label again">Missed</p>;
  if (standing === 'new') return <p className="label new">New</p>;
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
  question: Question;
  picked: Option;
  /** The card's record before this answer */
  before: Before | null;
  /** The card's saved record, with this answer counted */
  record: CardProgress | undefined;
  /** The full card's width above, in pixels; null until measured */
  cardWidth: number | null;
  onContinue: () => void;
}

/**
 * The width of the full card shown in this box after an answer, in pixels,
 * kept up to date as the screen changes. Null until measured. The card's
 * own CSS (.picture > .card-picture) sizes it from the box the same way:
 * the full width, or less when the height runs out first.
 */
function useCardWidth(box: RefObject<HTMLDivElement | null>, shown: boolean): number | null {
  const [width, setWidth] = useState<number | null>(null);
  useLayoutEffect(() => {
    const element = box.current;
    if (!shown || element === null) return;
    const observer = new ResizeObserver(([entry]) => {
      const room = entry.contentRect;
      setWidth(Math.min(room.width, (room.height * 488) / 680));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [box, shown]);
  return width;
}

function Feedback({ question, picked, before, record, cardWidth, onContinue }: FeedbackProps) {
  const correct = isCorrect(question, picked);
  const change: PipChange | null = before === null ? null : pipChange(before, record, correct);
  // This answer made the card mastered: the moment to celebrate
  const justMastered = change === 'up' && cardStanding(record) === 'mastered';
  const toGo = MASTERED_LEVEL - shownLevel(record);
  // Already answered today: practice, the pips stay as they were
  const practice = before !== null && !before.counted && record !== undefined;
  let line: ReactNode = '';
  if (!correct)
    line = (
      <>
        You picked <AnswerLabel question={question} option={picked} />
      </>
    );
  else if (justMastered) line = '⭐ Mastered!';
  else if (change === 'up' && toGo > 0)
    line = `${toGo} more ${toGo === 1 ? 'day' : 'days'} to Mastered`;
  else if (practice) line = `Counts once a day: back ${backWhen(record.due, localDay())}`;
  return (
    <div
      className={correct ? 'feedback correct' : 'feedback wrong'}
      // As wide as the card above it (see .feedback in Lesson.css)
      style={
        cardWidth === null ? undefined : ({ '--card-width': `${cardWidth}px` } as CSSProperties)
      }
    >
      {/* role="status" makes screen readers announce the result */}
      <div role="status" className="feedback-body">
        <p className="verdict">
          {correct ? 'Correct' : 'Not quite'}
          {practice && <span className="practice-tag"> · practice</span>}
        </p>
        {/* The card's pips, big, animating how this answer changed them */}
        <StandingLabel record={record} change={change} />
        {/* The card is in full view above, with its name, so the words
            only say what the pips can't. One line, always there, so the
            box is the same size after every answer. */}
        <p className="feedback-line">{line}</p>
      </div>
      <button className="primary" onClick={onContinue} autoFocus>
        Continue
      </button>
    </div>
  );
}
