import { type Card, formatLabel } from './cards';
import './Home.css';
import { localDay, type Progress, streak } from './progress';

interface HomeProps {
  format: string;
  /** null while the card list is still loading */
  cards: Card[] | null;
  /** The card list could not be loaded */
  failed: boolean;
  progress: Progress;
  /** How many card pictures are saved for offline use, out of how many */
  pictures: { saved: number; total: number };
  onStartLesson: () => void;
  onSeeCards: () => void;
}

export default function Home({
  format,
  cards,
  failed,
  progress,
  pictures,
  onStartLesson,
  onSeeCards,
}: HomeProps) {
  return (
    <main className="home">
      <header className="home-title">
        <h1>MetaMorphis</h1>
        <p>{formatLabel(format)}</p>
      </header>

      {failed ? (
        <p className="home-middle">
          Could not load the card list. Create it with{' '}
          <code>uv run python -m meta_morphis.export</code> and reload.
        </p>
      ) : cards === null ? (
        <p className="home-middle">Loading…</p>
      ) : (
        <>
          <Stats cards={cards} progress={progress} />
          <div className="home-actions">
            <button className="primary" onClick={onStartLesson}>
              Start lesson
            </button>
            <button className="link" onClick={onSeeCards}>
              See all cards
            </button>
            {pictures.total > 0 && (
              <p className="offline-status">
                {pictures.saved === pictures.total
                  ? 'Ready to use offline'
                  : `Saving pictures for offline use: ${pictures.saved} of ${pictures.total}`}
              </p>
            )}
          </div>
        </>
      )}

      <Notice />
    </main>
  );
}

function Stats({ cards, progress }: { cards: Card[]; progress: Progress }) {
  const days = streak(progress, localDay());
  // Only cards in today's list count: one that left the list keeps its
  // saved numbers but is no longer shown
  const seen = cards.filter((card) => card.oracle_id in progress.cards).length;

  return (
    <div className="home-middle">
      <div className="streak">
        <span aria-hidden="true">🔥</span>
        <strong>{days}</strong>
        <span>day streak</span>
      </div>
      <div className="seen">
        <div
          className="progress-bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={cards.length}
          aria-valuenow={seen}
          aria-label="Cards seen"
        >
          <div style={{ width: `${(seen / cards.length) * 100}%` }} />
        </div>
        <p>
          {seen} of {cards.length} cards seen
        </p>
      </div>
    </div>
  );
}

function Notice() {
  return (
    <footer className="notice">
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
