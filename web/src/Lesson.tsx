import { useState } from 'react';

import type { Card } from './cards';
import { isCorrect, makeLesson } from './quiz';

interface LessonProps {
  cards: Card[];
  /** Called when the player leaves the lesson */
  onDone: () => void;
}

export default function Lesson({ cards, onDone }: LessonProps) {
  const [questions, setQuestions] = useState(() => makeLesson(cards));
  // Which question is on screen, counting from 0
  const [index, setIndex] = useState(0);
  // The answer chosen for this question, or null while still choosing
  const [picked, setPicked] = useState<Card | null>(null);
  const [score, setScore] = useState(0);

  function pick(option: Card) {
    setPicked(option);
    if (isCorrect(questions[index], option)) {
      setScore(score + 1);
    }
  }

  function next() {
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
        <h2>Lesson complete</h2>
        <p className="score">
          {score} / {questions.length}
        </p>
        <div className="actions">
          <button onClick={restart}>Another lesson</button>
          <button onClick={onDone}>Back to the cards</button>
        </div>
      </section>
    );
  }

  const question = questions[index];
  const card = question.card;

  return (
    <section className="lesson">
      <p>
        Question {index + 1} of {questions.length}
      </p>
      <h2>Which card is this?</h2>

      {/* The alt text must not give the answer away */}
      <img className="art" src={card.art} alt="Card artwork" />
      <p className="credit">
        Illustrated by {card.artist} · © Wizards of the Coast
      </p>

      <ul className="options">
        {question.options.map((option) => (
          <li key={option.oracle_id}>
            <button
              className={optionClass(option, card, picked)}
              disabled={picked !== null}
              onClick={() => pick(option)}
            >
              {option.name}
            </button>
          </li>
        ))}
      </ul>

      {picked !== null && (
        <div className="feedback">
          {/* role="status" makes screen readers announce the result */}
          <p role="status">
            {isCorrect(question, picked) ? '✓ Correct' : `✗ It was ${card.name}`}
          </p>
          <div className="reveal">
            {card.images.map((image) => (
              <img key={image} src={image} alt={card.name} />
            ))}
          </div>
          <button onClick={next} autoFocus>
            Continue
          </button>
        </div>
      )}
    </section>
  );
}

// Once an answer is picked: mark the right option, and the picked one if it was wrong
function optionClass(option: Card, correct: Card, picked: Card | null): string {
  if (picked === null) return '';
  if (option.oracle_id === correct.oracle_id) return 'correct';
  if (option.oracle_id === picked.oracle_id) return 'wrong';
  return '';
}
