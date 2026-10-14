import { useEffect, useState } from 'react';

import './App.css';
import { type Card, loadCards } from './cards';
import Lesson from './Lesson';
import { savePictures } from './offline';
import {
  type CardProgress,
  localDay,
  type Progress,
  recordAnswer,
  recordLesson,
  streak,
} from './progress';
import { loadProgress, saveProgress } from './storage';

const FORMAT = 'pauper';

export default function App() {
  // null until the card list has arrived
  const [cards, setCards] = useState<Card[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [inLesson, setInLesson] = useState(false);
  // Read from the browser's storage once, when the app starts
  const [progress, setProgress] = useState(loadProgress);
  // How many card pictures are saved on the device, out of how many
  const [pictures, setPictures] = useState({ saved: 0, total: 0 });

  // Runs once, after the page first appears
  useEffect(() => {
    loadCards(FORMAT)
      .then(setCards)
      .catch(() => setFailed(true));
  }, []);

  // Once the card list is here, save its pictures for offline use
  useEffect(() => {
    if (cards !== null) {
      savePictures(cards, (saved, total) => setPictures({ saved, total }));
    }
  }, [cards]);

  // Runs after every change to the progress, so it is never lost
  useEffect(() => {
    saveProgress(progress);
  }, [progress]);

  return (
    <main>
      <h1>Most played cards in {FORMAT}</h1>
      {failed ? (
        <p>
          Could not load the card list. Create it with{' '}
          <code>uv run python -m meta_morphis.export</code> and reload.
        </p>
      ) : cards === null ? (
        <p>Loading…</p>
      ) : inLesson ? (
        <Lesson
          cards={cards}
          onAnswer={(card, correct) =>
            setProgress((before) => recordAnswer(before, card.oracle_id, correct))
          }
          onLessonFinished={() =>
            setProgress((before) => recordLesson(before, localDay()))
          }
          onDone={() => setInLesson(false)}
        />
      ) : (
        <>
          <Summary cards={cards} progress={progress} />
          {pictures.total > 0 && (
            <p className="offline-status">
              {pictures.saved === pictures.total
                ? 'Ready to use offline'
                : `Saving pictures for offline use: ${pictures.saved} of ${pictures.total}`}
            </p>
          )}
          <button onClick={() => setInLesson(true)}>Start lesson</button>
          <CardGrid cards={cards} progress={progress} />
        </>
      )}
      <Notice />
    </main>
  );
}

interface ProgressProps {
  cards: Card[];
  progress: Progress;
}

function Summary({ cards, progress }: ProgressProps) {
  const days = streak(progress, localDay());
  // Only cards in today's list count: one that left the list keeps its
  // saved numbers but is no longer shown
  const seen = cards.filter((card) => card.oracle_id in progress.cards).length;

  return (
    <p className="summary">
      <strong>{days}-day streak</strong> · {seen} of {cards.length} cards seen
    </p>
  );
}

function CardGrid({ cards, progress }: ProgressProps) {
  return (
    <ul className="card-grid">
      {cards.map((card) => (
        <li key={card.oracle_id}>
          <span>{card.name}</span>
          {/* Card pictures are shown as they are: never stretched, covered or dimmed */}
          {/* crossOrigin lets the saved copy of the picture be used */}
          <img
            src={card.images[0]}
            alt={card.name}
            loading="lazy"
            crossOrigin="anonymous"
          />
          <span className="card-progress">{describe(progress.cards[card.oracle_id])}</span>
        </li>
      ))}
    </ul>
  );
}

function describe(card: CardProgress | undefined): string {
  if (card === undefined) return 'new';
  return `${card.right} of ${card.right + card.wrong} right`;
}

function Notice() {
  return (
    <footer>
      {/* Required wording of the Wizards of the Coast Fan Content Policy */}
      <p>
        MetaMorphis is unofficial Fan Content permitted under the Fan Content
        Policy. Not approved/endorsed by Wizards. Portions of the materials
        used are property of Wizards of the Coast. ©Wizards of the Coast LLC.
      </p>
      <p>
        Card data and images come from{' '}
        <a href="https://scryfall.com">Scryfall</a>. The list of most played
        cards comes from <a href="https://www.mtggoldfish.com">MTGGoldfish</a>.
        This app is not affiliated with either.
      </p>
    </footer>
  );
}
