// Keeps the progress and the chosen format in the browser's localStorage: a small store of
// named text values that survives closing the page. It belongs to this
// browser on this device only.

import { parseProgress, type Progress } from './progress';

const KEY = 'meta-morphis-progress';

export function loadProgress(): Progress {
  try {
    return parseProgress(localStorage.getItem(KEY));
  } catch {
    // Storage can be switched off, for example in some private windows
    return parseProgress(null);
  }
}

export function saveProgress(progress: Progress): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(progress));
  } catch {
    // Storage is full or switched off: the app still works, it just
    // won't remember this session
  }
}

const FORMAT_KEY = 'meta-morphis-format';

/** The format the player chose last time, or null if none was chosen */
export function loadFormat(): string | null {
  try {
    return localStorage.getItem(FORMAT_KEY);
  } catch {
    return null;
  }
}

export function saveFormat(format: string): void {
  try {
    localStorage.setItem(FORMAT_KEY, format);
  } catch {
    // Not remembered: the player is asked again next time
  }
}

const LIST_KEY = 'meta-morphis-list';

/** The list kind ("all", "creatures"...) chosen last time, or null */
export function loadList(): string | null {
  try {
    return localStorage.getItem(LIST_KEY);
  } catch {
    return null;
  }
}

export function saveList(kind: string): void {
  try {
    localStorage.setItem(LIST_KEY, kind);
  } catch {
    // Not remembered: the overall list is used next time
  }
}

const COLUMNS_KEY = 'meta-morphis-columns';
const LANDSCAPE_COLUMNS_KEY = 'meta-morphis-columns-landscape';

/**
 * Cards per row in the card list, as last pinched, or null if never.
 * Upright and sideways each keep their own, since a sideways phone has
 * room for about twice as many.
 */
export function loadColumns(landscape: boolean): number | null {
  try {
    const saved = Number(localStorage.getItem(landscape ? LANDSCAPE_COLUMNS_KEY : COLUMNS_KEY));
    return Number.isInteger(saved) && saved > 0 ? saved : null;
  } catch {
    return null;
  }
}

export function saveColumns(columns: number, landscape: boolean): void {
  try {
    localStorage.setItem(landscape ? LANDSCAPE_COLUMNS_KEY : COLUMNS_KEY, String(columns));
  } catch {
    // Not remembered: the list starts with as many as fit next time
  }
}

const SOUNDS_KEY = 'meta-morphis-sounds';

/** Whether answers make a sound: on unless the player turned them off */
export function loadSoundsOn(): boolean {
  try {
    return localStorage.getItem(SOUNDS_KEY) !== 'off';
  } catch {
    return true;
  }
}

export function saveSoundsOn(on: boolean): void {
  try {
    localStorage.setItem(SOUNDS_KEY, on ? 'on' : 'off');
  } catch {
    // Not remembered: sounds are on again next time
  }
}
