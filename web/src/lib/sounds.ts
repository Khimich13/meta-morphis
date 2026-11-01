// Short sounds after an answer, made by the browser itself (the Web Audio
// API), so there are no sound files to download, save for offline use or
// license. They can be turned off on the start screen.

/** One note: a pitch, when it starts and how long it lasts */
export interface Note {
  /** Hertz */
  pitch: number;
  /** Seconds after the sound begins */
  start: number;
  duration: number;
  /** 0 to 1 */
  volume: number;
}

/**
 * Each note of the marimba-like sounds: a short pluck, with a quieter note
 * an octave above that fades sooner, which gives it a wooden ring
 */
function pluck(pitch: number, start: number, duration: number, volume: number): Note[] {
  return [
    { pitch, start, duration, volume },
    { pitch: pitch * 2, start, duration: duration * 0.4, volume: volume * 0.3 },
  ];
}

/**
 * The notes after an answer, like a marimba: three soft plucks rising (G4,
 * C5, E5) for a right one, one low muted pluck (G3) for a wrong one
 */
export function answerNotes(correct: boolean): Note[] {
  return correct
    ? [
        ...pluck(392, 0, 0.16, 0.16),
        ...pluck(523, 0.08, 0.16, 0.16),
        ...pluck(659, 0.16, 0.26, 0.16),
      ]
    : pluck(196, 0, 0.2, 0.3);
}

// One for the whole app, made on the first sound: browsers only allow
// sound to start after the player has tapped something
let context: AudioContext | null = null;

function audioContext(): AudioContext | null {
  if (context !== null) return context;
  if (typeof AudioContext === 'undefined') return null;
  // Safari on iPhones: "ambient" sound stays quiet while the phone is set
  // to silent, and never stops music the player is listening to
  const session = (navigator as Navigator & { audioSession?: { type: string } }).audioSession;
  if (session !== undefined) session.type = 'ambient';
  context = new AudioContext();
  return context;
}

/** Plays the sound for a right or a wrong answer */
export function playAnswerSound(correct: boolean): void {
  playNotes(answerNotes(correct));
}

/** Plays notes, each with a quick rise and a soft fade */
export function playNotes(notes: Note[]): void {
  const audio = audioContext();
  if (audio === null) return;
  // A phone may have paused it while the app was in the background
  if (audio.state === 'suspended') void audio.resume();
  const now = audio.currentTime;
  for (const note of notes) {
    const start = now + note.start;
    const end = start + note.duration;
    // A pure tone (a sine wave), the browser's default
    const oscillator = audio.createOscillator();
    oscillator.frequency.setValueAtTime(note.pitch, start);
    // A quick rise and a soft fade, so the note doesn't click on or off
    const gain = audio.createGain();
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(note.volume, start + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, end);
    oscillator.connect(gain).connect(audio.destination);
    oscillator.start(start);
    oscillator.stop(end);
  }
}
