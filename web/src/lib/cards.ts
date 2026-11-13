// The shape of web/public/data/<format>.json.
// Mirrors ExportCard and ExportFile in meta_morphis/export.py -
// change the two together.

export interface Card {
  oracle_id: string;
  name: string;
  /** One picture per physical side: two for a double-faced card */
  images: string[];
  /**
   * The same pictures larger, loaded only when the player zooms into the
   * card (see lib/largePictures.ts). Empty when Scryfall lacks one, and missing in
   * files written before it was added.
   */
  large_images?: string[];
  /**
   * Where the artwork sits on the front picture, as shares of its width
   * and height: [left, top, width, height]. Null for a card without a
   * single art box (a split card), missing in files written before it
   * was added.
   */
  art_box?: [number, number, number, number] | null;
  /**
   * Where the title bar sits on the front picture, as shares of its width
   * and height: [left, top, width, height]. The app covers it to ask which
   * card it is from the full picture. Null when the name can't be covered
   * everywhere it shows, missing in files written before it was added.
   */
  name_box?: [number, number, number, number] | null;
  /**
   * Where else the name is printed on the front picture, in the text box:
   * one [left, top, width, height] for each line a name runs over. Empty
   * when it isn't, missing in files written before it was added.
   */
  name_text_boxes?: [number, number, number, number][];
  /** The front side's artwork alone */
  art: string;
  /** Who painted it - shown wherever the artwork appears by itself */
  artist: string;
  /**
   * For each picture in `images`: whether that side is printed sideways
   * (a split card, a battle's front), to be read turned a quarter
   * clockwise. Missing in files written before it was added.
   */
  horizontal?: boolean[];
}

export interface CardFile {
  format: string;
  /**
   * When the list of most played cards was last fetched from MTGGoldfish,
   * in UTC. Missing in files written before it was added.
   */
  list_updated?: string;
  cards: Card[];
}

/** Loads a card file, named as listFile in formats.ts names it */
export function loadCards(file: string): Promise<CardFile> {
  return loadDataFile(file);
}

/** Must match the cacheName for card files in vite.config.ts */
export const DATA_CACHE = 'card-data';

/**
 * Loads data/<name>.json and saves a copy on the device for offline use.
 * The service worker saves it too when it handles the download, but on
 * the very first visit the page loads its first files before the service
 * worker has started, and they would be missing offline.
 */
export async function loadDataFile<T>(name: string): Promise<T> {
  const path = `data/${name}.json`;
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Could not load ${name}.json (HTTP ${response.status})`);
  }
  if ('caches' in window) {
    // A copy of this same download, under the full address the app asks
    // for, so the service worker finds it
    const copy = response.clone();
    caches
      .open(DATA_CACHE)
      .then((cache) => cache.put(new URL(path, window.location.href), copy))
      .catch(() => {
        // The browser refused to store it: the app still works online
      });
  }
  return response.json();
}

/**
 * A list older than this is shown with a warning. Keep in step with
 * EXPORT_STALE_AFTER in meta_morphis/config.py: from then on the daily
 * update stops publishing, so the list the app has gets no newer.
 */
export const LIST_OLD_AFTER_DAYS = 3;

/** Whole days since the list was fetched, or null if the file doesn't say */
export function listAgeDays(
  listUpdated: string | undefined,
  now: Date = new Date(),
): number | null {
  if (listUpdated === undefined) return null;
  const fetched = Date.parse(listUpdated);
  if (Number.isNaN(fetched)) return null;
  return Math.floor((now.getTime() - fetched) / (24 * 60 * 60 * 1000));
}

/** A format's name for showing on screen: "pauper" → "Pauper" */
export function formatLabel(format: string): string {
  return format.charAt(0).toUpperCase() + format.slice(1);
}

/** True when the side being looked at is printed sideways */
export function isHorizontal(card: Card, showingBack: boolean): boolean {
  return card.horizontal?.[showingBack ? 1 : 0] ?? false;
}

/**
 * Where the artwork is on a side printed sideways (split cards, Rooms),
 * in the picture as it is stored - upright, with the card's writing
 * running up the side: left, top, width, height, as shares of the
 * card's width and height, like art_box. Turned the right way up, a
 * quarter clockwise, its top left corner becomes the artwork's top right
 * one. Measured on Wear // Tear and Unholy Annex on 2026-11-05 and
 * 2026-11-07, whose art areas are within 2% of each other.
 */
export const SIDEWAYS_ART_BOX = [0.145, 0.05, 0.39, 0.85];

/**
 * The name of the side being looked at. A double-faced card's name is
 * its two face names joined by " // ", in the same order as its two
 * pictures. A split card has " // " in its name too, but both halves
 * are printed on its one side, so it keeps its full name.
 */
export function visibleName(card: Card, showingBack: boolean): string {
  const faces = card.name.split(' // ');
  if (card.images.length < 2 || faces.length !== 2) return card.name;
  return showingBack ? faces[1] : faces[0];
}
