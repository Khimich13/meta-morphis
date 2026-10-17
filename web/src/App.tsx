import { useEffect, useState } from 'react';

import './App.css';
import { type Card, loadCards } from './lib/cards';
import { savePictures } from './lib/offline';
import { localDay, recordAnswer, recordLesson } from './lib/progress';
import { loadProgress, saveProgress } from './lib/storage';
import { useAppUpdate } from './lib/update';
import CardList from './screens/CardList';
import Home from './screens/Home';
import Lesson from './screens/Lesson';

const FORMAT = 'pauper';

/** Which screen is showing */
type Screen = 'home' | 'lesson' | 'cards';

export default function App() {
  // null until the card list has arrived
  const [cards, setCards] = useState<Card[] | null>(null);
  // When the list of most played cards was last fetched, if the file says
  const [listUpdated, setListUpdated] = useState<string | undefined>(undefined);
  const [failed, setFailed] = useState(false);
  const [screen, setScreen] = useState<Screen>('home');
  // Read from the browser's storage once, when the app starts
  const [progress, setProgress] = useState(loadProgress);
  // How many card pictures are saved on the device, out of how many
  const [pictures, setPictures] = useState({ saved: 0, total: 0 });

  // Runs once, after the page first appears
  useEffect(() => {
    loadCards(FORMAT)
      .then((file) => {
        setCards(file.cards);
        setListUpdated(file.list_updated);
      })
      .catch(() => setFailed(true));
  }, []);

  // Once the card list is here, save its pictures for offline use
  useEffect(() => {
    if (cards !== null) {
      savePictures(cards, (saved, total) => setPictures({ saved, total }));
    }
  }, [cards]);

  // Switch to a newly published version of the app, but never mid-lesson
  useAppUpdate(screen !== 'lesson');

  // Runs after every change to the progress, so it is never lost
  useEffect(() => {
    saveProgress(progress);
  }, [progress]);

  const goHome = () => setScreen('home');

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
    return <CardList format={FORMAT} cards={cards} progress={progress} onBack={goHome} />;
  }

  return (
    <Home
      listUpdated={listUpdated}
      format={FORMAT}
      cards={cards}
      failed={failed}
      progress={progress}
      pictures={pictures}
      onStartLesson={() => setScreen('lesson')}
      onSeeCards={() => setScreen('cards')}
    />
  );
}
