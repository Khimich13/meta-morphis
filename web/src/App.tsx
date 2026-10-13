import { useEffect, useState } from 'react';

import './App.css';
import { type Card, loadCards } from './cards';

const FORMAT = 'pauper';

export default function App() {
  // null until the card list has arrived
  const [cards, setCards] = useState<Card[] | null>(null);
  const [failed, setFailed] = useState(false);

  // Runs once, after the page first appears
  useEffect(() => {
    loadCards(FORMAT)
      .then(setCards)
      .catch(() => setFailed(true));
  }, []);

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
      ) : (
        <CardGrid cards={cards} />
      )}
    </main>
  );
}

function CardGrid({ cards }: { cards: Card[] }) {
  return (
    <>
      <p>{cards.length} cards</p>
      <ul className="card-grid">
        {cards.map((card) => (
          <li key={card.oracle_id}>
            <span>{card.name}</span>
            {/* Card pictures are shown as they are: never stretched, covered or dimmed */}
            <img src={card.images[0]} alt={card.name} loading="lazy" />
          </li>
        ))}
      </ul>
    </>
  );
}
