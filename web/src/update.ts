// Brings a new version of the app onto the screen soon after it is
// published, without ever interrupting a lesson.
//
// The service worker downloads a new version in the background and
// then waits (registerType 'prompt' in vite.config.ts). This hook
// notices the waiting version and switches to it, which reloads the
// page - but only while `canReload` is true.

import { useEffect } from 'react';
import { useRegisterSW } from 'virtual:pwa-register/react';

export function useAppUpdate(canReload: boolean): void {
  const {
    needRefresh: [updateWaiting],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      if (registration === undefined) return;
      // Switching back to an installed app does not reload it, so the
      // browser would not look for a new version. Ask it to whenever
      // the app comes back to the foreground.
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
          // Fails without a connection; the next check will try again
          registration.update().catch(() => {});
        }
      });
    },
  });

  useEffect(() => {
    if (updateWaiting && canReload) {
      updateServiceWorker();
    }
  }, [updateWaiting, canReload, updateServiceWorker]);
}
