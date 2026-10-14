import { type Card, formatLabel } from './cards';
import type { CardProgress, Progress } from './progress';

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
            <span className="card-progress">
              {describe(progress.cards[card.oracle_id])}
            </span>
          </li>
        ))}
      </ul>
    </main>
  );
}

function describe(card: CardProgress | undefined): string {
  if (card === undefined) return 'new';
  return `${card.right} of ${card.right + card.wrong} right`;
}
