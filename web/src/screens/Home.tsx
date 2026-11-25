import { type Card, formatLabel, shortDay } from '../lib/cards';
import { LIST_LABELS, type ListKind, type Selection, selectionLabel } from '../lib/formats';
import { dueCount, localDay, masteredCount, type Progress, streak } from '../lib/progress';
import { OPTION_COUNT } from '../lib/questionKinds';
import './Home.css';

interface HomeProps {
  selection: Selection;
  /** The name of the player's own list that is open, if one is; then selection is not shown */
  listName: string | null;
  /** Only with one of the player's own lists open */
  onAddCards: () => void;
  onEditList: () => void;
  /** The lists the format offers; null while not known yet */
  offered: ListKind[] | null;
  onChooseKind: (kind: ListKind) => void;
  /** null while the card list is still loading */
  cards: Card[] | null;
  /** The card list could not be loaded */
  failed: boolean;
  /** A format and list that did load, to go back to after a failure */
  fallback: Selection | null;
  onChooseFallback: (selection: Selection) => void;
  /** The day of the newest decks the list was counted from, if known */
  decksTo: string | null;
  progress: Progress;
  /** How many card pictures are saved for offline use, out of how many */
  pictures: { saved: number; total: number };
  onStartLesson: () => void;
  onSeeCards: () => void;
  onChangeFormat: () => void;
  /** Whether answers make a sound, and how to switch that */
  soundsOn: boolean;
  onToggleSounds: () => void;
}

export default function Home({
  selection,
  listName,
  onAddCards,
  onEditList,
  offered,
  onChooseKind,
  cards,
  failed,
  fallback,
  onChooseFallback,
  decksTo,
  progress,
  pictures,
  onStartLesson,
  onSeeCards,
  soundsOn,
  onToggleSounds,
  onChangeFormat,
}: HomeProps) {
  return (
    <main className="home">
      <header className="home-title">
        <h1>MetaMorphis</h1>
        <p>
          {listName ?? formatLabel(selection.format)} ·{' '}
          {listName === null && <DecksTo day={decksTo} />}
          <button className="link" onClick={onChangeFormat}>
            Change
          </button>
        </p>
      </header>

      {listName === null && offered !== null && offered.length > 1 && (
        <ListChoice offered={offered} current={selection.kind} onChoose={onChooseKind} />
      )}

      {failed ? (
        <LoadFailed selection={selection} fallback={fallback} onChoose={onChooseFallback} />
      ) : cards === null ? (
        <p className="home-middle">Loading…</p>
      ) : (
        <>
          <Stats cards={cards} progress={progress} />
          <div className="home-actions">
            {/* A question needs as many cards as it has answers to choose from */}
            {cards.length < OPTION_COUNT ? (
              <p>Add at least {OPTION_COUNT} cards to start a lesson.</p>
            ) : (
              <button className="primary" onClick={onStartLesson}>
                Start lesson
              </button>
            )}
            <button className="link" onClick={onSeeCards}>
              See all cards
            </button>
            {listName !== null && (
              <>
                <button className="link" onClick={onAddCards}>
                  Add cards
                </button>
                <button className="link" onClick={onEditList}>
                  Edit list
                </button>
              </>
            )}
            <button className="link" aria-pressed={soundsOn} onClick={onToggleSounds}>
              {soundsOn ? '🔊 Sounds on' : '🔇 Sounds off'}
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
  const ids = cards.map((card) => card.oracle_id);
  const seen = cards.filter((card) => card.oracle_id in progress.cards).length;
  const mastered = masteredCount(progress, ids);
  const due = dueCount(progress, ids, today);
  // A list of the player's own can be emptied: then the bar stays empty
  const share = (count: number) => (cards.length === 0 ? 0 : (count / cards.length) * 100);

  return (
    <div className="home-middle">
      <div className="streak">
        <span aria-hidden="true">🔥</span>
        <strong>{days}</strong>
        <span>day streak</span>
      </div>
      <div className="seen">
        {/* Mastered cards in full green, the other seen ones in pale green */}
        <div
          className="progress-bar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={cards.length}
          aria-valuenow={mastered}
          aria-valuetext={`${mastered} of ${cards.length} cards mastered, ${seen} seen`}
          aria-label="Cards mastered"
        >
          <div style={{ width: `${share(mastered)}%` }} />
          <div className="seen-only" style={{ width: `${share(seen - mastered)}%` }} />
        </div>
        <p>
          {seen} of {cards.length} seen · <strong>{mastered} mastered</strong>
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

/** All · Creatures · Spells · Lands: which list of the format to learn */
function ListChoice({
  offered,
  current,
  onChoose,
}: {
  offered: ListKind[];
  current: ListKind;
  onChoose: (kind: ListKind) => void;
}) {
  return (
    <div className="list-choice" role="group" aria-label="Cards to learn">
      {offered.map((kind) => (
        <button
          key={kind}
          className={kind === current ? 'current' : ''}
          aria-pressed={kind === current}
          onClick={() => onChoose(kind)}
        >
          {LIST_LABELS[kind]}
        </button>
      ))}
    </div>
  );
}

function LoadFailed({
  selection,
  fallback,
  onChoose,
}: {
  selection: Selection;
  fallback: Selection | null;
  onChoose: (selection: Selection) => void;
}) {
  // The browser's own idea of the connection: false means surely offline
  const offline = !navigator.onLine;
  return (
    <div className="home-middle load-failed" role="status">
      {offline ? (
        <>
          <p>
            <strong>{selectionLabel(selection)} isn't on this device yet.</strong>
          </p>
          <p>Connect to the internet to download it.</p>
        </>
      ) : (
        <p>Couldn't load {selectionLabel(selection)}. Try again later.</p>
      )}
      {fallback !== null && (
        <button className="primary" onClick={() => onChoose(fallback)}>
          Back to {selectionLabel(fallback)}
        </button>
      )}
    </div>
  );
}

/**
 * How recent the list is: "decks to Nov 19 · ". It stops moving when the
 * decklists stop coming, so it also tells when the list has grown old.
 */
function DecksTo({ day }: { day: string | null }) {
  const shown = shortDay(day);
  if (shown === null) return null;
  return <>decks to {shown} · </>;
}

function Notice() {
  return (
    <footer className="notice">
      {/* Required wording of the Wizards of the Coast Fan Content Policy */}
      <p>
        MetaMorphis is unofficial Fan Content permitted under the Fan Content Policy. Not
        approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the
        Coast. ©Wizards of the Coast LLC.
      </p>
      <p>
        Card data and images come from <a href="https://scryfall.com">Scryfall</a>. The most played
        cards are counted from the decklists{' '}
        <a href="https://www.mtgo.com/decklists">Magic Online</a> publishes, and Commander's follow{' '}
        <a href="https://edhrec.com">EDHREC</a>'s rank of each card. This app is not affiliated with
        any of them.
      </p>
    </footer>
  );
}
