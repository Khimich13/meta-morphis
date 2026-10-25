# Decisions and rules

The choices that shape the project, and the rules it has to follow. What's
next is in the [issues](https://github.com/Khimich13/meta-morphis/issues);
what has been done is in the commit history.

## How the project is built

- **Two halves, a set of files between them.** Python fetches the data and
  writes a JSON file for each list of cards. The app reads those files and
  loads card pictures from Scryfall's image servers. The app never calls
  Scryfall's API or MTGGoldfish itself, so its users can never overload them.
- **The exporter is one module,** `meta_morphis/export.py`. It writes one
  file per format and list (`pauper.json`, `pauper-lands.json`, …) and
  `formats.json`, which lists what exists.
- **The data refreshes once a day** on GitHub Actions, at 19:17 UTC, about an
  hour after MTGGoldfish was seen to update its lists. The card database is
  kept between runs, so Scryfall data is only fetched again after 30 days.
- **One list failing doesn't stop the others.** It keeps its previous file,
  the other lists are published, and the run is then marked as failed, so
  GitHub reports it. A list older than three days fails on purpose, rather
  than being published again unchanged.
- **The app is React, TypeScript and Vite,** in `web/`. It is a progressive
  web app: installable, and usable offline once a list has been opened.
- **Hosting is GitHub Pages,** free for a public repository.
- **Progress is saved on the device,** in the browser's storage, under each
  card's Scryfall `oracle_id`, which stays the same across reprints. So what
  a player knows about a card counts in every format and list it appears in.
- **Cards come back by how well they're known** (Leitner boxes): a right
  first answer makes a card wait longer before it is asked again, a wrong one
  brings it back in the next lesson.
- **Each card is shown in its most familiar printing:** the artwork that
  appears on the most regular paper printings, in its newest printing. The
  question and the full card after answering always show the same printing.
- **From MTGGoldfish, only the lists of cards are used:** not their rank,
  deck percentages or copy counts. Basic lands are left out of every list.

## Rules to follow

- **Show the fan-content notice** in the app, word for word, as the
  [Wizards of the Coast Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy)
  requires.
- **Keep it free, with no required sign-up.** Both Wizards of the Coast and
  Scryfall require this.
- **Never alter card pictures:** no covering, cropping, dimming or stretching.
  Buttons may sit over the artwork, but never over the artist name or the
  copyright at the bottom of a card. When the artwork is shown on its own,
  credit the artist next to it. These are
  [Scryfall's rules](https://scryfall.com/docs/api).
- **Stay within Scryfall's rate limit** of 2 requests per second, and wait 30
  seconds after being told to slow down. The backend does both.
- **Don't share the app publicly yet.** MTGGoldfish's terms allow personal use
  only. Before a public launch, either get their permission or compute the
  lists from tournament decklists instead (issue #27).
