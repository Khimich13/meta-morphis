import { formatLabel } from '../lib/cards';
import { type CustomList } from '../lib/customLists';
import './Formats.css';

interface FormatsProps {
  /** The formats that have card data; null while still loading */
  formats: string[] | null;
  /** The list of formats could not be loaded */
  failed: boolean;
  /** The format chosen now; null on the very first visit, or with a list of the player's open */
  current: string | null;
  onChoose: (format: string) => void;
  /** The player's own lists, and the one open now, if any */
  lists: CustomList[];
  currentList: string | null;
  onChooseList: (id: string) => void;
  onAddCards: () => void;
  /** Only when a format is already chosen: back without changing it */
  onBack: (() => void) | null;
}

export default function Formats({
  formats,
  failed,
  current,
  onChoose,
  lists,
  currentList,
  onChooseList,
  onAddCards,
  onBack,
}: FormatsProps) {
  return (
    <main className="formats">
      <header>
        {onBack && (
          <button className="link" onClick={onBack}>
            ← Back
          </button>
        )}
        <h1>Choose what to learn</h1>
        <p>The most played cards of the format you play, or a list of your own.</p>
      </header>

      <h2>Formats</h2>

      {failed ? (
        <p>Could not load the list of formats. Check the connection and reload.</p>
      ) : formats === null ? (
        <p>Loading…</p>
      ) : (
        <ul>
          {formats.map((format) => (
            <li key={format}>
              <button
                className={format === current ? 'primary' : ''}
                aria-current={format === current}
                onClick={() => onChoose(format)}
              >
                {formatLabel(format)}
              </button>
            </li>
          ))}
        </ul>
      )}

      <h2>Your lists</h2>
      <ul>
        {lists.map((list) => (
          <li key={list.id}>
            <button
              className={list.id === currentList ? 'primary' : ''}
              aria-current={list.id === currentList}
              onClick={() => onChooseList(list.id)}
            >
              {list.name} · {list.cards.length} {list.cards.length === 1 ? 'card' : 'cards'}
            </button>
          </li>
        ))}
        <li>
          <button className="link" onClick={onAddCards}>
            + Add cards
          </button>
        </li>
      </ul>
    </main>
  );
}
