// Reads card names aloud with the browser's built-in speech synthesis,
// using the device's own voices. See issue #10 for the plan to correct
// names the voices pronounce wrongly.

/** False in a browser without speech synthesis: the app then offers none */
export function canSpeak(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

/**
 * A card's name as it should be said. A double-faced card's two names
 * are joined by " // ", which a voice reads out oddly; a comma makes it
 * pause between them instead.
 */
export function spokenName(name: string): string {
  return name.split(' // ').join(', ');
}

export function sayName(name: string): void {
  if (!canSpeak()) return;
  // A name still being read stops, so taps never queue up
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(spokenName(name));
  utterance.lang = 'en-US';
  // An English voice built into the device works offline; the browser
  // picks one by language if the list of voices isn't loaded yet
  const voice = speechSynthesis
    .getVoices()
    .find((candidate) => candidate.lang.startsWith('en') && candidate.localService);
  if (voice !== undefined) utterance.voice = voice;
  speechSynthesis.speak(utterance);
}
