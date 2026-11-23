# MetaMorphis

An app for learning the most played cards of a Magic: The Gathering format,
in short quiz lessons.

Pick a format (Pauper, Premodern, Pioneer, Standard or Modern) and a list
(all its most played cards, or just its creatures, spells or lands). Each
question shows a card's artwork, or the whole card with its name covered,
and asks which card it is - or the whole card with its mana cost, or a
creature's power and toughness or types, covered, and asks what they
are. Cards you miss come back sooner, and cards you know come back
later, so lessons spend their time where it's needed.

It runs in the browser on phones and computers, installs to the home screen
like an app, and works offline once a list has been opened.

## Features

- Lessons of ten cards, with missed cards repeated until answered right
- Spaced repetition: each card has a level from 0 to 5 that decides when it
  comes back. A right answer moves it up a level and a wrong one down, and
  only the first answer of each day counts.
- A daily streak, cards seen and mastered, and cards due for review on the
  start screen
- A card list per format and list, with three pips above each card for
  the steps to Mastered (level 3 and up). It also works with the phone
  turned sideways, with its own number of cards per row.
- Full-size card view, swiping between cards, flipping double-faced cards, and
  turning the phone to read cards printed sideways
- Card names read aloud
- Installable and usable offline

## How it works

```
 Magic Online ─► decklists ─────────┐
                                    ├─► Python exporter ──► JSON files ──► web app
 Scryfall ─────► card data ─────────┘   (daily, on           (GitHub Pages)
                                         GitHub Actions)
```

- **`meta_morphis/`** (Python) counts the most played cards of each
  format in the last 30 days of decklists Magic Online publishes, from
  [fbettega's archive](https://github.com/fbettega/MTG_decklistcache) on
  GitHub, keeping the count in a SQLite database. It reads each card's
  data from Scryfall's daily file of every card, downloaded only when
  Scryfall has made a newer one. Its exporter writes a JSON file for each
  format and list, and every card in `cards/`. It reads
  card pictures with Tesseract to find a card's name in its text box, and
  keeps what it found in `meta_morphis/name_in_text.json`, in git.
- **`web/`** (React, TypeScript, Vite) is the app. It reads those JSON files
  and loads card pictures from Scryfall's image servers. Progress is kept in
  the browser.
- **`.github/workflows/deploy.yml`** runs the exporter once a day, builds the
  app and publishes it to GitHub Pages.

The reasoning behind these choices is in [docs/decisions.md](docs/decisions.md).

## Running it locally

You need [uv](https://docs.astral.sh/uv/) for Python 3.10 or newer,
Node.js 26, and [Tesseract](https://tesseract-ocr.github.io/) (`sudo apt
install tesseract-ocr`). Without Tesseract the export still works, but cards
with their name in their text box are asked only by their artwork.

Write the card files (the first run downloads Scryfall's card data, about
80 MB, and the last 30 days of decklists, a few hundred small files, and
takes a few minutes):

```bash
uv run python -m meta_morphis.export
```

It reads the pictures of printings not yet in
`meta_morphis/name_in_text.json` and adds them there: commit the file, so
the daily run doesn't read them again.

The export reads the pictures of cards on a format's list, and of other
cards not read yet for at most 15 minutes, which covers a new set. To read
every other card's too, so cards on a player's own list are asked by their
full picture with the name covered (about 2 hours on 12 cores; stop it with
Ctrl+C at any time, and run it again to go on):

```bash
uv run python -m meta_morphis.read_every_picture
```

Then commit `meta_morphis/name_in_text.json`.

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
uv run ruff check .  # Python lint
uv run ruff format . # Python formatting
cd web
npm test             # app tests
npm run check        # TypeScript type check
```

## Credits

Card data and images come from [Scryfall](https://scryfall.com). The most
played cards are counted from the decklists
[Magic Online](https://www.mtgo.com/decklists) publishes, as
[fbettega's MTG_decklistcache](https://github.com/fbettega/MTG_decklistcache)
keeps them. This project is not affiliated with any of them.

MetaMorphis is unofficial Fan Content permitted under the Fan Content Policy.
Not approved/endorsed by Wizards. Portions of the materials used are property
of Wizards of the Coast. ©Wizards of the Coast LLC.
