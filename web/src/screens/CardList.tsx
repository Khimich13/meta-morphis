import { type Card, formatLabel } from '../lib/cards';
import { type CardProgress, cardStatus, type Progress } from '../lib/progress';

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
            {/* Card pictures are shown as they are: never stretched, covered or dimmed */}
            {/* crossOrigin lets the saved copy of the picture be used */}
            <img
              src={card.images[0]}
              alt={card.name}
              loading="lazy"
              crossOrigin="anonymous"
            />
            <CardRecord record={progress.cards[card.oracle_id]} />
          </li>
        ))}
      </ul>
    </main>
  );
}

/** A card's labels and record, e.g. "Learning · Tricky · 3 of 6 right" */
function CardRecord({ record }: { record: CardProgress | undefined }) {
  const status = cardStatus(record);
  const names = { new: 'New', learning: 'Learning', known: 'Known' };
  return (
    <span className="card-progress">
      <span className={`label ${status.knowledge}`}>{names[status.knowledge]}</span>
      {status.tricky && <span className="label tricky">Tricky</span>}
      {record !== undefined && (
        <span>
          {record.right} of {status.answers} right
        </span>
      )}
    </span>
  );
}
