// Keeps the progress in the browser's localStorage: a small store of
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
