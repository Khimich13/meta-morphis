import { type Card, formatLabel } from '../lib/cards';
import { type CardProgress, cardStatus, type Progress } from '../lib/progress';
import CardPicture from './CardPicture';

interface CardListProps {
  format: string;
  cards: Card[];
  progress: Progress;
  onBack: () => void;
}

export default function CardList({ format, cards, progress, onBack }: CardListProps) {
  return (
    <main className="card-list">
      <header className="card-list-bar">
        <button onClick={onBack}>← Back</button>
        <h1>Most played in {formatLabel(format)}</h1>
      </header>
      <ul className="card-grid">
        {cards.map((card) => (
          <li key={card.oracle_id}>
            <span>{card.name}</span>
            <CardPicture card={card} lazy />
            <CardRecord record={progress.cards[card.oracle_id]} />
          </li>
        ))}
      </ul>
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
