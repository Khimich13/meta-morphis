# MetaMorphis

An app for learning the most played cards of a Magic: The Gathering format,
in short quiz lessons.

Pick a format (Pauper, Premodern, Pioneer, Standard or Modern) and a list
(all its most played cards, or just its creatures, spells or lands). Each
question shows a card's artwork and asks which card it is. Cards you miss
come back sooner, and cards you know come back later, so lessons spend their
time where it's needed.

It runs in the browser on phones and computers, installs to the home screen
like an app, and works offline once a list has been opened.

## Features

- Lessons of ten cards, with missed cards repeated until answered right
- Spaced repetition: each card has a box that decides when it comes back
- A daily streak, cards seen and cards due for review on the start screen
- Labels for how well each card is known: New, Learning, Known and Tricky
- A card list per format and list, with each card's record
- Full-size card view, swiping between cards, and flipping double-faced cards
- Card names read aloud
- Installable and usable offline

## How it works

```
 MTGGoldfish ──► most played cards ─┐
                                    ├─► Python exporter ──► JSON files ──► web app
 Scryfall ─────► card data ─────────┘   (daily, on           (GitHub Pages)
                                         GitHub Actions)
```

- **`meta_morphis/`** (Python) reads MTGGoldfish's lists of most played
  cards and fetches each card's data from Scryfall, keeping both in a SQLite
  cache. Its exporter writes a JSON file for each format and list.
- **`web/`** (React, TypeScript, Vite) is the app. It reads those JSON files
  and loads card pictures from Scryfall's image servers. Progress is kept in
  the browser.
- **`.github/workflows/deploy.yml`** runs the exporter once a day, builds the
  app and publishes it to GitHub Pages.

The reasoning behind these choices is in [docs/decisions.md](docs/decisions.md).

## Running it locally

You need [uv](https://docs.astral.sh/uv/) for Python 3.10 or newer, and
Node.js 26.

Write the card files (the first run fetches everything and takes a few
minutes):

```bash
uv run python -m meta_morphis.export
```

Start the app at http://localhost:5173:

```bash
cd web
npm ci
npm run dev
```

The offline features only work in a built copy: `npm run build`, then
`npm run preview`.

### Tests and checks

```bash
uv run pytest        # Python tests
uv run mypy .        # Python type check
cd web
npm test             # app tests
npm run check        # TypeScript type check
```

## Credits

Card data and images come from [Scryfall](https://scryfall.com). The lists of
most played cards come from [MTGGoldfish](https://www.mtggoldfish.com). This
project is not affiliated with either.

MetaMorphis is unofficial Fan Content permitted under the Fan Content Policy.
Not approved/endorsed by Wizards. Portions of the materials used are property
of Wizards of the Coast. ©Wizards of the Coast LLC.
