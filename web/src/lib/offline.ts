// Saves every card picture of the chosen list on the device, so
// lessons work without a connection. Pictures of other formats' cards
// are deleted, but those of the format's other lists stay, so switching
// lists offline still shows them.
// The service worker (set up in vite.config.ts) serves pictures from
// this same cache.

import { type Card, loadCards } from './cards';
import { listFile, listsOf, loadFormats } from './formats';

/** Must match the cacheName for card pictures in vite.config.ts */
export const PICTURE_CACHE = 'card-pictures';

/** Every picture the app can show for these cards, each listed once */
export function pictureUrls(cards: readonly Card[]): string[] {
  const urls = cards.flatMap((card) => [...card.images, card.art]);
  return [...new Set(urls)];
}

/**
 * The cards of all of a format's lists. Fails if a list can't be loaded
 * (e.g. offline, for a list never opened), so nothing is deleted then.
 */
export async function formatCards(format: string): Promise<Card[]> {
  const kinds = listsOf(await loadFormats(), format);
  const files = await Promise.all(kinds.map((kind) => loadCards(listFile({ format, kind }))));
  return files.flatMap((file) => file.cards);
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
  /** Cards whose pictures stay too, asked for only before deleting */
  alsoKeep: () => Promise<readonly Card[]>,
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

  // Pictures of cards that left the format's lists, or of another format.
  // Large pictures stay for the cards kept: they are saved only for the
  // cards the player zoomed into, and would otherwise download again.
  if (done < wanted.length) return;
  let keptCards: readonly Card[];
  try {
    keptCards = [...cards, ...(await alsoKeep())];
  } catch {
    // Unsure what to keep: delete nothing this time
    return;
  }
  const kept = new Set([
    ...pictureUrls(keptCards),
    ...keptCards.flatMap((card) => card.large_images ?? []),
  ]);
  for (const url of saved) {
    if (isStopped()) return;
    if (!kept.has(url)) {
      await cache.delete(url);
    }
  }
}
