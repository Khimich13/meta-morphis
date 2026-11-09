import {
  type CSSProperties,
  lazy,
  memo,
  type ReactNode,
  type RefObject,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

import { PlainCardPicture } from '../components/CardPicture';
import LargeView from '../components/LargeView';
import StandingLabel from '../components/StandingLabel';
import { type Card, formatLabel } from '../lib/cards';
import { LIST_LABELS, type Selection } from '../lib/formats';
import { isLandscape, useLandscape, useLandscapeAllowed } from '../lib/landscape';
import { useLargeView } from '../lib/largeView';
import { useFewestColumns, usePinchColumns } from '../lib/pinch';
import type { Progress } from '../lib/progress';
import { loadColumns, saveColumns } from '../lib/storage';
import { type Direction, step } from '../lib/swipe';

// The large view's card, with the zoom library: loaded the first time the
// large view opens, so the list starts without it
const LargeCard = lazy(() => import('../components/LargeCard'));

interface CardListProps {
  selection: Selection;
  cards: Card[];
  progress: Progress;
  onBack: () => void;
}

/**
 * How many cards either side of the one in view hold their picture in the
 * large view. A row holding all its cards' full-size pictures ran short
 * of graphics memory while scrolling fast on a phone, and the browser
 * dropped and redrew the cards, which showed as flicker. While skimming
 * fast, the slots further away show a card shape until the cards come near.
 */
const NEARBY = 2;

export default function CardList({ selection, cards, progress, onBack }: CardListProps) {
  // "Most played in Pauper", or "Most played creatures in Pauper"
  const what = selection.kind === 'all' ? '' : `${LIST_LABELS[selection.kind].toLowerCase()} `;

  // The double-faced cards showing their back, by oracle_id. Kept here so
  // the large view shows the same side as the small picture.
  const [backs, setBacks] = useState<Set<string>>(new Set());
  // The same function every time, like open below, so the grid is drawn
  // again only when its cards change
  const flip = useCallback((card: Card) => {
    setBacks((before) => {
      const after = new Set(before);
      if (after.has(card.oracle_id)) after.delete(card.oracle_id);
      else after.add(card.oracle_id);
      return after;
    });
  }, []);

  // One large view for the whole list: a sideways row of every card,
  // which the browser scrolls with the finger and settles on one card
  const large = useLargeView();
  const [index, setIndex] = useState(0);
  const row = useRef<HTMLDivElement>(null);
  const openLarge = large.open;
  const open = useCallback(
    (position: number) => {
      setIndex(position);
      openLarge();
    },
    [openLarge],
  );

  // The list can turn sideways with the phone, keeping the card at the
  // top of the screen in view
  useLandscapeAllowed();
  const landscape = useLandscape();
  const grid = useRef<HTMLUListElement>(null);
  useKeepPlaceOnResize(grid, large.isOpen);

  // Cards per row, chosen by pinching, for upright and for sideways; null:
  // as many as fit
  const [chosen, setChosen] = useState(() => ({
    upright: loadColumns(false),
    sideways: loadColumns(true),
  }));
  // Never fewer than show a whole card on the screen: a choice made on
  // another screen, or before this limit, may be below it
  const fewest = useFewestColumns(grid);
  const choice = landscape ? chosen.sideways : chosen.upright;
  const columns = choice === null ? null : Math.max(choice, fewest);
  const chooseColumns = useCallback((count: number) => {
    const sideways = isLandscape();
    setChosen((before) =>
      sideways ? { ...before, sideways: count } : { ...before, upright: count },
    );
    saveColumns(count, sideways);
  }, []);
  usePinchColumns(grid, columns, chooseColumns, open);

  // Closing the large view: the list shows the card last looked at
  // there, which may be far from the one opened
  const wasOpen = useRef(false);
  useEffect(() => {
    if (wasOpen.current && !large.isOpen && grid.current !== null) {
      showInList(grid.current, index);
    }
    wasOpen.current = large.isOpen;
  }, [large.isOpen, index]);

  // The arrow keys and the buttons for a mouse: scroll to the neighbor
  function move(direction: Direction) {
    const element = row.current;
    const target = step(index, direction, cards.length);
    if (element === null || target === index) return;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    element.scrollTo({
      left: target * element.clientWidth,
      behavior: reduceMotion ? 'auto' : 'smooth',
    });
  }

  return (
    <main className="card-list">
      <header className="card-list-bar">
        <button onClick={onBack}>← Back</button>
        <h1>
          Most played {what}in {formatLabel(selection.format)}
        </h1>
      </header>
      <CardGrid
        gridRef={grid}
        cards={cards}
        progress={progress}
        backs={backs}
        columns={columns}
        onFlip={flip}
        onEnlarge={open}
      />
      {large.isOpen && (
        <LargeView
          onClose={large.close}
          onMove={move}
          hasPrevious={index > 0}
          hasNext={index < cards.length - 1}
        >
          <p className="position" aria-live="polite">
            {index + 1} / {cards.length}
          </p>
          <CardRow rowRef={row} startAt={index} onSettle={setIndex} count={cards.length}>
            {cards.map((card, position) => (
              <div className="card-slide" key={card.oracle_id}>
                {/* Only the cards near the one in view hold a picture; the
                    others show a card shape of the same size */}
                {Math.abs(position - index) <= NEARBY ? (
                  <Suspense fallback={<div className="card-placeholder" />}>
                    <LargeCard
                      card={card}
                      showingBack={backs.has(card.oracle_id)}
                      onFlip={() => flip(card)}
                    />
                  </Suspense>
                ) : (
                  <div className="card-placeholder" />
                )}
              </div>
            ))}
          </CardRow>
        </LargeView>
      )}
    </main>
  );
}

/**
 * The list's grid of small cards. memo skips drawing it again when its
 * props are the same as last time: swiping in the large view changes only
 * which card is shown there, and would otherwise draw every card here too.
 */
const CardGrid = memo(function CardGrid({
  gridRef,
  cards,
  progress,
  backs,
  columns,
  onFlip,
  onEnlarge,
}: {
  gridRef: RefObject<HTMLUListElement | null>;
  cards: Card[];
  progress: Progress;
  backs: Set<string>;
  /** Cards per row; null: as many as fit */
  columns: number | null;
  onFlip: (card: Card) => void;
  onEnlarge: (position: number) => void;
}) {
  return (
    <ul
      ref={gridRef}
      className={columns === null ? 'card-grid' : 'card-grid chosen'}
      style={columns === null ? undefined : ({ '--columns': columns } as CSSProperties)}
    >
      {cards.map((card, position) => (
        <li key={card.oracle_id}>
          {/* How the card is doing, above it */}
          <div className="card-progress">
            <StandingLabel record={progress.cards[card.oracle_id]} />
          </div>
          <PlainCardPicture
            card={card}
            lazy
            showingBack={backs.has(card.oracle_id)}
            onFlip={() => onFlip(card)}
            onEnlarge={() => onEnlarge(position)}
          />
        </li>
      ))}
    </ul>
  );
});

/** How long after a change of size the browser may still be laying the page out, in ms */
const RESIZE_LAYOUT_TIME = 500;

/**
 * Keeps the card at the top of the screen in view when the phone turns,
 * or the window changes size. The list's new width rearranges the rows,
 * and the same scroll position would show other cards. While the browser
 * lays the page out, in steps, the card is brought back after each step.
 *
 * Not while the large view is open: closing it brings its last card into
 * view anyway. And as the phone turns, the large view's card moves as a
 * copy in the page (see EaseNewSize in LargeCard.tsx), which a long scroll
 * made here carried off the screen for a moment: on an iPhone, the scroll
 * reaches the screen a frame or two after the copy is drawn.
 */
function useKeepPlaceOnResize(grid: RefObject<HTMLElement | null>, largeViewOpen: boolean) {
  const paused = useRef(largeViewOpen);
  useEffect(() => {
    paused.current = largeViewOpen;
  }, [largeViewOpen]);
  useEffect(() => {
    let resizedAt = -Infinity;
    let size = '';
    // True while a new window size is being laid out. An iPhone lays out
    // and scrolls the turned page before its resize event, so the size is
    // checked here too, not only when that event comes.
    const resizing = () => {
      const now = `${window.innerWidth}x${window.innerHeight}`;
      if (now !== size) {
        if (size !== '') resizedAt = performance.now();
        size = now;
      }
      return performance.now() - resizedAt < RESIZE_LAYOUT_TIME;
    };
    // The card at the top of the screen; null at the top of the page
    let top: Element | null = null;

    const remember = () => {
      // Not while a new size is being laid out: those scrolls aren't the player's
      if (grid.current === null || resizing()) return;
      if (window.scrollY < 1) {
        top = null;
        return;
      }
      const first = [...grid.current.children].find(
        (card) => card.getBoundingClientRect().bottom > 0,
      );
      // Still the card remembered, if it is in the top row: with more cards
      // per row, as on a phone turned sideways, it may share that row with
      // the cards before it, and turning back should bring back that card
      const sameRow =
        top !== null &&
        first !== undefined &&
        Math.abs(top.getBoundingClientRect().top - first.getBoundingClientRect().top) < 1;
      if (!sameRow) top = first ?? null;
    };
    let measuring = false;
    const onScroll = () => {
      if (measuring) return;
      measuring = true;
      requestAnimationFrame(() => {
        measuring = false;
        remember();
      });
    };
    // Each time the list takes a new size while the new window size is
    // laid out: first its new width, then its new number of cards per row,
    // which React applies a moment later
    const bringBack = () => {
      if (!resizing() || paused.current) return;
      if (top === null) window.scrollTo(0, 0);
      else top.scrollIntoView({ block: 'start' });
    };

    remember();
    window.addEventListener('scroll', onScroll, { passive: true });
    const observer = new ResizeObserver(bringBack);
    if (grid.current !== null) observer.observe(grid.current);
    return () => {
      window.removeEventListener('scroll', onScroll);
      observer.disconnect();
    };
  }, [grid]);
}

/** Scrolls the list just enough to show the card at this position */
function showInList(grid: HTMLElement, position: number) {
  grid.children[position]?.scrollIntoView({ block: 'nearest' });
}

/**
 * The sideways row of cards in the large view. The browser scrolls it with
 * the finger, a trackpad or the code above, and scroll snapping (see
 * components/LargeView.css) brings it to rest exactly on one card;
 * onSettle reports which. At either end, the phone's own edge effect shows
 * there is no more. When the row changes width, as when the phone turns,
 * it stays on the same card.
 */
function CardRow({
  rowRef,
  startAt,
  onSettle,
  count,
  children,
}: {
  rowRef: RefObject<HTMLDivElement | null>;
  startAt: number;
  onSettle: (position: number) => void;
  count: number;
  children: ReactNode;
}) {
  // The card in view, and the row's width when it was last measured
  const shown = useRef(startAt);
  const width = useRef(0);

  // Runs once, when the large view opens: start at the tapped card
  useEffect(() => {
    const element = rowRef.current;
    if (element === null) return;
    // The dialog must be open to have a size to scroll by; the large view
    // opens it now if it hasn't yet
    const dialog = element.closest('dialog');
    if (dialog !== null && !dialog.open) dialog.showModal();
    width.current = element.clientWidth;
    element.scrollLeft = startAt * element.clientWidth;
    markShown(element, startAt);
    // Only the starting position: later changes come from scrolling
  }, []);

  // A new width - the phone turned, or the window was resized
  useEffect(() => {
    const element = rowRef.current;
    if (element === null) return;
    const observer = new ResizeObserver(() => keepCard(element, width, shown));
    observer.observe(element);
    return () => observer.disconnect();
  }, [rowRef]);

  return (
    <div
      className="card-row"
      ref={rowRef}
      onScroll={(event) => {
        const element = event.currentTarget;
        // Scrolled by the change of width, not by the player
        if (keepCard(element, width, shown)) return;
        const position = Math.round(element.scrollLeft / element.clientWidth);
        shown.current = Math.min(Math.max(position, 0), count - 1);
        markShown(element, shown.current);
        onSettle(shown.current);
      }}
    >
      {children}
    </div>
  );
}

/**
 * Marks which card the row is on, for the large view's cards (see
 * EaseNewSize in LargeCard.tsx): as the phone turns, the row's scroll
 * position may show another card for a moment, before keepCard brings it
 * back. Near the end of the list, the browser first stops it at the last
 * card, since the new width leaves less room to scroll.
 */
function markShown(row: HTMLElement, position: number) {
  row.dataset.shown = String(position);
}

/**
 * After the row changed width, scrolls it back to the card that was in
 * view. Its scroll position is in pixels, so at a new width the same
 * position would land on another card. A hidden row has no width, and
 * nothing to scroll to until it shows again. True if the scroll wasn't the
 * player's.
 */
function keepCard(
  element: HTMLElement,
  width: RefObject<number>,
  shown: RefObject<number>,
): boolean {
  const now = element.clientWidth;
  if (now === width.current) return now === 0;
  width.current = now;
  if (now > 0) element.scrollLeft = shown.current * now;
  return true;
}
