// Saves every card picture of the chosen format on the device, so
// lessons work without a connection. Pictures of other formats' cards
// are deleted, which keeps only one format's pictures (about 5 MB).
// The service worker (set up in vite.config.ts) serves pictures from
// this same cache.

import type { Card } from './cards';

/** Must match the cacheName for card pictures in vite.config.ts */
export const PICTURE_CACHE = 'card-pictures';

/** Every picture the app can show for these cards, each listed once */
export function pictureUrls(cards: readonly Card[]): string[] {
  const urls = cards.flatMap((card) => [...card.images, card.art]);
  return [...new Set(urls)];
}

/** Must match the cacheName for card files in vite.config.ts */
export const DATA_CACHE = 'card-data';

/**
 * Saves a card file and the list of formats on the device. The
 * service worker saves them too when it handles their download, but on
 * the very first visit the page loads them before the service worker
 * has started, and they would be missing offline.
 */
export async function saveCardFile(file: string): Promise<void> {
  if (!('caches' in window)) return;
  const cache = await caches.open(DATA_CACHE);
  for (const path of ['data/formats.json', `data/${file}.json`]) {
    try {
      // The same full address the app asks for, so the service worker finds it
      await cache.add(new URL(path, window.location.href));
    } catch {
      // Offline: the copy saved earlier, if any, stays
    }
  }
}

/**
 * Downloads the pictures that aren't saved yet, then deletes saved ones
 * that are no longer needed - but only once every new one is saved, so a
 * download cut short (e.g. going offline after a format switch) never
 * leaves the device without the old pictures as well. Calls onProgress
 * with how many are saved so far and how many there are in total.
 */
export async function savePictures(
  cards: readonly Card[],
  onProgress: (saved: number, total: number) => void,
  /** Checked before each step: true stops the saving, e.g. after a format switch */
  isStopped: () => boolean = () => false,
): Promise<void> {
  // Very old browsers have no cache storage: the app then works online only
  if (!('caches' in window)) return;

  const wanted = pictureUrls(cards);
  const cache = await caches.open(PICTURE_CACHE);
  const saved = new Set((await cache.keys()).map((request) => request.url));

  let done = wanted.filter((url) => saved.has(url)).length;
  onProgress(done, wanted.length);

  // One at a time, to go easy on the picture server and the connection
  for (const url of wanted) {
    if (isStopped()) return;
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

  // Pictures of cards that left the list, or of another format. The large
  // pictures of cards still in the list stay: they are saved only for the
  // cards the player zoomed into, and would otherwise download again.
  if (done < wanted.length) return;
  const kept = new Set([...wanted, ...cards.flatMap((card) => card.large_images ?? [])]);
  for (const url of saved) {
    if (isStopped()) return;
    if (!kept.has(url)) {
      await cache.delete(url);
    }
  }
}
