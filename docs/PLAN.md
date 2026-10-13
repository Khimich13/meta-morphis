# meta-morphis plan

## Goal

An app for phones and computers that teaches the most-played cards of a Magic format, starting with Pauper, through short quiz lessons. It is for me and my friends first.

## How we work

1. Nothing is added unless its purpose fits in one sentence tied to something visible in the app. Everything else waits.
2. Before each brick: a short explanation of what it does and why. Then only that brick is built.
3. I read the change and ask questions. We commit when it makes sense to me.
4. I understand well the code that decides which answer is correct and the code that saves progress. Layout, styling and configuration I can understand loosely.

## Bricks

Each brick ends with something I can see and use.

| # | Brick | What I can see when it's done | Status |
|---|---|---|---|
| 0 | Backend groundwork: Scryfall rate limits, Pauper list with creatures, extra card fields, symbols fetch, meta timestamp | Tests pass | Done |
| 1 | Export one file, `web/public/data/pauper.json`, with each Pauper card's name, ID and picture link | The file, opened in an editor | Done |
| 2 | A web page that shows those 50 cards | The cards in a browser on my computer | Done |
| 3 | Put it online, with the required fan-content notice | The cards on my phone | Done |
| 4 | First quiz type: name the card from its art | A playable lesson | Done |
| 5 | Remember progress and a streak | My progress is still there tomorrow | **Next** |
| 6 | Works offline and installs to the home screen | A lesson in airplane mode | |
| 7 | Refresh the card data automatically once a day | New cards appear without me doing anything | |
| 8+ | One more quiz type at a time: mana cost, then name from text, then whatever I want | A new kind of question | |

## Decisions that apply now

- **Two programs, one file between them.** Python writes a JSON file per format. The app reads that file and loads card pictures from Scryfall's image servers. The app never calls Scryfall's API or MTGGoldfish.
- **The exporter is one module,** `meta_morphis/export.py`. Each brick adds only the fields it needs.
- **The app is built with React, TypeScript and Vite,** in a `web/` folder, introduced one piece at a time from brick 2.
- **Hosting is GitHub Pages.** It is free for this public repository.
- **From MTGGoldfish we use only the list of cards.** No rank, deck percentage or copy counts.
- **Progress is saved on the device,** under each card's Scryfall `oracle_id`, which stays the same across reprints.
- **Pauper first.** Other formats come after the bricks above.

## Rules we must follow

- **Show the fan-content notice** in the app before anyone else uses it, word for word as Wizards of the Coast requires.
- **Keep it free, with no required sign-up.** Both Wizards of the Coast and Scryfall require this.
- **Never alter card pictures:** no covering, cropping, dimming or stretching. When art is shown on its own, credit the artist next to it.
- **Stay within Scryfall's rate limit** of 2 requests per second. The backend already does.
- **Don't share the app publicly yet.** MTGGoldfish's terms allow personal use only. Before a public launch, get their permission or switch to the replacement source.

## Later, when wanted

Details for all of these are in [full-design.md](full-design.md), which is background research and not something to read through:

- more quiz types and more formats
- our own "most played" list computed from tournament decklists, replacing MTGGoldfish (section 9a there)
- rank and deck percentage in the app, which that replacement makes possible
- units, XP, daily goals, reminders, backup, account sync
- automated browser, accessibility and performance testing
