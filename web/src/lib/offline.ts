// Saves every card picture on the device, so lessons work without a
// connection. The service worker (set up in vite.config.ts) serves
// pictures from this same cache.

import type { Card } from './cards';

/** Must match the cacheName for card pictures in vite.config.ts */
export const PICTURE_CACHE = 'card-pictures';

/** Every picture the app can show for these cards, each listed once */
export function pictureUrls(cards: readonly Card[]): string[] {
  const urls = cards.flatMap((card) => [...card.images, card.art]);
  return [...new Set(urls)];
}

/**
 * Downloads the pictures that aren't saved yet and deletes saved ones
 * that are no longer needed. Calls onProgress with how many are saved
 * so far and how many there are in total.
 */
export async function savePictures(
  cards: readonly Card[],
  onProgress: (saved: number, total: number) => void,
): Promise<void> {
  // Very old browsers have no cache storage: the app then works online only
  if (!('caches' in window)) return;

  const wanted = pictureUrls(cards);
  const cache = await caches.open(PICTURE_CACHE);
  const saved = new Set((await cache.keys()).map((request) => request.url));

  // Pictures of cards that left the list
  for (const url of saved) {
    if (!wanted.includes(url)) {
      await cache.delete(url);
    }
  }

  let done = wanted.filter((url) => saved.has(url)).length;
  onProgress(done, wanted.length);

  // One at a time, to go easy on the picture server and the connection
  for (const url of wanted) {
    if (saved.has(url)) continue;
    try {
      await cache.add(url);
      done += 1;
      onProgress(done, wanted.length);
    } catch {
      // No connection or the picture is gone: skip it and try again
      // the next time the app opens
    }
  }
}
