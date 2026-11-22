// Mana costs as Scryfall writes them, "{1}{U}{U}": their symbols, the
// symbols' pictures, and the wrong costs a question about one offers.
// No React in here, so it can be tested without a browser.

/** A cost's symbols, in order: "{X}{1}{U}" → ["X", "1", "U"] */
export function symbols(cost: string): string[] {
  return [...cost.matchAll(/\{([^}]*)\}/g)].map((match) => match[1]);
}

/**
 * A symbol's picture on Scryfall's server, named after the symbol
 * without its slashes: "W/U" → WU.svg
 */
export function symbolUrl(symbol: string): string {
  return `https://svgs.scryfall.io/card-symbols/${symbol.replace(/\//g, '')}.svg`;
}

/**
 * A cost taken apart: its generic mana, and each other symbol (X, a
 * color, a hybrid, {C}) with how many times it is printed, in the order
 * printed
 */
interface Parts {
  generic: number;
  kinds: [string, number][];
}

function parse(cost: string): Parts {
  const parts: Parts = { generic: 0, kinds: [] };
  for (const symbol of symbols(cost)) {
    if (/^\d+$/.test(symbol)) {
      parts.generic += Number(symbol);
      continue;
    }
    const kind = parts.kinds.find(([name]) => name === symbol);
    if (kind) kind[1] += 1;
    else parts.kinds.push([symbol, 1]);
  }
  return parts;
}

/**
 * The cost written out as cards print it: X first, then the generic
 * mana, then the other symbols, each kind's together. Nothing at all is
 * {0}.
 */
function write({ generic, kinds }: Parts): string {
  const repeat = ([name, count]: [string, number]) => `{${name}}`.repeat(count);
  const variable = kinds.filter(([name]) => name === 'X').map(repeat);
  const others = kinds.filter(([name]) => name !== 'X').map(repeat);
  const printed = [...variable, generic > 0 ? `{${generic}}` : '', ...others].join('');
  return printed || '{0}';
}

/**
 * The costs one change away: one generic mana more or less, one more or
 * one fewer of a symbol the cost has, or one of those swapped for a
 * generic mana or the other way round. Every kind of symbol stays at
 * least once: the card's frame shows its colors.
 */
function changes({ generic, kinds }: Parts): Parts[] {
  const near: Parts[] = [{ generic: generic + 1, kinds }];
  if (generic > 0) near.push({ generic: generic - 1, kinds });
  kinds.forEach(([name, count], i) => {
    const withCount = (newCount: number) =>
      kinds.map((kind, j): [string, number] => (j === i ? [name, newCount] : kind));
    near.push({ generic, kinds: withCount(count + 1) });
    if (count > 1) near.push({ generic, kinds: withCount(count - 1) });
    // X is no mana by itself, so it isn't swapped for generic mana
    if (name === 'X') return;
    if (count > 1) near.push({ generic: generic + 1, kinds: withCount(count - 1) });
    if (generic > 0) near.push({ generic: generic - 1, kinds: withCount(count + 1) });
  });
  return near;
}

/**
 * Wrong costs near this one, for a question about it, nearest first:
 * those one change away (see changes), then, if they are fewer than
 * `count`, those two away, and so on. One list per step.
 * {1}{U} → [["{2}{U}", "{U}", "{1}{U}{U}", "{U}{U}"]]
 */
export function nearCosts(cost: string, count: number): string[][] {
  const seen = new Set([cost, write(parse(cost))]);
  const steps: string[][] = [];
  let found = 0;
  let from = [parse(cost)];
  // One more generic mana is always new, so each step finds more
  while (found < count) {
    const step: string[] = [];
    const next: Parts[] = [];
    for (const parts of from) {
      for (const near of changes(parts)) {
        const written = write(near);
        if (seen.has(written)) continue;
        seen.add(written);
        step.push(written);
        next.push(near);
      }
    }
    steps.push(step);
    found += step.length;
    from = next;
  }
  return steps;
}
