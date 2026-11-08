// Turning a phone sideways. index.html covers the app with "Turn your
// phone upright" on a sideways phone, except while a screen allows it
// (the "landscape-ok" class): the card list and the large view, where a
// wide screen shows more cards, or a card printed sideways the right way
// up - also a lesson's answer card printed sideways, whose turn opens the
// large view. The other screens are built for an upright phone only.

import { useEffect, useState } from 'react';

/** True while the screen is wider than it is tall */
export function isLandscape(): boolean {
  return window.innerWidth > window.innerHeight;
}

// How many screens on show allow landscape: the card list and its large
// view both do, and closing the large view mustn't end it for the list
let allowing = 0;

/**
 * Lets the phone turn sideways while the calling screen is on show, and
 * `allowed` is true
 */
export function useLandscapeAllowed(allowed = true): void {
  useEffect(() => {
    if (!allowed) return;
    allowing += 1;
    document.documentElement.classList.add('landscape-ok');
    return () => {
      allowing -= 1;
      if (allowing === 0) document.documentElement.classList.remove('landscape-ok');
    };
  }, [allowed]);
}

/** Whether the screen is wider than tall, following the phone as it turns */
export function useLandscape(): boolean {
  const [landscape, setLandscape] = useState(isLandscape);
  useEffect(() => {
    const onResize = () => setLandscape(isLandscape());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  return landscape;
}
