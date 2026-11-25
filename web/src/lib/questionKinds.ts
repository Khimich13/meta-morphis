// Each kind of question the quiz asks, in one place: which cards it can
// ask about, its right answer, and the answers it offers. A new kind is
// a new entry in KINDS. No React in here, like quiz.ts.

import { type Card, partName, partType, type PowerToughness } from './cards';
import { nearCosts } from './manaCost';
import { type Random, shuffle } from './random';

export const OPTION_COUNT = 4;

/** An answer to choose from */
export interface Option {
  card: Card;
  /**
   * The name on its button: a double-faced card's is one side's name,
   * the side asked about for the card itself, a random one for a wrong
   * answer - so a back side's name never tells the answer apart. The
   * same for a card with a spell: its spell's name or its main part's,
   * and a split card: one half's. For a question about the cost, a cost
   * as Scryfall writes it, "{1}{U}{U}", for one about the power and
   * toughness, both as printed, "2/3", and for one about the creature
   * types, those as printed, "Goblin Warrior": then `card` is the card
   * asked about on every answer.
   */
  name: string;
}

/** The part of the card a question asks about */
export interface Part {
  /** Asked about a double-faced card's back side */
  back: boolean;
  /**
   * Asked about an adventure's or prepare card's spell alone, by the
   * full picture with the spell's name covered (see SpellPart in cards.ts)
   */
  spell: boolean;
  /**
   * The half of a split card asked about, 0 for the first and 1 for the
   * second: by its half of the artwork, or by the full picture with its
   * name covered and the other's in sight (see halves in cards.ts). Null
   * for every other card.
   */
  half: number | null;
}

/** Where wrong answers come from, each list in turn (see makeQuestion in quiz.ts) */
export type Pools = readonly (readonly Card[])[];

/** How one kind of question asks about a card */
export interface Kind {
  /** Whether the card, on the part chosen, can be asked this way */
  asks(card: Card, part: Part): boolean;
  /** The right answer's words: a name, "{1}{U}{U}", "2/3", "Goblin Warrior" */
  answer(card: Card, part: Part): string;
  /** Every answer to choose from, the right one among them, in the order shown */
  options(card: Card, part: Part, pools: Pools, random: Random): Option[];
}

export type QuestionKind = 'picture' | 'artwork' | 'cost' | 'powerToughness' | 'creatureType';

/**
 * Every kind, in the order makeQuestion picks from. A spell is asked
 * about only by its picture: the artwork is the main part's.
 */
export const KINDS: Record<QuestionKind, Kind> = {
  // The full card, the side asked about, with its name covered (see
  // name_box in cards.ts), or a spell's alone (see Part's spell), or a
  // split card's half's (see Part's half)
  picture: {
    asks: (card, part) => part.spell || !!nameBox(card, part),
    answer: partNameOf,
    options: nameOptions,
  },
  // The card's artwork alone
  artwork: {
    asks: (_card, part) => !part.spell,
    answer: partNameOf,
    options: nameOptions,
  },
  // The full card with its mana cost covered (see cost in cards.ts),
  // asking what it costs
  cost: {
    asks: (card, part) => !part.spell && !!card.cost,
    answer: (card) => card.cost?.mana_cost ?? '',
    options: (card, _part, _pools, random) =>
      card.cost ? costOptions(card, card.cost.mana_cost, random) : [],
  },
  // The full card with its power and toughness covered (see
  // power_toughness in cards.ts), asking what they are
  powerToughness: {
    asks: (card, part) => !part.spell && !!card.power_toughness,
    answer: (card) => (card.power_toughness ? printedPowerToughness(card.power_toughness) : ''),
    options: (card, _part, _pools, random) =>
      card.power_toughness ? powerToughnessOptions(card, card.power_toughness, random) : [],
  },
  // The full card with its type line covered (see creature_type in
  // cards.ts), asking its creature types
  creatureType: {
    asks: (card, part) => !part.spell && !!card.creature_type,
    answer: (card) => card.creature_type?.types.join(' ') ?? '',
    options: (card, _part, pools, random) =>
      card.creature_type ? creatureTypeOptions(card, card.creature_type.types, pools, random) : [],
  },
};

