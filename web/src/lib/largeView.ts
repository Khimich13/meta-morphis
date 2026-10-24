import { useEffect, useState } from 'react';

/**
 * Whether the large view is open, and how to open and close it. The
 * phone's back gesture should close the large view, not leave the app:
 * opening it adds a step to the browser's history, every way of closing
 * goes back one step, and the view closes when that happens.
 */
export function useLargeView() {
  const [isOpen, setOpen] = useState(false);

  function open() {
    history.pushState({ enlarged: true }, '');
    setOpen(true);
  }
  const close = () => history.back();

  useEffect(() => {
    if (!isOpen) return;
    const onBack = () => setOpen(false);
    window.addEventListener('popstate', onBack);
    return () => window.removeEventListener('popstate', onBack);
  }, [isOpen]);

  return { isOpen, open, close };
}
