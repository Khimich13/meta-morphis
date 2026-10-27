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

/** Cards per row in the card list, as last pinched, or null if never */
export function loadColumns(): number | null {
  try {
    const saved = Number(localStorage.getItem(COLUMNS_KEY));
    return Number.isInteger(saved) && saved > 0 ? saved : null;
  } catch {
    return null;
  }
}

export function saveColumns(columns: number): void {
  try {
    localStorage.setItem(COLUMNS_KEY, String(columns));
  } catch {
    // Not remembered: the list starts with as many as fit next time
  }
}
