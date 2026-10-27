import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';
import { stopPageZoom } from './lib/pinch';

// Pinching changes the card list, not the size of the page
stopPageZoom();

// Put the app inside the <div id="app"> of index.html
createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
