// The player's own lists of cards, made by entering card names: one card,
// or a whole decklist pasted in. Names are found among every card, in the
// files data/cards/ holds - see export_every_card in meta_morphis/export.py.
// No React and no browser storage in here, so it can be tested alone;
// storage.ts keeps the lists.

import { type Card, loadDataFile } from './cards';

export interface CustomList {
  id: string;
  name: string;
  /**
   * The cards' full data, as the card files had it when they were added
   * or last refreshed, so the list opens offline and keeps cards that
   * leave every format's most played lists
   */
  cards: Card[];
}

/** The name a new list gets when the player leaves it empty */
export const DEFAULT_LIST_NAME = 'My list';

/**
 * Section headings of decklists exported by MTG Arena, MTGO, Moxfield and
 * the like, which are not cards. Compared as nameKey gives them.
 */
const HEADINGS = new Set([
  'deck',
  'main',
  'maindeck',
  'main deck',
  'sideboard',
  'commander',
  'companion',
  'about',
]);

/**
 * The card names in what the player entered, each once, in the order
 * given. One name a line; a decklist's counts ("4 ", "4x "), set codes
 * and collector numbers ("(MH2) 123") and section headings are left out.
 */
export function cardNamesFrom(text: string): string[] {
  const names = new Map<string, string>();
  for (const line of text.split('\n')) {
    let name = line.trim();
    const counted = /^\d+x?\s+/i.test(name);
    name = name.replace(/^\d+x?\s+/i, '');
    // From the set code to the end of the line: "(MH2) 123 *F*"
    name = name.replace(/\s+\([a-z0-9]{2,6}\)(\s.*)?$/i, '').trim();
    if (name === '' || name.endsWith(':')) continue;
    if (!counted && HEADINGS.has(nameKey(name))) continue;
    if (!names.has(nameKey(name))) names.set(nameKey(name), name);
  }
  return [...names.values()];
}

/**
 * A name as it is compared: without case, accents, curly apostrophes
 * or extra spaces, and with any slash between a split card's halves
 * written " // " - so "lorien revealed" finds Lórien Revealed and
 * "Wear/Tear" finds Wear // Tear
 */
export function nameKey(name: string): string {
  return name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[‘’]/g, "'")
    .replace(/\s*\/+\s*/g, ' // ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

/**
 * The cards by every name they can be entered by: the full name, and
 * each half of a split, double-faced or adventure card. A full name wins
 * over another card's half of the same name.
 */
export function cardsByName(cards: readonly Card[]): Map<string, Card> {
  const byName = new Map<string, Card>();
  for (const card of cards) byName.set(nameKey(card.name), card);
  for (const card of cards) {
    const halves = card.name.split(' // ');
    if (card.spell) halves.push(card.spell.name);
    for (const half of halves) {
      if (!byName.has(nameKey(half))) byName.set(nameKey(half), card);
    }
  }
  return byName;
}

/** What adding names to a list did, by the names as the player entered them */
export interface Added {
  list: CustomList;
  added: string[];
  /** Names of cards the list had already */
  already: string[];
  /** Names that are no card the app has: a typo, a joke card, a basic land */
  unknown: string[];
}

/**
 * The list with the named cards added at its end. The cards it had that
 * are in `known` too are refreshed from it, so they get any newer data
 * the card files have.
 */
export function addCards(
  list: CustomList,
  names: readonly string[],
  known: ReadonlyMap<string, Card>,
): Added {
  const byId = new Map<string, Card>();
  for (const card of known.values()) byId.set(card.oracle_id, card);
  const cards = list.cards.map((card) => byId.get(card.oracle_id) ?? card);
  const result: Added = { list: { ...list, cards }, added: [], already: [], unknown: [] };
  for (const name of names) {
    const card = known.get(nameKey(name));
    if (card === undefined) {
      result.unknown.push(name);
    } else if (cards.some((had) => had.oracle_id === card.oracle_id)) {
      result.already.push(name);
    } else {
      cards.push(card);
      result.added.push(name);
    }
  }
  return result;
}

/** The list without the card; the card's progress stays, see progress.ts */
export function removeCard(list: CustomList, oracleId: string): CustomList {
  return { ...list, cards: list.cards.filter((card) => card.oracle_id !== oracleId) };
}

/** A new, empty list; an empty or blank name becomes DEFAULT_LIST_NAME */
export function newList(name: string): CustomList {
  // Not crypto.randomUUID: it exists only on https pages, and the app is
  // also opened over plain http on the local network to test on a phone
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  return { id, name: name.trim() || DEFAULT_LIST_NAME, cards: [] };
}

/**
 * Whether a value read back from storage is a list, as far as the app
 * relies on it. Its cards are trusted to be as the card files had them.
 */
export function isCustomList(value: unknown): value is CustomList {
  if (typeof value !== 'object' || value === null) return false;
  const list = value as Record<string, unknown>;
  return typeof list.id === 'string' && typeof list.name === 'string' && Array.isArray(list.cards);
}

/**
 * The shape of data/cards/index.json: the names of the cards in each of
 * data/cards/<key>.json, by key - the first two characters of the cards'
 * oracle ids
 */
export type CardIndexFile = Record<string, string[]>;

/** The shape of data/cards/<key>.json */
export interface CardsFile {
  cards: Card[];
}

/**
 * The file each card is in, by every name it can be entered by, as
 * cardsByName finds cards: a full name wins over another card's half
 */
export function indexByName(index: CardIndexFile): Map<string, string> {
  const byName = new Map<string, string>();
  for (const [key, names] of Object.entries(index)) {
    for (const name of names) byName.set(nameKey(name), key);
  }
  for (const [key, names] of Object.entries(index)) {
    for (const name of names) {
      for (const half of name.split(' // ')) {
        if (!byName.has(nameKey(half))) byName.set(nameKey(half), key);
      }
    }
  }
  return byName;
}

/** Loads the index of every card. Fails offline if it was never loaded. */
export async function loadCardIndex(): Promise<Map<string, string>> {
  return indexByName(await loadDataFile<CardIndexFile>('cards/index'));
}

/**
 * The cards of the files the names are in, by every name they can be
 * entered by - what addCards looks the names up in. Loads each file
 * once. Fails if a file can't be loaded (e.g. offline, for one never
 * loaded before), so nothing is added half.
 */
export async function cardsNamed(
  names: readonly string[],
  index: ReadonlyMap<string, string>,
  load: (key: string) => Promise<CardsFile> = (key) => loadDataFile(`cards/${key}`),
): Promise<Map<string, Card>> {
  const keys = new Set<string>();
  for (const name of names) {
    const key = index.get(nameKey(name));
    if (key !== undefined) keys.add(key);
  }
  const files = await Promise.all([...keys].map(load));
  return cardsByName(files.flatMap((file) => file.cards));
}
