// Saves every card picture of the chosen list on the device, and the
// mana symbols its questions show, so lessons work without a
// connection. Pictures of other formats' cards are deleted, but those
// of the format's other lists stay, so switching lists offline still
// shows them.
// The service worker (set up in vite.config.ts) serves pictures from
// this same cache.

import { type ArtFrom, type Card, loadCards } from './cards';
import { type FormatsFile, listFile, listsOf, loadFormats } from './formats';
import { nearCosts, symbols, symbolUrl } from './manaCost';
import { OPTION_COUNT } from './questionKinds';

/** Must match the cacheName for card pictures in vite.config.ts */
export const PICTURE_CACHE = 'card-pictures';

/**
 * Every picture the app can show for these cards, each listed once: the
 * mana symbols of every answer a question about a card's cost can offer
 * too
 */
export function pictureUrls(cards: readonly Card[]): string[] {
  const urls = cards.flatMap((card) => [
    ...card.images,
    ...artworkUrls(card),
    ...(card.back ? artworkUrls(card.back) : []),
    ...(card.cost ? symbolUrls(card.cost.mana_cost) : []),
  ]);
  return [...new Set(urls)];
}

/** The symbols of a cost and of every wrong cost near it (see costOptions in questionKinds.ts) */
function symbolUrls(cost: string): string[] {
  const costs = [cost, ...nearCosts(cost, OPTION_COUNT - 1).flat()];
  return costs.flatMap(symbols).map(symbolUrl);
}

/** A side's artwork, and the picture the app cuts it from, if any */
function artworkUrls(side: { art: string; art_from?: ArtFrom | null }): string[] {
  return side.art_from ? [side.art, side.art_from.picture] : [side.art];
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
 * Every format's cards, all its lists together, by format: where a
 * lesson's wrong answers come from beyond the list being learned (see
 * makeQuestion in quiz.ts). Only names and types are needed there, so
 * no pictures are saved for them. A format whose lists can't be loaded
 * (e.g. offline, for one never opened) is left out.
 */
export async function cardsByFormat(formats: FormatsFile): Promise<Record<string, Card[]>> {
  const loaded = await Promise.all(
    formats.formats.map(async (format) => {
      try {
        const files = await Promise.all(
          listsOf(formats, format).map((kind) => loadCards(listFile({ format, kind }))),
        );
        return [[format, files.flatMap((file) => file.cards)]];
      } catch {
        return [];
      }
    }),
  );
  return Object.fromEntries(loaded.flat());
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
  // Pictures the server no longer has: they will never download, so they
  // neither count nor hold up deleting the old ones. Asked for again the
  // next time the app opens, in case they come back.
  let gone = 0;
  onProgress(done, wanted.length);

  // One at a time, to go easy on the picture server and the connection
  for (const url of wanted) {
    if (isStopped()) return;
    if (saved.has(url)) continue;
    try {
      const response = await fetch(url);
      if (response.ok) {
        await cache.put(url, response);
        done += 1;
      } else if (response.status === 404 || response.status === 410) {
        gone += 1;
      } else {
        // A passing server error: try again the next time the app opens
        continue;
      }
      onProgress(done, wanted.length - gone);
    } catch {
      // No connection, or the browser refused to store it: try again
      // the next time the app opens
    }
  }

  // Pictures of cards that left the format's lists, or of another format.
  // Large pictures stay for the cards kept: they are saved only for the
  // cards the player zoomed into, and would otherwise download again.
  if (done < wanted.length - gone) return;
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
