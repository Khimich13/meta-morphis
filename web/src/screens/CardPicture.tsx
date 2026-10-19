import { useState } from 'react';

import type { Card } from '../lib/cards';
import './CardPicture.css';

interface CardPictureProps {
  card: Card;
  /** Load the picture only when it scrolls into view (long lists) */
  lazy?: boolean;
}

/**
 * A card's full picture. A double-faced card gets a round button over its
 * artwork that turns it over to the back and back again.
 *
 * Card pictures are shown as they are: never stretched or dimmed. The
 * button sits over the artwork, never over the artist name or the
 * copyright at the bottom of the card, which Scryfall asks to keep visible.
 */
export default function CardPicture({ card, lazy = false }: CardPictureProps) {
  const [showingBack, setShowingBack] = useState(false);
  const [front, back] = card.images;

  return (
    <div className="card-picture">
      <div className={showingBack ? 'card-sides flipped' : 'card-sides'}>
        {/* crossOrigin lets the saved copy of the picture be used */}
        <img
          className="card-side"
          src={front}
          alt={card.name}
          loading={lazy ? 'lazy' : undefined}
          crossOrigin="anonymous"
          aria-hidden={showingBack}
        />
        {back !== undefined && (
          <img
            className="card-side card-back"
            src={back}
            alt={`${card.name}, back`}
            loading={lazy ? 'lazy' : undefined}
            crossOrigin="anonymous"
            aria-hidden={!showingBack}
          />
        )}
      </div>
      {back !== undefined && (
        <button
          className="flip"
          aria-label={showingBack ? 'Flip to see the front' : 'Flip to see the back'}
          onClick={(event) => {
            // Only flips: a tap on the card itself may do something else later
            event.stopPropagation();
            setShowingBack(!showingBack);
          }}
        >
          ↻
        </button>
      )}
    </div>
  );
}
