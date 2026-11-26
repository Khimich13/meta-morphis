// The covers over a card's name, for the question that shows the full
// card: on the card in the lesson (CoveredCard in Lesson.tsx), and on its
// large view, which a turn of the phone opens for a card printed
// sideways (see TurningLargeView in CardPicture.tsx).

import './NameCovers.css';

/**
 * Where a card's name is covered, as [left, top, width, height] shares of
 * the card: in the title bar first, then in the text box. `painted` is
 * the title bar painted over the name, as a picture to lay over the
 * first, or null until it is painted - or if it can't be.
 */
export interface NameCover {
  places: number[][];
  painted: string | null;
}

/**
 * How many pixels are taken off the top and the bottom of a cover in the
 * text box, so it sits a little thinner over the line's letters
 */
const TEXT_COVER_TRIM = 1;

/**
 * The covers, laid over a card's picture: the title bar's painted, or a
 * plain bar until then; a plain bar wherever else the name is printed in
 * the text box, so it is plain to see that a word was taken out there.
 * Their parent must be the card's own size.
 */
export default function NameCovers({ cover }: { cover: NameCover }) {
  return cover.places.map((place, i) => (
    <div
      key={i}
      className={i ? 'name-cover in-text' : cover.painted ? 'name-cover painted' : 'name-cover'}
      aria-hidden="true"
      style={{
        left: `${place[0] * 100}%`,
        top: `calc(${place[1] * 100}% + ${i ? TEXT_COVER_TRIM : 0}px)`,
        width: `${place[2] * 100}%`,
        height: `calc(${place[3] * 100}% - ${i ? 2 * TEXT_COVER_TRIM : 0}px)`,
      }}
    >
      {i === 0 && cover.painted && <img src={cover.painted} alt="" />}
    </div>
  ));
}
