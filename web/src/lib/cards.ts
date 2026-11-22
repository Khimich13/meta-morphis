// The shape of web/public/data/<format>.json.
// Mirrors ExportCard and ExportFile in meta_morphis/export.py -
// change the two together.

/**
 * Where the app cuts a side's artwork from, when the artwork from
 * Scryfall catches text around it: the side's large picture, and the
 * artwork's place on it as [left, top, width, height] shares
 */
export interface ArtFrom {
  picture: string;
  box: [number, number, number, number];
}

/**
 * A double-faced card's back, for questions about its artwork, and a
 * transform card's about its full picture too
 */
export interface BackSide {
  /** The back side's artwork alone */
  art: string;
  /** Who painted it */
  artist: string;
  /** Where the artwork sits on the back's picture, like Card's art_box */
  art_box: [number, number, number, number] | null;
  /** As Card's art_from */
  art_from?: ArtFrom | null;
  /**
   * Where the name sits on the back's picture, like Card's name_box and
   * name_text_boxes. Null for every back but a transform card's, which
   * shows only its own name; missing in files written before it was
   * added.
   */
  name_box?: [number, number, number, number] | null;
  name_text_boxes?: [number, number, number, number][];
  /** The back's own type, as Card's type: Insectile Aberration's "creature" */
  type?: string;
}

/**
 * The second, smaller spell printed on an adventure or prepare card:
 * Petty Theft on Brazen Borrower. A question may ask about it instead of
 * the main part, by the full picture only - the artwork is the main
 * part's - with the main part's name left in sight.
 */
export interface SpellPart {
  name: string;
  /**
   * Where its name sits on the card's picture, like Card's name_box and
   * name_text_boxes. Null when it can't be covered everywhere it shows:
   * then the spell is never asked about.
   */
  name_box: [number, number, number, number] | null;
  name_text_boxes: [number, number, number, number][];
  /** Its own type, as Card's type: "instant" or "sorcery" */
  type?: string;
}

/**
 * One half of a split card printed sideways: Wear on Wear // Tear, or a
 * Room's door. A question asks about one half at a time, with the other
 * half's name left in sight.
 */
export interface SplitHalf {
  name: string;
  /**
   * Where its name sits on the card's picture as stored - upright, the
   * name running up the side - like Card's name_box. Null when it can't
   * be covered: then the half is asked about by its artwork only.
   */
  name_box: [number, number, number, number] | null;
  /** Its own type, as Card's type: "instant" on Wear, "Room" on a door */
  type?: string;
}

/** A card's mana cost, for the question about it */
export interface CostPart {
  /** As Scryfall writes it: "{1}{U}{U}" */
  mana_cost: string;
  /** Where it sits in the title bar on the front picture, like name_box */
  box: [number, number, number, number];
}

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
   * Where the name sits in the title bar on the front picture, as shares of
   * its width and height: [left, top, width, height]. The app covers it,
   * and name_text_boxes, to ask which card it is from the full picture.
   * Null when the name can't be covered everywhere it shows, missing in
   * files written before it was added.
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
   * Where the app cuts the front's artwork from instead of showing `art`,
   * which then catches text around it. Null for nearly every card,
   * missing in files written before it was added.
   */
  art_from?: ArtFrom | null;
  /**
   * For each picture in `images`: whether that side is printed sideways
   * (a split card, a battle's front), to be read turned a quarter
   * clockwise. Missing in files written before it was added.
   */
  horizontal?: boolean[];
  /**
   * A double-faced card's back side, which a question may show instead
   * of the front: by its artwork, or a transform card's by its full
   * picture too. Null for a card with one side, or
   * whose back lacks its artwork; missing in files written before it was
   * added.
   */
  back?: BackSide | null;
  /**
   * An adventure's or prepare card's spell. Then name_box and
   * name_text_boxes are the main part's alone. Null for every other
   * card; missing in files written before it was added.
   */
  spell?: SpellPart | null;
  /**
   * A split card's two halves, first half first, each asked about by
   * itself: by its half of `art` (see halfArt), or by the full picture
   * with its name covered. Null for every other card, which is asked
   * about whole; missing in files written before it was added.
   */
  halves?: [SplitHalf, SplitHalf] | null;
  /**
   * The one type the question about the full picture names it by:
   * "creature", "land", "planeswalker", "battle", "artifact",
   * "enchantment", "instant", "sorcery", "Room" or "card". The front's
   * on a double-faced card, the main part's on one with a spell. Missing
   * in files written before it was added.
   */
  type?: string;
  /**
   * The mana cost, which a question may cover on the full card to ask
   * what it costs: only on a card with one side and one cost, in a frame
   * whose title bar is measured. Null on every other card, missing in
   * files written before it was added.
   */
  cost?: CostPart | null;
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
 * The same for each half of a split card (see Card's halves): the first
 * half's artwork is the lower one, as stored. Measured on Wear // Tear,
 * whose two artworks have a gap between them, on 2026-11-16.
 */
export const SIDEWAYS_HALF_ART_BOXES = [
  [0.145, 0.5, 0.39, 0.4],
  [0.145, 0.05, 0.39, 0.4],
];

/** A side's artwork, as a question shows it by itself */
export interface ArtSide {
  art: string;
  artist: string;
  art_from?: ArtFrom | null;
}

const halfArts = new WeakMap<Card, ArtSide[]>();

/**
 * One half of a split card's artwork: Scryfall's crops both, side by
 * side as the card is read, the first half's on the left. Cut by the app
 * from that picture (see Card's art_from); the same object each time for
 * the same card and half, so the cut isn't made again on every render.
 */
export function halfArt(card: Card, half: number): ArtSide {
  let sides = halfArts.get(card);
  if (!sides) {
    sides = [0, 0.5].map((left): ArtSide => ({
      art: card.art,
      artist: card.artist,
      art_from: { picture: card.art, box: [left, 0, 0.5, 1] },
    }));
    halfArts.set(card, sides);
  }
  return sides[half];
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

/**
 * The name of the part a question asks about, for its answer button:
 * one side's of a double-faced card (see visibleName), and of a card with
 * a spell, the spell's or the main part's alone, and of a split card,
 * the half's (0 or 1). Any other card's whole name.
 */
export function partName(
  card: Card,
  back: boolean,
  spell: boolean,
  half: number | null = null,
): string {
  if (card.halves && half !== null) return card.halves[half].name;
  if (card.spell) return spell ? card.spell.name : card.name.split(' // ')[0];
  return visibleName(card, back);
}

/**
 * The type of the part a question asks about, as partName picks the
 * part, for the question about its full picture: "Name the creature".
 * "card" in files written before types were added.
 */
export function partType(
  card: Card,
  back: boolean,
  spell: boolean,
  half: number | null = null,
): string {
  if (card.halves && half !== null) return card.halves[half].type ?? 'card';
  if (card.spell && spell) return card.spell.type ?? 'card';
  if (back && card.back) return card.back.type ?? 'card';
  return card.type ?? 'card';
}
