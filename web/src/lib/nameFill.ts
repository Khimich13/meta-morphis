// Paints over a card's name with its own title bar, for the question that
// shows the full card (NameHidden in Lesson.tsx). No React in here, so it
// can be tested without a browser.

/** Returns a number from 0 up to, but not including, 1 - like Math.random */
export type Random = () => number;

/**
 * How far to each side a pixel's neighbours are looked at, as a share of
 * the picture's width: wide enough that a letter reaching into the rows
 * above or below the name is outvoted by the title bar around it
 */
export const FILL_REACH = 0.025;

/**
 * Where the name is painted over:
 *   title - in the title bar, where the name is all the print, and the
 *           bar's shading runs every way
 *   text  - in the text box, dark print on a light background. The rows
 *           and columns just outside a name there run along the letters of
 *           the words and lines next to it, and a name starting a line has
 *           the box's border at its left.
 */
export type Area = 'title' | 'text';

/**
 * Which of the colors around a pixel is taken, by brightness: the middle
 * one in the title bar, a lighter one - the paper - in the text box
 */
const PICK: Record<Area, number> = { title: 0.5, text: 0.85 };

/** How many columns to each side of the name the left and right colors are taken from */
const SIDE_COLUMNS = 3;

/**
 * A pixel further than this from the smoothed color next to it, in
 * brightness (the sum of red, green and blue), is print, not grain
 */
const INK = 150;

/** How far the colors along the top and bottom are smoothed sideways, in pixels */
const SMOOTHING = 3;

/**
 * The pixels of the name's area, as RGBA, painted from the title bar
 * around it so that no edge shows:
 *
 *   - In the title bar, each pixel blends the colors on all four sides of
 *     the area (a Coons patch): at every edge it meets the bar exactly, and
 *     in between it follows the bar's own shading. In the text box, only
 *     the colors above and below are blended: the sides may be the border.
 *   - The colors along the top and bottom are chosen among their
 *     neighbours by brightness (see PICK): a letter's tail touching those
 *     rows is dark among light pixels (or light among dark ones), and so
 *     never chosen. They are then smoothed a little, so no column stands
 *     out. The sides are chosen the same way.
 *   - Last, it gets the same fine grain as the bar, measured on the rows
 *     above and below, so it doesn't look smoother than the print around
 *     it. Letters in those rows don't count as grain.
 *
 * `around` is the area with one row more above and below it, and `reach`
 * columns more to its left and right, as RGBA, `aroundWidth` pixels wide.
 */
export function fillName(
  around: Uint8ClampedArray,
  aroundWidth: number,
  reach: number,
  area: Area = 'title',
  random: Random = Math.random,
): Uint8ClampedArray<ArrayBuffer> {
  const pick = PICK[area];
  const width = aroundWidth - 2 * reach;
  const height = around.length / 4 / aroundWidth - 2;
  const pixel = (x: number, y: number): Color => {
    const at = (y * aroundWidth + x) * 4;
    return [around[at], around[at + 1], around[at + 2]];
  };

  // The colors just outside the area: x and y below count from its corner
  const edgeRow = (y: number) =>
    smooth(
      Array.from({ length: width }, (_, x) =>
        choose(Array.from({ length: 2 * reach + 1 }, (_, i) => pixel(x + i, y)), pick),
      ),
    );
  const above = edgeRow(0);
  const below = edgeRow(height + 1);
  const side = (from: number, step: number) =>
    Array.from({ length: height }, (_, y) =>
      choose(
        Array.from({ length: SIDE_COLUMNS }, (_, i) => pixel(from + i * step, y + 1)),
        pick,
      ),
    );
  const left = side(reach - 1, -1);
  const right = side(reach + width, 1);

  // How grainy the bar is: how far its pixels just above and below the
  // area stray, on average, from the smoothed colors there - leaving out
  // the print of the words and lines next to it
  let strays = 0;
  let counted = 0;
  for (let x = 0; x < width; x++) {
    for (const [y, edge] of [[0, above[x]], [height + 1, below[x]]] as const) {
      const stray = brightness(pixel(x + reach, y)) - brightness(edge);
      if (Math.abs(stray) > INK) continue;
      strays += (stray / 3) ** 2;
      counted++;
    }
  }
  const grain = counted ? Math.sqrt(strays / counted) : 0;
  const pixels = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    // How far down and across, with the edges just outside at 0 and 1
    const down = (y + 1) / (height + 1);
    for (let x = 0; x < width; x++) {
      const across = (x + 1) / (width + 1);
      const noise = grain * gaussian(random);
      const at = (y * width + x) * 4;
      for (let c = 0; c < 3; c++) {
        const vertical = above[x][c] * (1 - down) + below[x][c] * down;
        if (area === 'text') {
          pixels[at + c] = vertical + noise;
          continue;
        }
        const sideways = left[y][c] * (1 - across) + right[y][c] * across;
        // What the two share - the corners - would otherwise count twice
        const corners =
          above[0][c] * (1 - across) * (1 - down) +
          above[width - 1][c] * across * (1 - down) +
          below[0][c] * (1 - across) * down +
          below[width - 1][c] * across * down;
        pixels[at + c] = vertical + sideways - corners + noise;
      }
      pixels[at + 3] = 255;
    }
  }
  return pixels;
}

type Color = [number, number, number];

function brightness([r, g, b]: Color): number {
  return r + g + b;
}

/** The color at `pick` of some, by brightness: 0.5 is the middle one */
function choose(colors: Color[], pick: number): Color {
  const sorted = [...colors].sort((a, b) => brightness(a) - brightness(b));
  return sorted[Math.min(colors.length - 1, Math.floor(colors.length * pick))];
}

/** Each color averaged with its SMOOTHING neighbours to each side */
function smooth(colors: Color[]): Color[] {
  return colors.map((_, i) => {
    const near = colors.slice(Math.max(0, i - SMOOTHING), i + SMOOTHING + 1);
    return [0, 1, 2].map(
      (c) => near.reduce((sum, color) => sum + color[c], 0) / near.length,
    ) as Color;
  });
}

/** A random number from a bell curve around 0, with a spread of 1 (Box-Muller) */
function gaussian(random: Random): number {
  // 1 - random() is never 0, so the logarithm stays finite
  return Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random());
}
