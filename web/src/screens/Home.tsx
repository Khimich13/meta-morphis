import { type Card, formatLabel, LIST_OLD_AFTER_DAYS, listAgeDays } from '../lib/cards';
import { dueCount, localDay, type Progress, streak } from '../lib/progress';
import './Home.css';

interface HomeProps {
  format: string;
  /** null while the card list is still loading */
  cards: Card[] | null;
  /** The card list could not be loaded */
  failed: boolean;
  /** A format that did load, to go back to after a failure */
  fallbackFormat: string | null;
  onChooseFormat: (format: string) => void;
  /** When the list of most played cards was last fetched, if known */
  listUpdated: string | undefined;
  progress: Progress;
  /** How many card pictures are saved for offline use, out of how many */
  pictures: { saved: number; total: number };
  onStartLesson: () => void;
  onSeeCards: () => void;
  onChangeFormat: () => void;
}

export default function Home({
  format,
  cards,
  failed,
  fallbackFormat,
  onChooseFormat,
  listUpdated,
  progress,
  pictures,
  onStartLesson,
  onSeeCards,
  onChangeFormat,
}: HomeProps) {
  return (
    <main className="home">
      <header className="home-title">
        <h1>MetaMorphis</h1>
        <p>
          {formatLabel(format)} ·{' '}
          <button className="link" onClick={onChangeFormat}>
            Change
          </button>
        </p>
      </header>

      <OldListBanner listUpdated={listUpdated} />

      {failed ? (
        <LoadFailed format={format} fallback={fallbackFormat} onChoose={onChooseFormat} />
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
  const today = localDay();
  const days = streak(progress, today);
  // Only cards in today's list count: one that left the list keeps its
  // saved numbers but is no longer shown
  const seen = cards.filter((card) => card.oracle_id in progress.cards).length;
  const due = dueCount(progress, cards.map((card) => card.oracle_id), today);

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
        <p className="due">
          {due === 0
            ? 'No cards to review today'
            : `${due} ${due === 1 ? 'card' : 'cards'} to review today`}
        </p>
      </div>
    </div>
  );
}

function LoadFailed({
  format,
  fallback,
  onChoose,
}: {
  format: string;
  fallback: string | null;
  onChoose: (format: string) => void;
}) {
  // The browser's own idea of the connection: false means surely offline
  const offline = !navigator.onLine;
  return (
    <div className="home-middle load-failed" role="status">
      {offline ? (
        <>
          <p>
            <strong>{formatLabel(format)} isn't on this device yet.</strong>
          </p>
          <p>Connect to the internet to download it.</p>
        </>
      ) : (
        <p>Couldn't load {formatLabel(format)}. Try again later.</p>
      )}
      {fallback !== null && (
        <button className="primary" onClick={() => onChoose(fallback)}>
          Back to {formatLabel(fallback)}
        </button>
      )}
    </div>
  );
}

/**
 * Shown when the list of most played cards hasn't been updated for a
 * while, which means fetching it has been failing
 */
function OldListBanner({ listUpdated }: { listUpdated: string | undefined }) {
  const days = listAgeDays(listUpdated);
  if (days === null || days <= LIST_OLD_AFTER_DAYS) return null;
  return (
    <p className="old-list" role="status">
      ⚠ The card list was last updated {days} days ago, so it may not match the
      current meta.
    </p>
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
