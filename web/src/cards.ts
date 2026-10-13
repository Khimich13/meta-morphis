// The shape of web/public/data/<format>.json.
// Mirrors ExportCard and ExportFile in meta_morphis/export.py -
// change the two together.

export interface Card {
  oracle_id: string;
  name: string;
  /** One picture per physical side: two for a double-faced card */
  images: string[];
}

export interface CardFile {
  format: string;
  cards: Card[];
}

export async function loadCards(format: string): Promise<Card[]> {
  const response = await fetch(`data/${format}.json`);
  if (!response.ok) {
    throw new Error(`Could not load ${format}.json (HTTP ${response.status})`);
  }
  const file: CardFile = await response.json();
  return file.cards;
}