/** Every kind, in the order of KINDS */
export const QUESTION_KINDS = Object.keys(KINDS) as QuestionKind[];

/**
 * Where the name of the side or half asked about sits on its picture
 * (see name_box in cards.ts): null or missing when it can't be covered
 */
function nameBox(card: Card, { back, half }: Part) {
  if (card.halves && half !== null) return card.halves[half].name_box;
  return back ? card.back?.name_box : card.name_box;
}

/** The name of the part asked about, as its answer button shows it (see partName) */
function partNameOf(card: Card, { back, spell, half }: Part): string {
  return partName(card, back, spell, half);
}

/**
 * The answers to a question asking for the card's name, in the order
 * shown: the part asked about's and OPTION_COUNT - 1 wrong ones.
 *
 * The wrong answers are of the same type as the part asked about, so the
 * shape of a name never gives the answer away - a planeswalker's "Name,
 * epithet" among three plain names. Only when the pools run out of that
 * type do cards of other types fill in (see wrongOptions).
 */
function nameOptions(card: Card, part: Part, pools: Pools, random: Random): Option[] {
  const right = { card, name: partNameOf(card, part) };
  const wrong = wrongOptions(card, partType(card, part.back, part.spell, part.half), pools, random);
  return shuffle([right, ...wrong], random);
}

/**
 * OPTION_COUNT - 1 wrong answers for a question about the card, whose
 * part asked about is of this type: cards with a part of that type
 * first, each named by such a part, the earlier pools' before the later
 * ones', in random order within each pool. Then, if those are too few,
 * any other cards, each named by a random part. A card in more than one
 * pool counts once.
 */
function wrongOptions(card: Card, type: string, pools: Pools, random: Random): Option[] {
  const seen = new Set([card.oracle_id]);
  const matching: Option[] = [];
  const others: Card[] = [];
  for (const pool of pools) {
    for (const other of shuffle(pool, random)) {
      if (seen.has(other.oracle_id)) continue;
      seen.add(other.oracle_id);
      const parts = answerParts(other).filter((part) => part.type === type);
      if (parts.length > 0) {
        matching.push({ card: other, name: parts[Math.floor(random() * parts.length)].name });
      } else {
        others.push(other);
      }
    }
    if (matching.length >= OPTION_COUNT - 1) break;
  }
  const filler = others.map((other) => ({ card: other, name: wrongName(other, random) }));
  return [...matching, ...filler].slice(0, OPTION_COUNT - 1);
}

/**
 * The answers to a question about the card's cost, in the order shown:
 * its own and OPTION_COUNT - 1 wrong ones near it (see nearCosts), the
 * nearest first, at random among those as near as each other
 */
function costOptions(card: Card, cost: string, random: Random): Option[] {
  const wrong = nearCosts(cost, OPTION_COUNT - 1)
    .flatMap((step) => shuffle(step, random))
    .slice(0, OPTION_COUNT - 1);
  return shuffle([cost, ...wrong], random).map((name) => ({ card, name }));
}

/**
 * The answers to a question about the card's power and toughness, in
 * the order shown: the four corners of a square, its own one of them -
 * with the power one more or one less, the toughness one more or one
 * less, and both. A 2/2 offers 2/2, 3/2, 2/3 and 3/3, or 1/2, 2/2, 1/3
 * and 2/3, and so on. Each answer shares a number with two others, so
 * none stands out; answers all around the card's own (2/2 among 1/2,
 * 3/2 and 2/3) would give it away as the one in the middle. Never below
 * 0, and a toughness of 0 only on a card that has it.
 */
function powerToughnessOptions(
  card: Card,
  { power, toughness }: PowerToughness,
  random: Random,
): Option[] {
  const [p, t] = [Number(power), Number(toughness)];
  const powers = [p, p === 0 || random() < 0.5 ? p + 1 : p - 1];
  const toughnesses = [t, t <= 1 || random() < 0.5 ? t + 1 : t - 1];
  const square = powers.flatMap((a) => toughnesses.map((b) => `${a}/${b}`));
  return shuffle(square, random).map((name) => ({ card, name }));
}

