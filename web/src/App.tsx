import { useEffect, useState } from 'react';

import './App.css';
import { type Card, loadCards } from './lib/cards';
import { type CustomList } from './lib/customLists';
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
import { formatCards, savePictures } from './lib/offline';
import { localDay, recordAnswer, recordLesson } from './lib/progress';
import {
  loadCustomLists,
  loadFormat,
  loadList,
  loadOpenList,
  loadProgress,
  loadSoundsOn,
  saveCustomLists,
  saveFormat,
  saveList,
  saveOpenList,
  saveProgress,
  saveSoundsOn,
} from './lib/storage';
import { useAppUpdate } from './lib/update';
import AddCards from './screens/AddCards';
import CardList from './screens/CardList';
import EditList from './screens/EditList';
import Formats from './screens/Formats';
import Home from './screens/Home';
import Lesson from './screens/Lesson';

/** Which screen is showing */
type Screen = 'home' | 'lesson' | 'cards' | 'formats' | 'add' | 'edit';

export default function App() {
  // Read from the browser's storage once, when the app starts
  const [progress, setProgress] = useState(loadProgress);
  // The chosen format; null until the player has chosen one
  const [format, setFormat] = useState(() =>
    startFormat(loadFormat(), Object.keys(progress.cards).length > 0),
  );
  // The chosen list of that format: all, creatures, spells or lands
  const [kind, setKind] = useState<ListKind>(() => startKind(loadList()));
  // The player's own lists of cards, see lib/customLists.ts
  const [lists, setLists] = useState(loadCustomLists);
  // The id of the one open instead of the format's list, if any
  const [openId, setOpenId] = useState(loadOpenList);
  const openList = lists.find((list) => list.id === openId) ?? null;
  // The list the add screen adds to at first, null for a new one, and
  // the screen it goes back to
  const [addTarget, setAddTarget] = useState<string | null>(null);
  const [addFrom, setAddFrom] = useState<Screen>('formats');
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
  const [screen, setScreen] = useState<Screen>(
    format === null && openList === null ? 'formats' : 'home',
  );
  // Whether answers make a sound, see lib/sounds.ts
  const [soundsOn, setSoundsOn] = useState(loadSoundsOn);
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

  // Runs whenever the chosen format or list changes: load its cards. Not
  // while one of the player's own lists is open, which has its cards
  // with it.
  const listOpen = openList !== null;
  useEffect(() => {
    if (format === null || listOpen) return;
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
      })
      .catch(() => {
        if (!stale) setFailed(true);
      });
    // React runs this before the effect runs again for the next list
    return () => {
      stale = true;
    };
  }, [format, shownKind, listOpen]);

  // The cards being learned: the open list's of the player's own, or the
  // format list's
  const shownCards = openList?.cards ?? cards;

  // Once a list's cards are here, save their pictures for offline use,
  // keeping those of the format's other lists - or, for one of the
  // player's own lists, none else; a switch stops the saving for the old
  // list. lastLoaded is set along with the cards, so it names their
  // format.
  const keepFormat = listOpen ? null : lastLoaded?.format;
  useEffect(() => {
    if (shownCards === null || keepFormat === undefined) return;
    let stopped = false;
    setPictures({ saved: 0, total: 0 });
    savePictures(
      shownCards,
      () => (keepFormat === null ? Promise.resolve([]) : formatCards(keepFormat)),
      (saved, total) => setPictures({ saved, total }),
      () => stopped,
    ).catch(() => {
      // The browser refused to store them (some private windows do, or the
      // disk is full): the app still works online
    });
    return () => {
      stopped = true;
    };
  }, [shownCards, keepFormat]);

  // Switch to a newly published version of the app, but never mid-lesson
  useAppUpdate(screen !== 'lesson');

  // Runs after every change to the progress, so it is never lost
  useEffect(() => {
    saveProgress(progress);
  }, [progress]);

  const goHome = () => setScreen('home');

  function chooseFormat(chosen: string) {
    setFormat(chosen);
    openOwnList(null);
    setScreen('home');
  }

  /** Opens one of the player's own lists, or with null, the format's again */
  function openOwnList(id: string | null) {
    setOpenId(id);
    saveOpenList(id);
    if (id !== null) setScreen('home');
  }

  function addCards(target: string | null, from: Screen) {
    setAddTarget(target);
    setAddFrom(from);
    setScreen('add');
  }

  /**
   * Deletes the open list of the player's own, and goes back to the
   * format's list - or to choosing one, if none was ever chosen
   */
  function deleteOpenList() {
    if (openList === null) return;
    const after = lists.filter((each) => each.id !== openList.id);
    // Saving less never runs out of room; storage switched off forgets it anyway
    saveCustomLists(after);
    setLists(after);
    openOwnList(null);
    setScreen(format === null ? 'formats' : 'home');
  }

  /** Saves a new or changed list of the player's own; false if it couldn't */
  function saveOwnList(list: CustomList): boolean {
    const had = lists.some((each) => each.id === list.id);
    const after = had ? lists.map((each) => (each.id === list.id ? list : each)) : [...lists, list];
    if (!saveCustomLists(after)) return false;
    setLists(after);
    return true;
  }

  function choose(selection: Selection) {
    setFormat(selection.format);
    setKind(selection.kind);
  }

  if (screen === 'edit' && openList !== null) {
    return (
      <EditList
        // A fresh screen for each list, so it starts from that list's name
        key={openList.id}
        list={openList}
        onSave={saveOwnList}
        onDelete={deleteOpenList}
        onBack={goHome}
      />
    );
  }

  if (screen === 'add') {
    return (
      <AddCards
        lists={lists}
        target={addTarget}
        onSave={saveOwnList}
        onOpen={openOwnList}
        onBack={() => setScreen(addFrom)}
      />
    );
  }

  if ((format === null && openList === null) || screen === 'formats') {
    return (
      <Formats
        formats={formats === null ? null : formats.formats}
        failed={formatsFailed}
        current={openList === null ? format : null}
        onChoose={chooseFormat}
        lists={lists}
        currentList={openList?.id ?? null}
        onChooseList={openOwnList}
        onAddCards={() => addCards(null, 'formats')}
        onBack={format === null && openList === null ? null : goHome}
      />
    );
  }

  if (shownCards !== null && screen === 'lesson') {
    return (
      <Lesson
        cards={shownCards}
        progress={progress}
        onAnswer={(card, correct) =>
          setProgress((before) => recordAnswer(before, card.oracle_id, correct, localDay()))
        }
        onLessonFinished={() => setProgress((before) => recordLesson(before, localDay()))}
        onDone={goHome}
        soundsOn={soundsOn}
      />
    );
  }

  if (shownCards !== null && screen === 'cards') {
    return (
      <CardList
        selection={{ format: format ?? '', kind: shownKind }}
        listName={openList?.name ?? null}
        cards={shownCards}
        progress={progress}
        onBack={goHome}
      />
    );
  }

  return (
    <Home
      listUpdated={listUpdated}
      selection={{ format: format ?? '', kind: shownKind }}
      listName={openList?.name ?? null}
      onAddCards={() => addCards(openList?.id ?? null, 'home')}
      onEditList={() => setScreen('edit')}
      offered={offered}
      onChooseKind={setKind}
      cards={shownCards}
      failed={!listOpen && failed}
      fallback={
        lastLoaded !== null &&
        format !== null &&
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
      soundsOn={soundsOn}
      onToggleSounds={() => {
        setSoundsOn(!soundsOn);
        saveSoundsOn(!soundsOn);
      }}
    />
  );
}
