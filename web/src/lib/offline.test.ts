import { afterEach, expect, test, vi } from 'vitest';

import type { Card } from './cards';
import { pictureUrls, savePictures } from './offline';

function card(name: string, images: string[], art: string): Card {
  return { oracle_id: name, name, images, art, artist: 'Some Artist' };
}

test('pictureUrls lists every side and the artwork of each card', () => {
  const cards = [
    card('Hydroblast', ['hydro.webp'], 'hydro-art.webp'),
    card('Fable', ['front.webp', 'back.webp'], 'front-art.webp'),
  ];

  expect(pictureUrls(cards)).toEqual([
    'hydro.webp',
    'hydro-art.webp',
    'front.webp',
    'back.webp',
    'front-art.webp',
  ]);
});

test('pictureUrls lists a shared picture once', () => {
  const cards = [
    card('One', ['same.webp'], 'art.webp'),
    card('Two', ['same.webp'], 'art.webp'),
  ];

  expect(pictureUrls(cards)).toEqual(['same.webp', 'art.webp']);
});

/**
 * A stand-in for the browser's cache storage: the saved addresses, and
 * a set of addresses whose download fails (as when offline)
 */
function fakeCaches(saved: string[], unreachable: string[] = []) {
  const urls = new Set(saved);
  const cache = {
    keys: async () => [...urls].map((url) => ({ url })),
    add: async (url: string) => {
      if (unreachable.includes(url)) throw new Error('offline');
      urls.add(url);
    },
    delete: async (url: string) => urls.delete(url),
  };
  vi.stubGlobal('window', { caches: {} });
  vi.stubGlobal('caches', { open: async () => cache });
  return urls;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const NEW_FORMAT = [card('New', ['new.webp'], 'new-art.webp')];

test('new pictures are saved, then the old ones deleted', async () => {
  const urls = fakeCaches(['old.webp', 'old-art.webp']);

  await savePictures(NEW_FORMAT, () => {});

  expect([...urls].sort()).toEqual(['new-art.webp', 'new.webp']);
});

test("large pictures of the list's cards stay, other ones go", async () => {
  // Zoomed into a card of this list, and into one of another format
  const zoomed = { ...card('New', ['new.webp'], 'new-art.webp'), large_images: ['new-large.jpg'] };
  const urls = fakeCaches(['new.webp', 'new-art.webp', 'new-large.jpg', 'old-large.jpg']);

  await savePictures([zoomed], () => {});

  expect([...urls].sort()).toEqual(['new-art.webp', 'new-large.jpg', 'new.webp']);
});

test('old pictures stay when the new ones cannot all be downloaded', async () => {
  // Switched format, then went offline before the artwork downloaded
  const urls = fakeCaches(['old.webp', 'old-art.webp'], ['new-art.webp']);

  await savePictures(NEW_FORMAT, () => {});

  expect([...urls].sort()).toEqual(['new.webp', 'old-art.webp', 'old.webp']);
});

test('progress counts the pictures saved, out of all wanted', async () => {
  fakeCaches(['new.webp']);
  const reports: [number, number][] = [];

  await savePictures(NEW_FORMAT, (saved, total) => reports.push([saved, total]));

  expect(reports).toEqual([
    [1, 2],
    [2, 2],
  ]);
});
