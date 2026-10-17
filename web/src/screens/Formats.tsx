import { formatLabel } from '../lib/cards';
import './Formats.css';

interface FormatsProps {
  /** The formats that have card data; null while still loading */
  formats: string[] | null;
  /** The list of formats could not be loaded */
  failed: boolean;
  /** The format chosen now, or null on the very first visit */
  current: string | null;
  onChoose: (format: string) => void;
  /** Only when a format is already chosen: back without changing it */
  onBack: (() => void) | null;
}

export default function Formats({ formats, failed, current, onChoose, onBack }: FormatsProps) {
  return (
    <main className="formats">
      <header>
        {onBack && (
          <button className="link" onClick={onBack}>
            ← Back
          </button>
        )}
        <h1>Choose a format</h1>
        <p>Learn the most played cards of the format you play.</p>
      </header>

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
    </main>
  );
}
