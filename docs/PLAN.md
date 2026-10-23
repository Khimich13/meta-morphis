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

New features get a row. Fixes and adjustments to an existing brick are recorded in the git history, not here.

| # | Brick | What I can see when it's done | Status |
|---|---|---|---|
| 0 | Backend groundwork: Scryfall rate limits, Pauper list with creatures, extra card fields, symbols fetch, meta timestamp | Tests pass | Done |
| 1 | Export one file, `web/public/data/pauper.json`, with each Pauper card's name, ID and picture link | The file, opened in an editor | Done |
| 2 | A web page that shows those 50 cards | The cards in a browser on my computer | Done |
| 3 | Put it online, with the required fan-content notice | The cards on my phone | Done |
| 4 | First quiz type: name the card from its art | A playable lesson | Done |
| 5 | Remember progress and a streak | My progress is still there tomorrow | Done |
| 6 | Works offline and installs to the home screen | A lesson in airplane mode | Done |
| 6b | Lesson layout that fits one screen: top bar with progress, the full card after answering | A lesson with no scrolling | Done |
| 6c | Portrait only: installed Android app stays upright; a sideways phone shows "Turn your phone upright" | No sideways layout on a phone | Done |
| 6d | A start screen in place of the card list: streak, cards seen, Start lesson; the card list moves behind a "See all cards" link | A start screen that fits one screen | Done |
| 6e | Show each card in the printing whose artwork appears on the most regular printings, the same printing in the question and after answering | Familiar artworks, and a full card that matches the question | Done |
| 6f | A missed card comes back at the end of the lesson, as a new question, until it is answered right; the score and saved progress count first tries only | Every lesson ends with every card answered right | Done |
| 6g | Lessons that use progress: each card sits in a box from 0 to 5 that sets when it is asked again (Leitner boxes); a lesson takes due cards first, then up to 3 new ones; the start screen shows how many are due | Missed cards come back sooner, known ones later | Done |
| 6h | Labels for how well each card is known: New, Learning, Known, and Tricky for often-missed cards, shown in the lesson, after a wrong answer and in the card list | Which cards I know and which I struggle with | Done |
| 6i | Pick the format: Pauper, Premodern, Pioneer, Standard or Modern; each is exported on its own, and the app remembers the last one that loaded | Lessons for the format I play | Done |
| 6j | Flip double-faced cards: a see-through round button over the artwork turns the card over with a short 3D turn, after answering and in the card list | The back side of a double-faced card | Done |
| 6k | Tap a card to see it as large as the screen allows; close with ✕, a tap outside, Esc or the back gesture; double-faced cards keep their flip button | A card I can read in full | Done |
| 6l | Hear a card's name: a speaker button after answering, and on the enlarged card, using the device's own voices | A card's name read aloud | Done |
| 6m | Learn a format's creatures, spells or lands separately, as MTGGoldfish lists them, without basic lands; chosen on the start screen | Lessons on just the lands, creatures or spells | Done |
| 7 | Refresh the card data automatically once a day | New cards appear without me doing anything | Done |
| 7b | Faster app updates: reload into a new version as soon as it is downloaded, but never during a lesson, and check for one whenever the installed app comes back to the foreground. Today a new version arrives one visit late; card data is not affected | A new version within seconds of opening the app | Done |
| 7c | Keep the card database between daily runs on GitHub, so the 50 artwork searches and the card data are only fetched again when they are 30 days old | Fewer requests to Scryfall | Done |
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
