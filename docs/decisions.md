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
  answer makes a card wait longer before it is asked again, a wrong one moves
  it back a step and brings it back the next day. Only a card's first answer
  each day counts.
- **Two kinds of question:** a card's artwork alone, or its full picture with
  the name painted over by the title bar around it, the mana cost still
  showing, and painted over in the text box too. The second is asked only
  about a card with one name on one side, in English, not a planeswalker
  (its title bar has another shape). A card that can be asked both ways
  gets either, half the time each.
- **The name in the text box is found by reading the picture** with
  Tesseract, once per printing, whenever it may be printed there: in the
  Oracle or flavor text, as "this creature" and the like on a printing
  older than Foundations or a reprint (which may print the name instead),
  or as an old creature's "Summon" type line. A keyword's reminder text
  doesn't count: it says "this card" on every printing. A reading that
  leaves anything like a word of the name uncovered, or reads the text
  poorly, leaves the card to its artwork: a missed name gives the answer
  away. What was read is kept in git, as the first reading of many cards
  takes hours. The app doesn't paint over the text box yet: until it does,
  a card with its name there is asked only by its artwork.
- **Each card is shown in its most familiar printing:** the artwork that
  appears on the most regular English paper printings, in its newest
  printing. The question and the full card after answering always show the
  same printing.
- **From MTGGoldfish, only the lists of cards are used:** not their rank,
  deck percentages or copy counts. Basic lands are left out of every list.

## Rules to follow

- **Show the fan-content notice** in the app, word for word, as the
  [Wizards of the Coast Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy)
  requires.
- **Free to use in full, with no required sign-up.** Every card, list and
  quiz stays free for everyone; both Wizards of the Coast and Scryfall
  require this. Income may come only from donations, ads, sponsors,
  affiliate links and supporter perks that hide no content (no ads, themes,
  a badge). Ads never cover a card.
  A paid app or subscription would need Wizards' written permission.
- **Follow [Scryfall's rules for card pictures](https://scryfall.com/docs/api):**
  - never cover, crop or clip off the artist name or the copyright;
  - never distort, skew or stretch a picture;
  - never blur, sharpen, desaturate or color-shift it;
  - never add watermarks, stamps or logos to it;
  - never show a card as if someone other than Wizards of the Coast made
    it, or as if it were from another game;
  - when the artwork is shown on its own, name the artist and the copyright
    next to it.

  So buttons may sit over the artwork, and a question may hide the card's
  name under a layer painted from the title bar around it, never drawn
  into the picture itself. Turning a card printed sideways the right
  way up is fine too: the picture itself stays as it is, and Scryfall's
  own site has a button for it.
- **Stay within Scryfall's rate limit** of 2 requests per second, and wait 30
  seconds after being told to slow down. The backend does both.
- **Don't share the app publicly yet.** MTGGoldfish's terms allow personal use
  only. Before a public launch, either get their permission or compute the
  lists from tournament decklists instead (issue #27).
