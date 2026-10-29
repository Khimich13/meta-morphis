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
   * card (see lib/zoom.ts). Empty when Scryfall lacks one, and missing in
   * files written before it was added.
   */
  large_images?: string[];
  /** The front side's artwork alone */
  art: string;
  /** Who painted it - shown wherever the artwork appears by itself */
  artist: string;
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
export async function loadCards(file: string): Promise<CardFile> {
  const response = await fetch(`data/${file}.json`);
  if (!response.ok) {
    throw new Error(`Could not load ${file}.json (HTTP ${response.status})`);
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
export function listAgeDays(listUpdated: string | undefined, now: Date = new Date()): number | null {
  if (listUpdated === undefined) return null;
  const fetched = Date.parse(listUpdated);
  if (Number.isNaN(fetched)) return null;
  return Math.floor((now.getTime() - fetched) / (24 * 60 * 60 * 1000));
}

/** A format's name for showing on screen: "pauper" → "Pauper" */
export function formatLabel(format: string): string {
  return format.charAt(0).toUpperCase() + format.slice(1);
}

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
