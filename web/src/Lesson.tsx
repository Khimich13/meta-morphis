import { useState } from 'react';

import type { Card } from './cards';
import './Lesson.css';
import { isCorrect, makeLesson } from './quiz';

interface LessonProps {
  cards: Card[];
  /** Called once for every answer given */
  onAnswer: (card: Card, correct: boolean) => void;
  /** Called once when the last question has been answered */
  onLessonFinished: () => void;
  /** Called when the player leaves the lesson, finished or not */
  onDone: () => void;
}

export default function Lesson({
  cards,
  onAnswer,
  onLessonFinished,
  onDone,
}: LessonProps) {
  const [questions, setQuestions] = useState(() => makeLesson(cards));
  // Which question is on screen, counting from 0
  const [index, setIndex] = useState(0);
  // The answer chosen for this question, or null while still choosing
  const [picked, setPicked] = useState<Card | null>(null);
  const [score, setScore] = useState(0);

  function pick(option: Card) {
    const correct = isCorrect(questions[index], option);
    setPicked(option);
    if (correct) {
      setScore(score + 1);
    }
    onAnswer(questions[index].card, correct);
  }

  function next() {
    if (index + 1 === questions.length) {
      onLessonFinished();
    }
    setIndex(index + 1);
    setPicked(null);
  }

  function restart() {
    setQuestions(makeLesson(cards));
    setIndex(0);
    setPicked(null);
    setScore(0);
  }

  if (index >= questions.length) {
    return (
      <section className="lesson">
        <div className="lesson-done">
          <h2>Lesson complete</h2>
          <p className="score">
            {score} / {questions.length}
          </p>
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

  const question = questions[index];
  const card = question.card;
  // A question counts as done in the progress bar once it is answered
  const answered = index + (picked === null ? 0 : 1);

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
          aria-valuemax={questions.length}
          aria-valuenow={answered}
        >
          <div style={{ width: `${(answered / questions.length) * 100}%` }} />
        </div>
        <span>
          {index + 1}/{questions.length}
        </span>
      </header>

      {picked === null ? (
        <>
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
            {/* Only the front: two sides would each be too small to read.
                The full card shows its own artist and copyright. */}
            <img src={card.images[0]} alt={card.name} crossOrigin="anonymous" />
          </div>
          <Feedback card={card} picked={picked} onContinue={next} />
        </>
      )}
    </section>
  );
}

interface FeedbackProps {
  card: Card;
  picked: Card;
  onContinue: () => void;
}

function Feedback({ card, picked, onContinue }: FeedbackProps) {
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
          </>
        )}
      </div>
      <button className="primary" onClick={onContinue} autoFocus>
        Continue
      </button>
    </div>
  );
}
