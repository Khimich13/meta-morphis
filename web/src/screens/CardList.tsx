import { useState } from 'react';

import { type Card, formatLabel } from '../lib/cards';
import { LIST_LABELS, type Selection } from '../lib/formats';
import { useLargeView } from '../lib/largeView';
import { type CardProgress, cardStatus, type Progress } from '../lib/progress';
import { type Direction, step } from '../lib/swipe';
import CardPicture, { Enlarged, LargeCard } from './CardPicture';

interface CardListProps {
  selection: Selection;
  cards: Card[];
  progress: Progress;
  onBack: () => void;
}

/**
 * How the card in the large view arrived: opened, moved to from either
 * side, or bounced back after trying to move past either end of the list
 */
type Arrival = 'opened' | 'from-right' | 'from-left' | 'bounce-next' | 'bounce-previous';

export default function CardList({ selection, cards, progress, onBack }: CardListProps) {
  // "Most played in Pauper", or "Most played creatures in Pauper"
  const what = selection.kind === 'all' ? '' : `${LIST_LABELS[selection.kind].toLowerCase()} `;

  // The double-faced cards showing their back, by oracle_id. Kept here so
  // the large view shows the same side as the small picture.
  const [backs, setBacks] = useState<Set<string>>(new Set());
  function flip(card: Card) {
    setBacks((before) => {
      const after = new Set(before);
      if (after.has(card.oracle_id)) after.delete(card.oracle_id);
      else after.add(card.oracle_id);
      return after;
    });
  }

  // One large view for the whole list, which can move between its cards
  const large = useLargeView();
  const [index, setIndex] = useState(0);
  const [arrival, setArrival] = useState<Arrival>('opened');
  // Counts bounces, so a second bounce in a row replays the animation
  const [bounces, setBounces] = useState(0);

  function open(position: number) {
    setIndex(position);
    setArrival('opened');
    large.open();
  }

  function move(direction: Direction) {
    const target = step(index, direction, cards.length);
    if (target === index) {
      // At an end of the list: a short bounce shows there is nothing further
      setArrival(direction === 'next' ? 'bounce-next' : 'bounce-previous');
      setBounces(bounces + 1);
      return;
    }
    // Swiping left brings the next card in from the right
    setArrival(direction === 'next' ? 'from-right' : 'from-left');
    setIndex(target);
  }

  const shown = cards[index];

  return (
    <main className="card-list">
      <header className="card-list-bar">
        <button onClick={onBack}>← Back</button>
        <h1>
          Most played {what}in {formatLabel(selection.format)}
        </h1>
      </header>
      <ul className="card-grid">
        {cards.map((card, position) => (
          <li key={card.oracle_id}>
            <span>{card.name}</span>
            <CardPicture
              card={card}
              lazy
              showingBack={backs.has(card.oracle_id)}
              onFlip={() => flip(card)}
              onEnlarge={() => open(position)}
            />
            <CardRecord record={progress.cards[card.oracle_id]} />
          </li>
        ))}
      </ul>
      {large.isOpen && shown !== undefined && (
        <Enlarged
          onClose={large.close}
          onMove={move}
          hasPrevious={index > 0}
          hasNext={index < cards.length - 1}
        >
          {/* Where in the list, which also shows when an end is reached */}
          <p className="position" aria-live="polite">
            {index + 1} / {cards.length}
          </p>
          {/* A new key for each card, and for each bounce, makes it a new
              element, so its animation plays again */}
          <div key={`${shown.oracle_id}-${bounces}`} className={`arriving ${arrival}`}>
            <LargeCard
              card={shown}
              showingBack={backs.has(shown.oracle_id)}
              onFlip={() => flip(shown)}
            />
          </div>
        </Enlarged>
      )}
    </main>
  );
}

/** A card's labels, then its record below them, e.g. "3 of 6 right" */
function CardRecord({ record }: { record: CardProgress | undefined }) {
  const status = cardStatus(record);
  const names = { new: 'New', learning: 'Learning', known: 'Known' };
  return (
    <div className="card-progress">
      <div className="card-labels">
        <span className={`label ${status.knowledge}`}>{names[status.knowledge]}</span>
        {status.tricky && <span className="label tricky">Tricky</span>}
      </div>
      {record !== undefined && (
        <p className="card-record">
          {record.right} of {status.answers} right
        </p>
      )}
    </div>
  );
}
