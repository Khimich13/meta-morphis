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
  `formats.json`, which lists what exists. It also writes every card, for
  the player's own lists, in `cards/`: an index of the names, and the
  cards in 256 files by the first two characters of their oracle id, so a
  phone loads only the files of the cards it adds. A card's file never
  changes, as its oracle id doesn't. Cards printed only in joke sets are
  left out.
- **The data refreshes once a day** on GitHub Actions, at 19:17 UTC, about an
  hour after MTGGoldfish was seen to update its lists.
- **Scryfall's card data comes from its file of every printing** ("Default
  cards" bulk data), not from looking cards up one by one: Scryfall asks for
  its bulk files when many cards are looked up, and they have no rate
  limit. It is downloaded only when Scryfall has made a newer one, and kept
  between runs. If the download fails the last copy is used, and after a
  week of that the run is marked as failed, so GitHub reports it. A name on
  a list must match a card's name exactly, ignoring case and accents: its
  full name first, then a front face, then another face.
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
- **Two kinds of question about the name:** a card's artwork alone, or its full picture with
  the name painted over by the title bar around it, the mana cost still
  showing, and painted over in the text box too. The second is asked only
  about a card with one name on one side, in English. A saga, class or
  case counts: its title bar is a normal card's, and its text is read
  beside its artwork, with its type line when that has a word of the
  name (Urza's Saga). So does a planeswalker in the modern frame: its
  title bar, thinner and higher, has its own measures, and its type
  line, which nearly always names it ("— Teferi"), is read with its
  text, always. Its type must be found there and covered, or the card is
  left out: a short one like "Ral" read badly would show. So does a
  transform card, by either side: each shows only its own name and
  text. The front's name starts after an icon; the back's after one
  too, or, when the icon sits on the right where a mana cost would be,
  where a normal card's starts. So does a modal double-faced card, by
  either side: the strip at its bottom left shows the other side's type
  and mana cost or ability, never its name, and both sides' names start
  after an icon. An adventure or a prepare card does, by
  each part: see below. A card that can be asked both ways gets
  either, half the time each.
- **A card can be asked its mana cost too,** a third kind of question,
  as often as each of the others, and sharing the card's one level with
  them: its full picture with the cost painted over the same way and
  the name in sight, and four costs to choose from, drawn with
  Scryfall's symbol pictures. The wrong ones are near the right one:
  one generic mana more or less, one more or one fewer of a symbol it
  has, or one swapped for a generic mana or the other way round. Every
  kind of symbol stays at least once: the frame shows the colors. Asked
  for now only of a card with one side and one cost, in a frame whose
  title bar is measured. The cost is covered a little wider than
  measured, and the 1997 frame's symbols were measured again for it:
  see COST_AREAS in `export.py`.
- **A creature can be asked its power and toughness too,** the same
  way: as often as each of the other kinds, sharing the card's one
  level, its full picture with the two painted over in their box at the
  bottom right, and four answers to choose from. The answers are the
  corners of a square: the card's own, the power one more or one less,
  the toughness one more or one less, and both - a 2/2 offers 2/2, 3/2,
  2/3 and 3/3, or another square around it. Each shares a number with
  two others, so none stands out; answers all around the card's own
  would give it away as the one in the middle. Never below 0, and a
  toughness of 0 only on a card that has it. Asked for now only of a
  card with one side, or an adventure's or prepare card's main part, in
  the modern or 2003 frame, whose box was measured (see
  POWER_TOUGHNESS_BOXES in `export.py`), and only when both are whole
  numbers - not Tarmogoyf's */1+*. The older frames print them on the
  frame itself, with no box to paint them over with. A spacecraft
  prints them in its text box, and isn't asked.
- **A double-faced card is asked by either side,** half the time each:
  by its back's artwork, as by its front's, and a transform or modal
  double-faced card's by its back's full picture too. The answers name
  one side each: the side asked for the card itself, either side for a
  wrong answer, so a back's name never tells the right one apart. After the
  answer the card shows the side asked first; the other is a flip away.
- **An adventure or a prepare card is asked by either part,** half the
  time each: its main part, as any card, or the second, smaller spell
  printed on it (Petty Theft on Brazen Borrower), by its full picture
  only - the artwork is the main part's. One part is asked at a time,
  with the other's name left in sight. The spell's name is covered in its
  own small title bar, measured on the six on the lists on 2026-11-16 -
  on the left on an adventure (an omen too), on the right on a prepare
  card - and the text box is read for each part's name, its own half
  first. The answers name one part each, as a double-faced card's name
  one side: the part asked for the card itself, either part for a wrong
  answer.
- **A split card printed sideways is asked by either half,** half the
  time each (Wear // Tear, the Rooms), in the modern frame: by its half
  of the artwork, which Scryfall crops with both side by side and the
  app cuts in two, or by its full picture with its name covered and the
  other half's left in sight. Each name bar runs up the card's left
  side, measured on 2026-11-16 on Wear // Tear and Unholy Annex //
  Ritual Chamber, the only ones on the lists; a split card without fuse
  isn't measured, so its halves are asked by their artwork only. The
  name is painted along its own line, as it reads. The answers name one
  half each, as for a part above. An aftermath card keeps being asked
  whole. Turning the phone sideways during the question opens the card
  in the large view the right way up, its name still covered, as the
  answer card does after it.
- **The artwork comes from Scryfall,** cut out by them, except where
  their cut catches text around it: then the app cuts it from the card's
  large picture itself, at the measured art box. Only Summon: Esper
  Maduin, as of 2026-11-15, when every card's cut was compared with its
  art box; it is named in the code, not found by its kind. Its name is
  shown without "Summon:" too, which read oddly and was the only one on
  the lists: the word alone told it apart.
- **The name in the text box is found by reading the picture** with
  Tesseract, once per printing, whenever it may be printed there: in the
  Oracle or flavor text, a word of it alone in the flavor text ("Lórien"
  on Lórien Revealed), as "this creature" and the like on a printing
  older than Foundations or a reprint (which may print the name instead),
  or as an old creature's "Summon" type line. A keyword's reminder text
  doesn't count: it says "this card" on every printing. A word of the
  name standing alone is left in sight when it is a subtype from
  Scryfall's lists ("a Goblin card"), or when the card's own Oracle text
  uses it, or its plural, apart from the name ("a card from a graveyard"
  on Graveyard Trespasser, "cards from graveyards" on Graveyard Glutton,
  though not in an ability's name like "Wasp's Sting"): a word of the
  rules tells nothing of which card it is. Any other is covered,
  up to three: a place or a person, like
  "Locthwain's" in a flavor text, gives the answer away. So is a word
  that only starts like one of the name's: "coastline" on Stormcarved
  Coast. A word of the card's own Oracle text that is no word or piece of
  the name is plain text, never the name read badly: "can't" on Orim's
  Chant. A reading that leaves anything else like a word of the name -
  run together, broken at a line's end, or with a piece of the name next
  to it - or reads the text poorly, leaves the card to its artwork: a
  missed name gives the answer away. A picture is read enlarged and in color first; when that
  leaves the card out, it is read again in grayscale at its own size,
  which reads the textured text box of an old frame far better and a few
  other cards worse - so it only gets the cards the first reading gave up
  on. What was read is kept in git, as the first reading of many cards
  takes hours. The app paints over the name there from the paper just
  above and below it, which leaves out the print and the box's border.
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
