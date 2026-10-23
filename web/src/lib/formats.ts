// Which formats and lists the app can teach, and which it starts with.

import { formatLabel } from './cards';

/** The format a player who used the app before formats existed was using */
export const FIRST_FORMAT = 'pauper';

/** A format's lists of most played cards; "all" is creatures and spells */
export type ListKind = 'all' | 'creatures' | 'spells' | 'lands';
export const LIST_KINDS: ListKind[] = ['all', 'creatures', 'spells', 'lands'];
export const LIST_LABELS: Record<ListKind, string> = {
  all: 'All',
  creatures: 'Creatures',
  spells: 'Spells',
  lands: 'Lands',
};

/** A format and one of its lists: what the app is teaching */
export interface Selection {
  format: string;
  kind: ListKind;
}

/** The shape of data/formats.json - see FormatsFile in meta_morphis/export.py */
export interface FormatsFile {
  /** The formats that have card data */
  formats: string[];
  /** Each format's lists that have card data; missing in older files */
  lists?: Record<string, string[]>;
}

export async function loadFormats(): Promise<FormatsFile> {
  const response = await fetch('data/formats.json');
  if (!response.ok) {
    throw new Error(`Could not load formats.json (HTTP ${response.status})`);
  }
  return response.json();
}

/**
 * The name of a list's card file: "pauper" for the overall list,
 * "pauper-creatures" for the others. Must match list_name in
 * meta_morphis/config.py, which names the files.
 */
export function listFile({ format, kind }: Selection): string {
  return kind === 'all' ? format : `${format}-${kind}`;
}

/** The lists a format offers; only the overall list for an older file */
export function listsOf(file: FormatsFile, format: string): ListKind[] {
  const offered = file.lists?.[format] ?? ['all'];
  return LIST_KINDS.filter((kind) => offered.includes(kind));
}

/** A saved list kind, if it is one this app knows; otherwise the overall list */
export function startKind(saved: string | null): ListKind {
  return LIST_KINDS.find((kind) => kind === saved) ?? 'all';
}

/** The chosen kind if the format offers it, otherwise its overall list */
export function kindFor(kind: ListKind, offered: ListKind[]): ListKind {
  return offered.includes(kind) ? kind : 'all';
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

/** "Pauper" for the overall list, "Pauper creatures" for the others */
export function selectionLabel({ format, kind }: Selection): string {
  const name = formatLabel(format);
  return kind === 'all' ? name : `${name} ${LIST_LABELS[kind].toLowerCase()}`;
}
