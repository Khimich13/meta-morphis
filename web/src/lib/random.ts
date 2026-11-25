// Random choices the quiz makes, taken from a function that can be
// swapped for one the tests can repeat

/** Returns a number from 0 up to, but not including, 1 - like Math.random */
export type Random = () => number;

/** A shuffled copy of the list. The original is left as it was. */
export function shuffle<T>(items: readonly T[], random: Random = Math.random): T[] {
  const result = [...items];
  // Fisher-Yates: walk from the end, swapping each item with a random earlier one
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}