/** Power and toughness as cards print them: "2/3" */
function printedPowerToughness({ power, toughness }: PowerToughness): string {
  return `${power}/${toughness}`;
}

/**
 * The answers to a question about the card's creature types, in the
 * order shown: the four corners of a square, as for the power and
 * toughness - its own types, with the first swapped for another, the
 * last swapped for another, and both. A Goblin Warrior offers Goblin
 * Warrior, Elf Warrior, Goblin Scout and Elf Scout; a type in between
 * stays (Human Soldier Ranger). Each answer shares a word with two
 * others, so none stands out. A card of one type offers three other
 * single types: Bird among Insect, Spirit and Elemental.
 *
 * A word is swapped for one that other creatures have in the same
 * place - a first for a first, a last for a last, a single type for a
 * single type - so a race stays a race (Goblin, Elf) and a job a job
 * (Warrior, Scout). They come from `pools` in turn, the cards being
 * learned first, at random within each, so a type more creatures have
 * comes up more often. Only when those run out does a word from
 * anywhere on their type lines fill in.
 */
function creatureTypeOptions(
  card: Card,
  types: readonly string[],
  pools: Pools,
  random: Random,
): Option[] {
  // The words in a place of the other creatures' types, the pools in
  // turn, each pool shuffled anew for each place: so the first and the
  // last swapped in come from different creatures, and the answer with
  // both swapped isn't always another creature's whole type
  const wordsAt = (place: (words: readonly string[]) => readonly string[]) =>
    pools.flatMap((pool) =>
      shuffle(pool, random).flatMap((other) =>
        other.oracle_id !== card.oracle_id && other.creature_type
          ? place(other.creature_type.types)
          : [],
      ),
    );
  const single = wordsAt((words) => (words.length === 1 ? words : []));
  const firsts = wordsAt((words) => (words.length > 1 ? words.slice(0, 1) : []));
  const lasts = wordsAt((words) => (words.length > 1 ? words.slice(-1) : []));
  const anywhere = wordsAt((words) => words);
  const taken = new Set(types);
  /** The first of the words not taken yet, which is taken then */
  const take = (words: readonly string[]): string[] => {
    const word = words.find((word) => !taken.has(word));
    if (word === undefined) return [];
    taken.add(word);
    return [word];
  };

  let answers: string[][];
  if (types.length === 1) {
    const wrong = Array.from({ length: OPTION_COUNT - 1 }, () =>
      take([...single, ...anywhere]),
    ).flat();
    answers = [[...types], ...wrong.map((word) => [word])];
  } else {
    const firstWords = [types[0], ...take([...firsts, ...anywhere])];
    const lastWords = [types.at(-1)!, ...take([...lasts, ...anywhere])];
    const middle = types.slice(1, -1);
    answers = firstWords.flatMap((first) => lastWords.map((last) => [first, ...middle, last]));
  }
  return shuffle(answers, random).map((words) => ({ card, name: words.join(' ') }));
}

/**
 * The parts of a card that can be asked about, each with its name, as
 * its answer button shows it, and its type: a split card's halves, an
 * adventure's or prepare card's main part and spell, a double-faced
 * card's sides, or any other card whole
 */
function answerParts(card: Card): { name: string; type: string }[] {
  const part = (back: boolean, spell: boolean, half: number | null = null) => ({
    name: partName(card, back, spell, half),
    type: partType(card, back, spell, half),
  });
  if (card.halves) return [part(false, false, 0), part(false, false, 1)];
  if (card.spell?.name_box) return [part(false, false), part(false, true)];
  if (card.images.length > 1) return [part(false, false), part(true, false)];
  return [part(false, false)];
}

/**
 * A wrong answer's name: a random side or part of its card, of those
 * that can be asked about, so the right answer's never stands out
 */
function wrongName(card: Card, random: Random): string {
  const parts = answerParts(card);
  return parts[Math.floor(random() * parts.length)].name;
}
