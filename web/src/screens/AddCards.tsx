import { useEffect, useState } from 'react';

import { type Card } from '../lib/cards';
import {
  type Added,
  addCards,
  cardNamesFrom,
  cardsByName,
  type CustomList,
  DEFAULT_LIST_NAME,
  everyCard,
  newList,
} from '../lib/customLists';
import './AddCards.css';

interface AddCardsProps {
  /** The player's own lists, to add to one of them */
  lists: CustomList[];
  /** The list to add to at first; null for a new one */
  target: string | null;
  /** Saves the list, new or changed; false when the device couldn't */
  onSave: (list: CustomList) => boolean;
  onOpen: (id: string) => void;
  onBack: () => void;
}

/** The value of the "Add to" choice that makes a new list */
const NEW = '';

export default function AddCards({ lists, target, onSave, onOpen, onBack }: AddCardsProps) {
  // Every card the app has, by every name it can be entered by; null
  // while loading
  const [known, setKnown] = useState<Map<string, Card> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [into, setInto] = useState(target ?? NEW);
  const [name, setName] = useState('');
  const [text, setText] = useState('');
  const [result, setResult] = useState<Added | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);

  // Runs once: the cards of every format, to find the names in
  useEffect(() => {
    everyCard()
      .then((cards) => setKnown(cardsByName(cards)))
      .catch(() => setLoadFailed(true));
  }, []);

  const names = cardNamesFrom(text);

  function add() {
    if (known === null) return;
    const list = lists.find((each) => each.id === into) ?? newList(name);
    const added = addCards(list, names, known);
    setSaveFailed(false);
    setResult(added);
    // A new list with none of the cards is not made at all
    if (added.list.cards.length === 0) return;
    if (!onSave(added.list)) {
      setSaveFailed(true);
      return;
    }
    // Adding more goes into the same list
    setInto(added.list.id);
    setText('');
  }

  return (
    <main className="form-screen add-cards">
      <header>
        <button className="link" onClick={onBack}>
          ← Back
        </button>
        <h1>Add cards</h1>
        <p>One card a line, or paste a whole decklist.</p>
      </header>

      <label>
        Add to
        <select value={into} onChange={(event) => setInto(event.target.value)}>
          <option value={NEW}>New list</option>
          {lists.map((list) => (
            <option key={list.id} value={list.id}>
              {list.name}
            </option>
          ))}
        </select>
      </label>

      {into === NEW && (
        <label>
          Name
          <input
            value={name}
            placeholder={DEFAULT_LIST_NAME}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
      )}

      <label>
        Cards
        <textarea
          value={text}
          rows={8}
          placeholder={'4 Lightning Bolt\n4 Counterspell'}
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          onChange={(event) => setText(event.target.value)}
        />
      </label>

      {loadFailed ? (
        <p role="status">
          Couldn't load the cards to look the names up in. Check the connection and try again.
        </p>
      ) : (
        <button className="primary" disabled={known === null || names.length === 0} onClick={add}>
          {known === null ? 'Loading cards…' : 'Add'}
        </button>
      )}

      {result !== null && (
        <AddResult result={result} saveFailed={saveFailed} onOpen={() => onOpen(result.list.id)} />
      )}
    </main>
  );
}

function AddResult({
  result,
  saveFailed,
  onOpen,
}: {
  result: Added;
  saveFailed: boolean;
  onOpen: () => void;
}) {
  const { list, added, already, unknown } = result;
  const saved = !saveFailed && list.cards.length > 0;
  return (
    <section className="add-result" role="status">
      {saveFailed ? (
        <p>
          <strong>Couldn't save the list:</strong> this device's storage for the app is full.
        </p>
      ) : (
        <p>
          {added.length} added
          {already.length > 0 && ` · ${already.length} already there`}
          {saved && ` · ${list.name} has ${list.cards.length} cards`}
        </p>
      )}
      {unknown.length > 0 && (
        <>
          <p>Not among the app's cards yet:</p>
          <ul>
            {unknown.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </>
      )}
      {saved && (
        <button className="primary" onClick={onOpen}>
          Open {list.name}
        </button>
      )}
    </section>
  );
}
