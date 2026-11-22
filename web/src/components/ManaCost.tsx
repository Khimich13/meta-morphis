// A mana cost drawn as its symbols, the pictures Scryfall's server has
// for them: on the answers to a question about a card's cost, and in
// the line saying which one was picked.

import { symbols, symbolUrl } from '../lib/manaCost';
import './ManaCost.css';

/** The cost, "{1}{U}{U}", as a row of symbols sized to the text around it */
export default function ManaCost({ cost }: { cost: string }) {
  return (
    <span className="mana-cost">
      {symbols(cost).map((symbol, i) => (
        <img
          key={i}
          className="mana-symbol"
          src={symbolUrl(symbol)}
          // Read out as cards are written: "{1}", "{U}"
          alt={`{${symbol}}`}
          // Lets the saved copy of the picture be used, as for card pictures
          crossOrigin="anonymous"
        />
      ))}
    </span>
  );
}
