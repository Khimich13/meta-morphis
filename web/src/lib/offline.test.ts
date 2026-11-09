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
  const cards = [card('One', ['same.webp'], 'art.webp'), card('Two', ['same.webp'], 'art.webp')];

  expect(pictureUrls(cards)).toEqual(['same.webp', 'art.webp']);
});

/**
 * A stand-in for the browser's cache storage and the picture server: the
 * saved addresses, the addresses whose download fails (as when offline),
 * and the addresses the server answers with an error status
 */
function fakeCaches(
  saved: string[],
  unreachable: string[] = [],
  statuses: Record<string, number> = {},
) {
  const urls = new Set(saved);
  const cache = {
    keys: async () => [...urls].map((url) => ({ url })),
    put: async (url: string) => {
      urls.add(url);
    },
    delete: async (url: string) => urls.delete(url),
  };
  vi.stubGlobal('window', { caches: {} });
  vi.stubGlobal('caches', { open: async () => cache });
  vi.stubGlobal('fetch', async (url: string) => {
    if (unreachable.includes(url)) throw new TypeError('offline');
    const status = statuses[url] ?? 200;
    return { ok: status === 200, status };
  });
  return urls;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const NEW_FORMAT = [card('New', ['new.webp'], 'new-art.webp')];

/** The format has no other lists */
const NOTHING_ELSE = async () => [];

test('new pictures are saved, then the old ones deleted', async () => {
  const urls = fakeCaches(['old.webp', 'old-art.webp']);

  await savePictures(NEW_FORMAT, NOTHING_ELSE, () => {});

  expect([...urls].sort()).toEqual(['new-art.webp', 'new.webp']);
});

test("large pictures of the list's cards stay, other ones go", async () => {
  // Zoomed into a card of this list, and into one of another format
  const zoomed = { ...card('New', ['new.webp'], 'new-art.webp'), large_images: ['new-large.jpg'] };
  const urls = fakeCaches(['new.webp', 'new-art.webp', 'new-large.jpg', 'old-large.jpg']);

  await savePictures([zoomed], NOTHING_ELSE, () => {});

  expect([...urls].sort()).toEqual(['new-art.webp', 'new-large.jpg', 'new.webp']);
});

test('old pictures stay when the new ones cannot all be downloaded', async () => {
  // Switched format, then went offline before the artwork downloaded
  const urls = fakeCaches(['old.webp', 'old-art.webp'], ['new-art.webp']);

  await savePictures(NEW_FORMAT, NOTHING_ELSE, () => {});

  expect([...urls].sort()).toEqual(['new.webp', 'old-art.webp', 'old.webp']);
});

test('a picture the server no longer has does not keep the old ones', async () => {
  const urls = fakeCaches(['old.webp'], [], { 'new-art.webp': 404 });
  const reports: [number, number][] = [];

  await savePictures(NEW_FORMAT, NOTHING_ELSE, (saved, total) => reports.push([saved, total]));

  expect([...urls].sort()).toEqual(['new.webp']);
  // The missing picture leaves the total, so the saving can finish
  expect(reports.at(-1)).toEqual([1, 1]);
});

test('old pictures stay after a passing server error', async () => {
  const urls = fakeCaches(['old.webp'], [], { 'new-art.webp': 503 });

  await savePictures(NEW_FORMAT, NOTHING_ELSE, () => {});

  expect([...urls].sort()).toEqual(['new.webp', 'old.webp']);
});

test("pictures of the format's other lists stay", async () => {
  // Switched from the format's creature list to its spell list
  const creatures = [
    { ...card('Elf', ['elf.webp'], 'elf-art.webp'), large_images: ['elf-large.jpg'] },
  ];
  const urls = fakeCaches(['elf.webp', 'elf-art.webp', 'elf-large.jpg', 'old.webp']);

  await savePictures(
    NEW_FORMAT,
    async () => creatures,
    () => {},
  );

  expect([...urls].sort()).toEqual([
    'elf-art.webp',
    'elf-large.jpg',
    'elf.webp',
    'new-art.webp',
    'new.webp',
  ]);
});

test("nothing is deleted when the format's other lists cannot load", async () => {
  const urls = fakeCaches(['old.webp']);
  const offline = async () => {
    throw new Error('offline');
  };

  await savePictures(NEW_FORMAT, offline, () => {});

  expect([...urls].sort()).toEqual(['new-art.webp', 'new.webp', 'old.webp']);
});

test('progress counts the pictures saved, out of all wanted', async () => {
  fakeCaches(['new.webp']);
  const reports: [number, number][] = [];

  await savePictures(NEW_FORMAT, NOTHING_ELSE, (saved, total) => reports.push([saved, total]));

  expect(reports).toEqual([
    [1, 2],
    [2, 2],
  ]);
});
