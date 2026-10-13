import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';

// Put the app inside the <div id="app"> of index.html
createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
