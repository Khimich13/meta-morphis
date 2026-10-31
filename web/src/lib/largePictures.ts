// Sharper pictures for zooming into a card in the large view (the zoom
// itself comes from the react-zoom-pan-pinch library, see LargeCard in
// components/CardPicture.tsx).

import { useEffect, useState } from 'react';

/**
 * The card's large pictures, once the player has zoomed in and they have
 * downloaded; null until then, while the normal ones show. They download
 * and are made ready to draw in the background, so swapping them in shows
 * no gap. Offline, or without large pictures, the normal ones stay.
 */
export function useLargePictures(
  large: string[] | undefined,
  zoomedIn: boolean,
): string[] | null {
  const [ready, setReady] = useState<string[] | null>(null);
  useEffect(() => {
    if (!zoomedIn || ready !== null || large === undefined || large.length === 0) return;
    let stopped = false;
    Promise.all(
      large.map((url) => {
        const picture = new Image();
        // The same way the card's <img> asks, so it finds this download
        picture.crossOrigin = 'anonymous';
        picture.src = url;
        return picture.decode();
      }),
    )
      .then(() => {
        if (!stopped) setReady(large);
      })
      .catch(() => {
        // No connection, or the picture is gone: the normal ones stay
      });
    return () => {
      stopped = true;
    };
  }, [zoomedIn, large, ready]);
  return ready;
}
