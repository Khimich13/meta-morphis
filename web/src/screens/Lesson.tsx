import { useState } from 'react';

import type { Card } from '../lib/cards';
import { cardStatus, type Knowledge, localDay, type Progress } from '../lib/progress';
import CardPicture from './CardPicture';
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

  function pick(option: Card) {
    const question = lesson.queue[0];
    setPicked(option);
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
  const status = cardStatus(progress.cards[card.oracle_id]);
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
          <QuestionLabel repeat={repeat} knowledge={status.knowledge} tricky={status.tricky} />
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
            missedNote={
              status.tricky
                ? `You've missed this card ${status.wrong} of ${status.answers} times`
                : null
            }
            onContinue={next}
          />
        </>
      )}
    </section>
  );
}

/**
 * One label above the artwork, the most useful one: a repeat says so
 * first, then a card never seen before, then one often missed.
 */
function QuestionLabel({
  repeat,
  knowledge,
  tricky,
}: {
  repeat: boolean;
  knowledge: Knowledge;
  tricky: boolean;
}) {
  if (repeat) return <p className="label tricky">Try again</p>;
  if (knowledge === 'new') return <p className="label new">New card</p>;
  if (tricky) return <p className="label tricky">Tricky card</p>;
  return null;
}

interface FeedbackProps {
  card: Card;
  picked: Card;
  /** Shown after a wrong answer to a card that is often missed */
  missedNote: string | null;
  onContinue: () => void;
}

function Feedback({ card, picked, missedNote, onContinue }: FeedbackProps) {
  const correct = picked.oracle_id === card.oracle_id;
  return (
    <div className={correct ? 'feedback correct' : 'feedback wrong'}>
      {/* role="status" makes screen readers announce the result */}
      <div role="status">
        {correct ? (
          <p className="verdict">✓ Correct: {card.name}</p>
        ) : (
          <>
            <p className="verdict">✗ Not quite</p>
            <p>You picked {picked.name}</p>
            <p>It was {card.name}</p>
            {missedNote && <p className="missed-note">{missedNote}</p>}
          </>
        )}
      </div>
      <button className="primary" onClick={onContinue} autoFocus>
        Continue
      </button>
    </div>
  );
}
