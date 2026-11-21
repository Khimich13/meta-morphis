import { useCallback, useEffect, useRef, useState } from 'react';

/** How long the large view takes to close; keep in step with .closing in LargeView.css */
export const CLOSE_TIME = 300;

/**
 * Whether the large view is open, and how to open and close it. The
 * phone's back gesture should close the large view, not leave the app:
 * opening it adds a step to the browser's history, every way of closing
 * goes back one step, and the view closes when that happens.
 *
 * Closing, the view stays for a moment (`closing`) as it fades out and
 * the page brightens back (see .closing in LargeView.css), the opening
 * reversed. closeAtOnce skips that, for a view that has already faded
 * out in its own way (see useOpenOnTurn in CardPicture.tsx).
 */
export function useLargeView() {
  const [state, setState] = useState<'closed' | 'open' | 'closing'>('closed');
  const atOnce = useRef(false);

  // The same function every time, so effects can depend on it
  const open = useCallback(() => {
    // Going back, the browser would put the page back where it was scrolled
    // when the view opened. After the phone has turned, that position
    // shows other cards; the card list brings its card into view itself.
    history.scrollRestoration = 'manual';
    history.pushState({ enlarged: true }, '');
    atOnce.current = false;
    setState('open');
  }, []);
  const close = useCallback(() => history.back(), []);
  const closeAtOnce = useCallback(() => {
    atOnce.current = true;
    history.back();
  }, []);

  useEffect(() => {
    if (state !== 'open') return;
    const onBack = () => {
      const still = atOnce.current || matchMedia('(prefers-reduced-motion: reduce)').matches;
      setState(still ? 'closed' : 'closing');
    };
    window.addEventListener('popstate', onBack);
    return () => window.removeEventListener('popstate', onBack);
  }, [state]);

  useEffect(() => {
    if (state !== 'closing') return;
    const timer = setTimeout(() => setState('closed'), CLOSE_TIME);
    return () => clearTimeout(timer);
  }, [state]);

  return { isOpen: state !== 'closed', closing: state === 'closing', open, close, closeAtOnce };
}
