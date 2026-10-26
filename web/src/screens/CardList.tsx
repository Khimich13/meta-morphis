import { type ReactNode, type RefObject, useEffect, useRef, useState } from 'react';

import CardPicture, { LargeCard } from '../components/CardPicture';
import LargeView from '../components/LargeView';
import StandingLabel from '../components/StandingLabel';
import { type Card, formatLabel } from '../lib/cards';
import { LIST_LABELS, type Selection } from '../lib/formats';
import { useLargeView } from '../lib/largeView';
import type { Progress } from '../lib/progress';
import { type Direction, step } from '../lib/swipe';

interface CardListProps {
  selection: Selection;
  cards: Card[];
  progress: Progress;
  onBack: () => void;
}

/**
 * How many cards either side of the one in view hold their picture in the
 * large view. A row holding all its cards' full-size pictures ran short
 * of graphics memory while scrolling fast on a phone, and the browser
 * dropped and redrew the cards, which showed as flicker. While skimming
 * fast, the slots further away show a card shape until the cards come near.
 */
const NEARBY = 2;

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

  // One large view for the whole list: a sideways row of every card,
  // which the browser scrolls with the finger and settles on one card
  const large = useLargeView();
  const [index, setIndex] = useState(0);
  const row = useRef<HTMLDivElement>(null);

  function open(position: number) {
    setIndex(position);
    large.open();
  }

  // The arrow keys and the buttons for a mouse: scroll to the neighbor
  function move(direction: Direction) {
    const element = row.current;
    const target = step(index, direction, cards.length);
    if (element === null || target === index) return;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    element.scrollTo({
      left: target * element.clientWidth,
      behavior: reduceMotion ? 'auto' : 'smooth',
    });
  }


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
            {/* How the card is doing, above it */}
            <div className="card-progress">
              <StandingLabel record={progress.cards[card.oracle_id]} />
            </div>
            <CardPicture
              card={card}
              lazy
              showingBack={backs.has(card.oracle_id)}
              onFlip={() => flip(card)}
              onEnlarge={() => open(position)}
            />
          </li>
        ))}
      </ul>
      {large.isOpen && (
        <LargeView
          onClose={large.close}
          onMove={move}
          hasPrevious={index > 0}
          hasNext={index < cards.length - 1}
        >
          <p className="position" aria-live="polite">
            {index + 1} / {cards.length}
          </p>
          <CardRow
            rowRef={row}
            startAt={index}
            onSettle={setIndex}
            count={cards.length}
          >
            {cards.map((card, position) => (
              <div className="card-slide" key={card.oracle_id}>
                {/* Only the cards near the one in view hold a picture; the
                    others show a card shape of the same size */}
                {Math.abs(position - index) <= NEARBY ? (
                  <LargeCard
                    card={card}
                    showingBack={backs.has(card.oracle_id)}
                    onFlip={() => flip(card)}
                  />
                ) : (
                  <div className="card-placeholder" />
                )}
              </div>
            ))}
          </CardRow>
        </LargeView>
      )}
    </main>
  );
}

/**
 * The sideways row of cards in the large view. The browser scrolls it with
 * the finger, a trackpad or the code above, and scroll snapping (see
 * components/LargeView.css) brings it to rest exactly on one card;
 * onSettle reports which. At either end, the phone's own edge effect shows
 * there is no more.
 */
function CardRow({
  rowRef,
  startAt,
  onSettle,
  count,
  children,
}: {
  rowRef: RefObject<HTMLDivElement | null>;
  startAt: number;
  onSettle: (position: number) => void;
  count: number;
  children: ReactNode;
}) {
  // Runs once, when the large view opens: start at the tapped card
  useEffect(() => {
    const element = rowRef.current;
    if (element === null) return;
    // The dialog must be open to have a size to scroll by; the large view
    // opens it now if it hasn't yet
    const dialog = element.closest('dialog');
    if (dialog !== null && !dialog.open) dialog.showModal();
    element.scrollLeft = startAt * element.clientWidth;
    // Only the starting position: later changes come from scrolling
  }, []);

  return (
    <div
      className="card-row"
      ref={rowRef}
      onScroll={(event) => {
        const element = event.currentTarget;
        const position = Math.round(element.scrollLeft / element.clientWidth);
        onSettle(Math.min(Math.max(position, 0), count - 1));
      }}
    >
      {children}
    </div>
  );
}

