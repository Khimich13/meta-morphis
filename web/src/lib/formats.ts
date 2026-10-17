// Which formats the app can teach, and which one it starts with.

/** The format a player who used the app before formats existed was using */
export const FIRST_FORMAT = 'pauper';

/** The formats that have card data, from data/formats.json */
export async function loadFormats(): Promise<string[]> {
  const response = await fetch('data/formats.json');
  if (!response.ok) {
    throw new Error(`Could not load formats.json (HTTP ${response.status})`);
  }
  const file: { formats: string[] } = await response.json();
  return file.formats;
}

/**
 * The format to open the app with: the saved choice, or Pauper for a
 * player who has progress from before the choice existed. null means
 * the player should choose.
 */
export function startFormat(saved: string | null, hasProgress: boolean): string | null {
  if (saved !== null) return saved;
  return hasProgress ? FIRST_FORMAT : null;
}
