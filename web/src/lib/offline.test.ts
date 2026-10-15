import { expect, test } from 'vitest';

import type { Card } from './cards';
import { pictureUrls } from './offline';

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
