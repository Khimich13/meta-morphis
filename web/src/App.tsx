import { useEffect, useState } from 'react';

import './App.css';
import { type Card, loadCards } from './lib/cards';
import {
  type FormatsFile,
  kindFor,
  listFile,
  listsOf,
  type ListKind,
  loadFormats,
  type Selection,
  startFormat,
  startKind,
} from './lib/formats';
import { saveCardFile, savePictures } from './lib/offline';
import { localDay, recordAnswer, recordLesson } from './lib/progress';
import {
  loadFormat,
  loadList,
  loadProgress,
  saveFormat,
  saveList,
  saveProgress,
} from './lib/storage';
import { useAppUpdate } from './lib/update';
import CardList from './screens/CardList';
import Formats from './screens/Formats';
import Home from './screens/Home';
import Lesson from './screens/Lesson';

/** Which screen is showing */
type Screen = 'home' | 'lesson' | 'cards' | 'formats';

export default function App() {
  // Read from the browser's storage once, when the app starts
  const [progress, setProgress] = useState(loadProgress);
  // The chosen format; null until the player has chosen one
  const [format, setFormat] = useState(() =>
    startFormat(loadFormat(), Object.keys(progress.cards).length > 0),
  );
  // The chosen list of that format: all, creatures, spells or lands
  const [kind, setKind] = useState<ListKind>(() => startKind(loadList()));
  // The last format and list whose cards loaded; the way back when a new
  // one fails
  const [lastLoaded, setLastLoaded] = useState<Selection | null>(() => {
    const saved = loadFormat();
    return saved === null ? null : { format: saved, kind: startKind(loadList()) };
  });
  // The formats and lists that have card data; null until loaded
  const [formats, setFormats] = useState<FormatsFile | null>(null);
  const [formatsFailed, setFormatsFailed] = useState(false);
  // The chosen format's cards; null until they have arrived
  const [cards, setCards] = useState<Card[] | null>(null);
  // When that format's list was last fetched, if the file says
  const [listUpdated, setListUpdated] = useState<string | undefined>(undefined);
  const [failed, setFailed] = useState(false);
  const [screen, setScreen] = useState<Screen>(format === null ? 'formats' : 'home');
  // How many card pictures are saved on the device, out of how many
  const [pictures, setPictures] = useState({ saved: 0, total: 0 });

  // Runs once: the formats to choose from
  useEffect(() => {
    loadFormats()
      .then(setFormats)
      .catch(() => setFormatsFailed(true));
  }, []);

  // The lists the chosen format offers, once known. A chosen kind of list
  // the format lacks (say, after switching format) means its overall list.
  const offered = formats !== null && format !== null ? listsOf(formats, format) : null;
  const shownKind = offered === null ? kind : kindFor(kind, offered);

  // Runs whenever the chosen format or list changes: load its cards
  useEffect(() => {
    if (format === null) return;
    const selection: Selection = { format, kind: shownKind };
    // A switch before the file arrives makes this load stale: its result
    // must not replace the newer list's cards
    let stale = false;
    setCards(null);
    setFailed(false);
    loadCards(listFile(selection))
      .then((file) => {
        if (stale) return;
        setCards(file.cards);
        setListUpdated(file.list_updated);
        // Remembered only once it has loaded, so the app never reopens
        // on a list it can't show
        saveFormat(format);
        saveList(shownKind);
        setLastLoaded(selection);
        saveCardFile(listFile(selection));
      })
      .catch(() => {
        if (!stale) setFailed(true);
      });
    // React runs this before the effect runs again for the next list
    return () => {
      stale = true;
    };
  }, [format, shownKind]);

  // Once a format's cards are here, save their pictures for offline use;
  // a format switch stops the saving for the old one
  useEffect(() => {
    if (cards === null) return;
    let stopped = false;
    setPictures({ saved: 0, total: 0 });
    savePictures(
      cards,
      (saved, total) => setPictures({ saved, total }),
      () => stopped,
    );
    return () => {
      stopped = true;
    };
  }, [cards]);

  // Switch to a newly published version of the app, but never mid-lesson
  useAppUpdate(screen !== 'lesson');

  // Runs after every change to the progress, so it is never lost
  useEffect(() => {
    saveProgress(progress);
  }, [progress]);

  const goHome = () => setScreen('home');

  function chooseFormat(chosen: string) {
    setFormat(chosen);
    setScreen('home');
  }

  function choose(selection: Selection) {
    setFormat(selection.format);
    setKind(selection.kind);
  }

  if (format === null || screen === 'formats') {
    return (
      <Formats
        formats={formats === null ? null : formats.formats}
        failed={formatsFailed}
        current={format}
        onChoose={chooseFormat}
        onBack={format === null ? null : goHome}
      />
    );
  }

  if (cards !== null && screen === 'lesson') {
    return (
      <Lesson
        cards={cards}
        progress={progress}
        onAnswer={(card, correct) =>
          setProgress((before) => recordAnswer(before, card.oracle_id, correct, localDay()))
        }
        onLessonFinished={() =>
          setProgress((before) => recordLesson(before, localDay()))
        }
        onDone={goHome}
      />
    );
  }

  if (cards !== null && screen === 'cards') {
    return (
      <CardList
        selection={{ format, kind: shownKind }}
        cards={cards}
        progress={progress}
        onBack={goHome}
      />
    );
  }

  return (
    <Home
      listUpdated={listUpdated}
      selection={{ format, kind: shownKind }}
      offered={offered}
      onChooseKind={setKind}
      cards={cards}
      failed={failed}
      fallback={
        lastLoaded !== null &&
        (lastLoaded.format !== format || lastLoaded.kind !== shownKind)
          ? lastLoaded
          : null
      }
      onChooseFallback={choose}
      progress={progress}
      pictures={pictures}
      onStartLesson={() => setScreen('lesson')}
      onSeeCards={() => setScreen('cards')}
      onChangeFormat={() => setScreen('formats')}
    />
  );
}
