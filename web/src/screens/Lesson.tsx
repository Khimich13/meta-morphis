import { useState } from 'react';

import CardPicture from '../components/CardPicture';
import StandingLabel from '../components/StandingLabel';
import type { Card } from '../lib/cards';
import {
  type CardProgress,
  cardStanding,
  localDay,
  type Progress,
  type Standing,
  STANDING_LABELS,
} from '../lib/progress';
import { canSpeak, sayName } from '../lib/speech';
import {
  afterAnswer,
  isCorrect,
  isFinished,
  isFirstTry,
  startLesson,
} from '../lib/quiz';
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
}

export default function Lesson({
  cards,
  progress,
  onAnswer,
  onLessonFinished,
  onDone,
}: LessonProps) {
  // The rules for what comes next are in quiz.ts
  const [lesson, setLesson] = useState(() => startLesson(cards, progress, localDay()));
  // The answer chosen for the question on screen, or null while choosing
  const [picked, setPicked] = useState<Card | null>(null);
  // The card's standing before this answer was counted, to show how the
  // answer changed it; null for a repeat, which isn't counted
  const [standingBefore, setStandingBefore] = useState<Standing | null>(null);

  function pick(option: Card) {
    const question = lesson.queue[0];
    setPicked(option);
    setStandingBefore(
      isFirstTry(lesson, question.card)
        ? cardStanding(progress.cards[question.card.oracle_id])
        : null,
    );
    // Saved progress counts the first answer to each card only: a right
    // answer on a repeat comes straight after seeing the answer
    if (isFirstTry(lesson, question.card)) {
      onAnswer(question.card, isCorrect(question, option));
    }
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
  }

  function restart() {
    setLesson(startLesson(cards, progress, localDay()));
    setPicked(null);
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
  // Cards answered right, including this one as soon as it is: the bar
  // only moves forward on a right answer
  const done = lesson.done + (picked !== null && isCorrect(question, picked) ? 1 : 0);

  return (
    <section className="lesson">
      <header className="lesson-bar">
        <button className="leave" onClick={onDone} aria-label="Leave the lesson">
          ✕
        </button>
        <div
          className="progress-bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={lesson.total}
          aria-valuenow={done}
        >
          <div style={{ width: `${(done / lesson.total) * 100}%` }} />
        </div>
        <span>
          {done}/{lesson.total}
        </span>
      </header>

      {picked === null ? (
        <>
          <QuestionLabel repeat={repeat} standing={cardStanding(record)} />
          <h2 className="question">Which card is this?</h2>
          {/* A figure ties the credit to the artwork, for screen readers too */}
          <figure className="artwork">
            {/* The alt text must not give the answer away */}
            <img src={card.art} alt="Card artwork" crossOrigin="anonymous" />
            {/* Scryfall asks for this whenever the artwork is shown by itself */}
            <figcaption className="credit">
              Illustrated by {card.artist} · © Wizards of the Coast
            </figcaption>
          </figure>
          <ul className="options">
            {question.options.map((option) => (
              <li key={option.oracle_id}>
                <button onClick={() => pick(option)}>{option.name}</button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <div className="picture">
            {/* One side at a time, which a double-faced card can turn over.
                The full card shows its own artist and copyright. */}
            <CardPicture key={card.oracle_id} card={card} />
          </div>
          <Feedback
            card={card}
            picked={picked}
            standingBefore={standingBefore}
            record={record}
            onContinue={next}
          />
        </>
      )}
    </section>
  );
}

/**
 * A label above the artwork: a repeat, a card never seen before, or one
 * often missed - the same red "Poor" as in the card list, as a warning
 */
function QuestionLabel({ repeat, standing }: { repeat: boolean; standing: Standing }) {
  if (repeat) return <p className="label again">Try again</p>;
  if (standing === 'new') return <p className="label new">New card</p>;
  if (standing === 'poor') return <p className="label standing poor">Poor</p>;
  return null;
}

/** Reads the name aloud; nothing in a browser that can't speak */
function SayButton({ name }: { name: string }) {
  if (!canSpeak()) return null;
  return (
    <button className="say" aria-label={`Say ${name}`} onClick={() => sayName(name)}>
      🔊
    </button>
  );
}

interface FeedbackProps {
  card: Card;
  picked: Card;
  /** The card's standing before this answer; null for a repeat */
  standingBefore: Standing | null;
  /** The card's saved record, with this answer counted */
  record: CardProgress | undefined;
  onContinue: () => void;
}

function Feedback({ card, picked, standingBefore, record, onContinue }: FeedbackProps) {
  const standingNow = cardStanding(record);
  const correct = picked.oracle_id === card.oracle_id;
  return (
    <div className={correct ? 'feedback correct' : 'feedback wrong'}>
      {/* role="status" makes screen readers announce the result */}
      <div role="status">
        {correct ? (
          <p className="verdict">
            ✓ Correct: {card.name} <SayButton name={card.name} />
          </p>
        ) : (
          <>
            <p className="verdict">✗ Not quite</p>
            <p>You picked {picked.name}</p>
            <p>
              It was {card.name} <SayButton name={card.name} />
            </p>
          </>
        )}
        {/* How this answer moved the card, e.g. "Fair → Good" */}
        <p className="standing-change">
          {standingBefore !== null && standingBefore !== standingNow && (
            <>
              <span className={`label standing ${standingBefore}`}>
                {STANDING_LABELS[standingBefore]}
              </span>
              <span aria-hidden="true"> → </span>
            </>
          )}
          <StandingLabel record={record} />
        </p>
      </div>
      <button className="primary" onClick={onContinue} autoFocus>
        Continue
      </button>
    </div>
  );
}
