import { useState } from 'react';

import { type CustomList, removeCard } from '../lib/customLists';
import './EditList.css';

interface EditListProps {
  list: CustomList;
  /** Saves the changed list; false when the device couldn't */
  onSave: (list: CustomList) => boolean;
  onDelete: () => void;
  onBack: () => void;
}

/** Renaming one of the player's own lists, taking cards out, or deleting it */
export default function EditList({ list, onSave, onDelete, onBack }: EditListProps) {
  // As typed: the list keeps its last name that wasn't blank
  const [name, setName] = useState(list.name);
  const [saveFailed, setSaveFailed] = useState(false);
  const [deleting, setDeleting] = useState(false);

  function save(changed: CustomList) {
    setSaveFailed(!onSave(changed));
  }

  function rename(typed: string) {
    setName(typed);
    if (typed.trim() !== '') save({ ...list, name: typed.trim() });
  }

  const count = list.cards.length;

  return (
    <main className="form-screen edit-list">
      <header>
        <button className="link" onClick={onBack}>
          ← Back
        </button>
        <h1>Edit list</h1>
      </header>

      <label>
        Name
        <input value={name} onChange={(event) => rename(event.target.value)} />
      </label>

      {saveFailed && (
        <p role="status">
          <strong>Couldn't save the change:</strong> this device's storage for the app is full.
        </p>
      )}

      <section>
        <h2>
          {count} {count === 1 ? 'card' : 'cards'}
        </h2>
        <ul>
          {list.cards.map((card) => (
            <li key={card.oracle_id}>
              <span>{card.name}</span>
              <button
                aria-label={`Remove ${card.name}`}
                onClick={() => save(removeCard(list, card.oracle_id))}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* Asked once more right here, rather than in a pop-up */}
      {deleting ? (
        <div className="delete-confirm" role="group" aria-label="Delete the list">
          <p>Delete {list.name}? What you learned about its cards is kept.</p>
          <button className="danger" onClick={onDelete}>
            Delete
          </button>
          <button onClick={() => setDeleting(false)}>Cancel</button>
        </div>
      ) : (
        <button className="danger-outline" onClick={() => setDeleting(true)}>
          Delete list
        </button>
      )}
    </main>
  );
}
