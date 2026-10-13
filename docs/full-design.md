# meta-morphis PWA — full design (reference)

> **Background research, not the plan.** The current plan is [PLAN.md](PLAN.md), and it wins wherever the two disagree.
> This document is the full design written on 2026-10-06 for a polished public product. It is kept as a reference to look details up in: API rules, legal findings, phone behavior, data shapes, later features. Nothing in it is built unless a brick in PLAN.md asks for it.

---

## Context

`meta-morphis` is a Python library and CLI. It scrapes MTGGoldfish "format staples" (the top 50 cards per format) and caches Scryfall card data in SQLite. The goal is a Duolingo-style PWA (iPhone, Android, desktop) that teaches those 50 cards. Each question shows a card with one fact missing, and the user picks the answer.

There is no HTTP API and no frontend yet. `pwa/data/*.json` are empty placeholders. This plan settles every major decision, the data contracts, the backend and frontend structure, the quiz engine, testing, the roadmap and the risks.

**Answers you gave:** mostly Python and little JS → Svelte at first, **changed to React on 2026-10-13** (see decision 3). Audience is **you + friends first**. **No hearts.**

**Assumptions (correct me if any is wrong):**
- No accounts in the MVP; progress stays on the device and is designed to sync later.
- Free and English only.
- Offline after the first load, installable.
- One maintainer.
- No app-store builds yet.
- MVP format: **Pauper**.
- Hosting at `https://khimich13.github.io/meta-morphis/`. The repo is public and Pages is not enabled yet; both verified.
- Sizes: **S** ≤ 1 day, **M** 2–5 days, **L** 1–2+ weeks of solo work.

---

## ⚠️ Legal and terms findings (read first)

| Source | What it says (verified 2026-10-06) | Effect on this plan |
|---|---|---|
| **MTGGoldfish Terms of Use** | "intended solely for personal, non-commercial use… You may not reproduce…, publish, transmit, distribute, display, modify, create derivative works from… any of the contents". robots.txt does **not** disallow `/format-staples/` and has no crawl-delay. | **Not a blocker for a private MVP. It is a blocker for any public launch.** A GitHub Pages URL can be reached by anyone, so "friends only" is only privacy by obscurity. Before sharing widely, get written permission or switch to the planned replacement source (§9a). Packs publish only the card list for now, with attribution (decided 2026-10-10). Rank, deck % and copy counts are optional in the format and switched off (decision 11). |
| **Scryfall API terms** | Data is free "for the primary purpose of creating additional Magic software". You may not paywall it. You "may not use Scryfall data to create new games". You may not "simply repackage, republish, or proxy". | Fine. The app is a study tool about Magic cards, and it adds value: packs carry about 5% of Scryfall's fields, reshaped for quizzes. |
| **Scryfall image rules** | "Do not cover, crop, or clip off the copyright or artist name". No distort, blur, desaturate or color-shift. No watermarks. `art_crop` requires listing the artist and copyright in the same interface. | **We never draw over card images** (decision 5). UI rule: never apply CSS `filter`, `opacity` dimming or stretching to a card image. |
| **Scryfall rate limits** | `/cards/collection`, `/cards/named` and `/cards/search` allow **2 requests/second**. A 429 locks the client out for 30 s. `*.scryfall.io` has no limits. The User-Agent must be `AppName/version`. | **The current backend breaks this.** `request_with_retries` paces at `min_delay=0.2` (5 req/s), and on a 429 it retries after 0.5 s and 1 s, inside the lockout. Fixing this is Phase 0.1. |
| **WotC Fan Content Policy** (updated 2017-11-15) | It must be free: no "payments, surveys, downloads, subscriptions, or email registration". The notice is required word for word. "Don't use Wizards' IP in other games… regardless of whether it is distributed for free." | Accounts must stay **optional forever**. The notice goes on About and onboarding. On the "games" clause: it targets putting Magic IP into a *different* game. Scryfall, itself fan content under this policy, runs an "Art Game" built on the same idea. Risk is low; we frame the app as a trainer and add no non-Magic game mechanics. |

---

## 1. Summary and decisions

| # | Decision | Choice | Why | Rejected |
|---|---|---|---|---|
| 1 | Data delivery | **Static, versioned JSON packs**, written by a new Python exporter in a daily GitHub Actions job and served by GitHub Pages | Data changes at most daily and is the same for every user. An offline-first app needs a downloadable bundle anyway. No server, no cost, and user traffic can never reach Goldfish or Scryfall. | (b) Thin API: needs a host and uptime, with no benefit until sync exists. (c) Hybrid: later, only when optional sync arrives (static packs + a small sync API). |
| 2 | Question generation | **On the client**, from pack data, with a seeded RNG. **Text features are precomputed in Python**: segmented oracle text, self-name redaction, cloze candidates. | Questions can adapt to SRS state, variety is unlimited, and the payload stays small. Tests are deterministic through the seed. The text-processing work lands in Python, where you're strongest, and is tested with pytest. | A pre-generated `quizzes.json`: a fixed set that repeats, can't adapt to the learner, and is bigger. |
| 3 | Frontend | **React 19.3 + Vite 8.3 + TypeScript 6.0.3**, single-page app (changed from Svelte on 2026-10-13). **react-router 8.4** with a hash router, **vite-plugin-pwa 2.0** (Workbox 7.4, `generateSW`), **Dexie 4.4**. Plain CSS files with design tokens and the system font stack. | React has the largest ecosystem and the most learning material, and it is the most widely used front-end library. Hash routes need no server rewrites on Pages and work inside Capacitor later. | **Svelte 5**: the first choice, easier to learn and about 55 KB smaller compressed, but with a much smaller ecosystem. **Next.js and other React frameworks**: add server rendering concepts with no benefit for a 7-screen offline SPA. **Vue**: a smaller ecosystem than React. **TypeScript 7**: very new on 2026-10-06 and not yet tried with this setup. **Tailwind**: another language to learn. |
| 4 | Progress | IndexedDB through Dexie. An **append-only review event log** plus **derived per-item Leitner state**. Items are keyed `card:<oracle_id>:<facet>`, or `<format>:<oracle_id>:<facet>` for meta facets. | `oracle_id` is stable across printings. Knowing a card's cost carries over between formats. Sync later means uploading events and replaying them. | localStorage (synchronous, small). Name-based keys (renames, aliases). |
| 5 | Images and hiding info | Hotlink `cards.scryfall.io` (webp `grid` and `art`). **Questions use our own text-rendered card** with a blank slot. Art questions use the `art` crop with an "Illustrated by X · © Wizards of the Coast" caption. The full card image appears **unaltered** on intro, reveal and card detail. The service worker caches images CacheFirst over CORS, plus an explicit "Download for offline" step. | Follows the image rules. Works for every layout and frame. Verified: both CDNs send `access-control-allow-origin: *` and `max-age` of one year, so cached responses are non-opaque with no quota padding. About 100 KB per card, roughly 5 MB per format. | **Masking regions of the real image**: frame positions vary across old, modern, showcase, split and saga frames, and covering the image is close to the legal-notice rules. **Self-hosting images**: Pages bandwidth, looks like republishing, and scans go stale. |
| 6 | Hosting and updates | **GitHub Pages via Actions**, deployed on push, on a daily cron and on demand. `data/manifest.json` is NetworkFirst. Packs and symbols have hash-named, immutable filenames. The app shell is precached, with an update toast. | No new accounts or cost. The repo is already public on GitHub. | Cloudflare Pages: custom headers are nice, but it needs a new account and token; move there if needed. Committing data to git: noisy history. |
| 7 | Spaced repetition | **Leitner, 6 boxes**, due dates stored as local `YYYY-MM-DD` | Multiple choice has a 25–50% guess floor, so a "correct" answer is weak evidence and FSRS's recall model would be noisy. At about 250 items per format there is nothing to optimize. Leitner is easy to explain and to test. The event log lets us switch to `ts-fsrs` 5.4 later by replaying history. | FSRS now. |
| 8 | Mistakes | **No hearts.** A wrong item is re-asked once at the end of the lesson and goes into review. | Your choice. | Hearts. |
| 9 | Symbols | Scryfall `/symbology`: `svg_uri` on `svgs.scryfall.io` (CORS `*`, cached), with the `english` field as `aria-label`. Exported as `symbols.<hash>.json`. | Official artwork and accessible names. | `mana-font` 1.18.0: last published 2024-11 and has no alt text. |
| 10 | Pauper list | Change `config.GOLDFISH_FORMAT_URLS["pauper"]` from `/full/spells` to **`/full/all`** | Verified today: `/spells` leaves out creatures. Eleven of the `/all` top 50 are missing, including Guttersnipe, Baleful Strix and Writhing Chrysalis. `/all` has no lands, which matches the other formats. | Keeping `/spells`. |
| 11 | Meta data in packs | **None for now** (decided 2026-10-10): no rank, deck % or copy counts. The pack format has an optional `meta` object and the exporter has `EXPORT_META_FIELDS = ()`, so any of them can be switched on later without a new format version. | Simpler exporter with no pairing step. Publishes the least MTGGoldfish content: only which 50 cards. Packs change only when a card enters or leaves the list. Cost: cards are taught in a per-device shuffled order, not most-played first. | Rank only (better teaching order, a little more exposure). All three values (enables two more question types, most exposure). |

**Where your framing changes:**
- Lighthouse 12 **removed the PWA category**, so PWA checks become Playwright assertions (§7).
- Rarity, set, artist, flavor and colors questions are **dropped** (§6).
- Some facts are binary (instant vs. sorcery, "which is played more"), so not every question has 4 options.
- Production formats (build the mana cost, type the name) arrive in Phase 3.

---

## 2. Architecture

```
 GitHub Actions deploy.yml — cron "17 6 * * *" · push to main · workflow_dispatch
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │ restore data/cards.db (actions/cache)     curl live /data/* → web/public/data │
 │                                            (last-known-good fallback)         │
 │ MTGGoldfish ──1 req/format/day──► meta/ (24h cache) ─────┐                    │
 │ api.scryfall.com collection/named @≤2 req/s ─► scryfall/ (30d cache, stale ok)│
 │ api.scryfall.com/symbology (1 req) ──────────────────────┤                    │
 │                                       SQLite data/cards.db                    │
 │                                               ▼                               │
 │            python -m meta_morphis.export  (build → hash → write)              │
 │                                               ▼                               │
 │   web/public/data/manifest.json · packs/<fmt>.<sha12>.json · symbols.<sha12>.json
 │                                               ▼                               │
 │                       vite build → web/dist → actions/deploy-pages            │
 └───────────────────────────────────────────────────────────────────────────────┘
                                   ▼
           GitHub Pages  https://khimich13.github.io/meta-morphis/
                                   ▼
 Service worker (Workbox)                         cards.scryfall.io · svgs.scryfall.io
  ├ precache: app shell (hashed JS/CSS, index.html, icons) — data/** excluded
  ├ NetworkFirst 3 s: data/manifest.json
  ├ CacheFirst: data/packs/*, data/symbols.*        ◄─ CacheFirst, CORS, statuses [200]
                                   ▼
 React app:  pack loader (sha256 check) → reconcile → lesson composer → generators
                                   ▼
 IndexedDB (Dexie): reviews (event log) → items (Leitner projection) · lessons · kv
```

Rule: **the browser never calls `api.scryfall.com` or Goldfish.** It only reads static files and the image/SVG CDNs.

---

## 3. Data contracts

The JSON Schemas in `schema/` at the repo root are the source of truth: `manifest.schema.json`, `pack.schema.json`, `symbols.schema.json`. pytest validates exporter output against them, and Vitest validates the shared fixture against them. The TypeScript types in `web/src/lib/data/types.ts` mirror them. Every file carries an integer `schema` field. The client refuses packs whose `schema` is newer than it supports and shows "Update the app".

**Hash stability:** packs contain **no timestamps**. Timestamps live only in the manifest. Unchanged content therefore keeps the same hash, and clients don't re-download.

### `data/manifest.json` (mutable, NetworkFirst, fetched with `cache: 'no-cache'`)
```json
{
  "schema": 1,
  "generated_at": "2026-10-07T06:19:42Z",
  "symbols": { "path": "symbols.5b0e19c2d4aa.json", "sha256": "5b0e19c2d4aa…64hex" },
  "formats": {
    "pauper": {
      "label": "Pauper",
      "path": "packs/pauper.9f2c41d07ab3.json",
      "sha256": "9f2c41d07ab3…64hex",
      "bytes": 48211,
      "card_count": 50,
      "meta_scraped_at": "2026-10-07T06:18:40Z",
      "stale": false
    }
  }
}
```
`stale: true` means the exporter fell back: Goldfish data older than 48 h, or this format failed and the previous pack was carried forward. The UI then shows "Meta data as of <date>".

### `data/packs/<format>.<sha256[:12]>.json` (immutable)
```jsonc
{
  "schema": 1,
  "format": "pauper",
  "source": { "meta": "MTGGoldfish", "meta_url": "https://www.mtggoldfish.com/format-staples/pauper/full/all", "cards": "Scryfall" },
  "cards": [ /* PackCard, sorted by name; by rank once meta.rank is published */ ]
}
```
**PackCard** fields:
- `oracle_id`, `scryfall_id` (the printing used for images), `name` (display name, from `Card.name`, which comes from the raw JSON)
- `layout`, `cmc`, `color_identity[]`, `keywords[]`, `scryfall_uri`
- `meta` (**optional, not published for now**): `{ rank?, decks_pct?: int, avg_copies?: float }`. The exporter writes only the fields named in `config.EXPORT_META_FIELDS`, and leaves the whole object out while that is empty. The app must work without it.
- `faces[]`: one entry for single-faced cards
- `sides[]`: physical images. 2 for transform/MDFC; 1 for normal, split, adventure and flip.
- `name_tokens[]`: used for redaction and leak checks

**PackFace** fields:
- `name`, `mana_cost` (`""` when none), `type_line`, `colors[]`
- `power`, `toughness`, `loyalty`, `defense` (string or null)
- `text`: lossless segments. Concatenating every `t` reproduces `oracle_text` exactly (a tested invariant). `k` is one of:
  - `self`: a self-reference, shown as "this card" when the name is hidden
  - `reminder`: shown in italics; never a cloze
  - a cloze class: `number`, `verb`, `card_type`, `zone`, `color`, `keyword`

  A token becomes a cloze only if it appears exactly once in the face's non-reminder text, so the answer can't leak elsewhere in the text. Segments avoid offsets on purpose: Python code-point offsets and JS UTF-16 offsets disagree.

**PackSide** fields: `card` (`grid` webp URL), `card_fallback` (`normal` jpg), `art` (`art` webp), `artist`.

**Example: normal card** (Pauper, real values from the cache)
```json
{
  "oracle_id": "b94c0336-2ca8-4bb1-bb1f-e9babd1826ad",
  "scryfall_id": "4c9c9b16-5567-4473-95e6-622292f77336",
  "name": "Hydroblast", "layout": "normal", "cmc": 1, "color_identity": ["U"], "keywords": [],
  "scryfall_uri": "https://scryfall.com/card/ema/55/hydroblast",
  "name_tokens": ["Hydroblast"],
  "faces": [{
    "name": "Hydroblast", "mana_cost": "{U}", "type_line": "Instant", "colors": ["U"],
    "power": null, "toughness": null, "loyalty": null, "defense": null,
    "text": [
      {"t": "Choose "}, {"t": "one", "k": "number"}, {"t": " —\n• "},
      {"t": "Counter", "k": "verb"}, {"t": " target "}, {"t": "spell", "k": "card_type"},
      {"t": " if it's red.\n• "}, {"t": "Destroy", "k": "verb"}, {"t": " target "},
      {"t": "permanent", "k": "card_type"}, {"t": " if it's red."}
    ]
  }],
  "sides": [{
    "card": "https://cards.scryfall.io/grid/front/4/c/4c9c9b16-5567-4473-95e6-622292f77336.webp?1783937613",
    "card_fallback": "https://cards.scryfall.io/normal/front/4/c/4c9c9b16-5567-4473-95e6-622292f77336.jpg?1783937613",
    "art": "https://cards.scryfall.io/art/front/4/c/4c9c9b16-5567-4473-95e6-622292f77336.webp?1783937613",
    "artist": "Lake Hurwitz"
  }]
}
```
"red" appears twice, so it is not a cloze candidate.

**Example: double-faced card** (Pioneer; text segments shortened here)
```json
{
  "oracle_id": "c0957e5e-c71b-439c-931c-9f55d2f76ace",
  "scryfall_id": "24c0d87b-0049-4beb-b9cb-6f813b7aa7dc",
  "name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki", "layout": "transform",
  "cmc": 3, "color_identity": ["R"], "keywords": ["Transform", "Treasure"],
  "scryfall_uri": "https://scryfall.com/card/neo/141/fable-of-the-mirror-breaker-reflection-of-kiki-jiki",
  "name_tokens": ["Fable of the Mirror-Breaker // Reflection of Kiki-Jiki", "Fable of the Mirror-Breaker", "Reflection of Kiki-Jiki"],
  "faces": [
    { "name": "Fable of the Mirror-Breaker", "mana_cost": "{2}{R}", "type_line": "Enchantment — Saga", "colors": ["R"],
      "power": null, "toughness": null, "loyalty": null, "defense": null,
      "text": [ {"t": "(As this Saga enters and after your draw step, add a lore counter.)", "k": "reminder"},
                {"t": "\nI — Create a 2/2 "}, {"t": "red", "k": "color"}, {"t": " Goblin Shaman creature token with …"},
                {"t": "\nII — You may "}, {"t": "discard", "k": "verb"}, {"t": " up to "}, {"t": "two", "k": "number"}, {"t": " cards. …"} ] },
    { "name": "Reflection of Kiki-Jiki", "mana_cost": "", "type_line": "Enchantment Creature — Goblin Shaman", "colors": ["R"],
      "power": "2", "toughness": "2", "loyalty": null, "defense": null,
      "text": [ {"t": "{1}, {T}: Create a token that's a copy of another target nonlegendary creature you control, except it has haste. …"} ] }
  ],
  "sides": [
    { "card": "https://cards.scryfall.io/grid/front/2/4/24c0d87b-0049-4beb-b9cb-6f813b7aa7dc.webp?1783923875",
      "card_fallback": "https://cards.scryfall.io/normal/front/2/4/24c0d87b-0049-4beb-b9cb-6f813b7aa7dc.jpg?1783923875",
      "art": "https://cards.scryfall.io/art/front/2/4/24c0d87b-0049-4beb-b9cb-6f813b7aa7dc.webp?1783923875", "artist": "Joseph Meehan" },
    { "card": "https://cards.scryfall.io/grid/back/2/4/24c0d87b-0049-4beb-b9cb-6f813b7aa7dc.webp?1783923875",
      "card_fallback": "https://cards.scryfall.io/normal/back/2/4/24c0d87b-0049-4beb-b9cb-6f813b7aa7dc.jpg?1783923875",
      "art": "https://cards.scryfall.io/art/back/2/4/24c0d87b-0049-4beb-b9cb-6f813b7aa7dc.webp?1783923875", "artist": "Joseph Meehan" }
  ]
}
```

### `data/symbols.<sha12>.json`
Contains only the symbols used by any pack:
```json
{ "schema": 1, "symbols": { "{U}": {"svg": "https://svgs.scryfall.io/card-symbols/U.svg", "english": "one blue mana"}, "{T}": {"svg": "…/T.svg", "english": "tap this permanent"} } }
```

### Client store: Dexie database `meta-morphis`, version 1
```ts
db.version(1).stores({
  items:   'id, oracleId, format, dueDate, box',           // derived state (rebuildable from reviews)
  reviews: 'id, ts, itemId, lessonId, localDate',          // append-only event log — the sync unit
  lessons: 'id, localDate, format, completedAt',
  kv:      'key'                                           // settings, deviceId, activeFormat, appliedPack:<fmt>, unlockedUnit:<fmt>
});
```
- **Item**:
  ```ts
  { id: 'card:<oid>:mana_cost' | 'pauper:<oid>:meta_copies', oracleId, facet,
    format: string|null, box: 0..5, dueDate: 'YYYY-MM-DD', introducedAt, lastReviewedAt,
    reviews, lapses, answerKey?: string /* meta facets only */, nameSeen: string }
  ```
- **Review event**:
  ```ts
  { id: uuidv7, deviceId, ts, localDate, itemId, oracleId, facet, format, questionType,
    optionCount, correct, firstTry, latencyMs, lessonId, packSha, appVersion }
  ```
- **Lesson**: `{ id, format, seed, startedAt, completedAt, localDate, xp, correctFirstTry, total }`
- Whether an item is schedulable is **computed, never stored**: its `oracleId` is in the active pack, and its `format` is null or equal to the active format. Cards that leave the meta therefore need no writes.

Future sync uploads `reviews` with ids greater than the last cursor and pulls other devices' events. `items` is rebuilt with `rebuildItems(reviews)`. Schema bumps follow the same discipline as `SCHEMA_VERSION`: a new `db.version(n).upgrade()` block each time.

---

## 4. Backend changes, file by file

All new Python follows the existing patterns:
- client / repo / service layering
- mypy strict
- `RequestUnavailable` means "unknown, retry later"; `None` means "confirmed miss"
- pytest using the `conn` and `db_file` fixtures in `tests/conftest.py`

The CLI in `main.py` keeps working unchanged.

**Phase 0 (required)**
1. `meta_morphis/config.py`
   - Pauper URL → `/full/all`.
   - `SCRYFALL_HEADERS["User-Agent"] = "meta-morphis/0.1.0 (+https://github.com/Khimich13/meta-morphis)"`.
   - Add `SCRYFALL_MIN_DELAY = 0.5`, `SCRYFALL_RATE_LIMIT_COOLDOWN = 30.0`, `SCRYFALL_SYMBOLOGY_URL`, `EXPORT_MIN_CARDS = 45`, `EXPORT_STALE_AFTER = 2 * _DAY`, `EXPORT_META_FIELDS: tuple[str, ...] = ()` (which of `rank`, `decks_pct`, `avg_copies` to publish; empty for now).
2. `meta_morphis/utils/http.py`: new parameter `default_retry_after: float | None = None` on `request_with_retries`, used when a 429 has no `Retry-After`. It is clamped by the existing `max_retry_after`. Defaults are unchanged, so existing tests still pass.
3. `meta_morphis/scryfall/client.py`
   - `fetch_batch` and `fetch_single` pass `min_delay=config.SCRYFALL_MIN_DELAY, default_retry_after=config.SCRYFALL_RATE_LIMIT_COOLDOWN`.
   - Add `fetch_symbology() -> dict[str, Any] | None`, reusing `_parse_json`.
4. `meta_morphis/models/card.py` and `card_face.py`
   - Add **defaulted** typed fields, parsed with `.get` in `from_raw`. Existing constructor calls and the KeyError-means-malformed behavior stay the same.
     - `Card`: `oracle_id`, `layout`, `cmc`, `color_identity`, `keywords`, `scryfall_uri`, `image_uris`.
     - `CardFace`: `oracle_text`, `power`, `toughness`, `loyalty`, `defense`, `colors`, `artist`, `image_uris`.
   - Add `Card.gameplay_faces() -> list[CardFace]`, which builds one face for single-faced cards, and `Card.image_sides()`, which reads face images for transform/MDFC and top-level images otherwise.
   - This follows the earlier audit's advice to read `raw` only inside `from_raw`.
5. `meta_morphis/meta/repo.py`: add `get_meta_timestamp(conn, format_name) -> int | None`. It reads `meta_refresh` and feeds `meta_scraped_at` and `stale`.
6. **New `meta_morphis/export/`:**
   - `schema.py`: TypedDicts `Manifest`, `ManifestFormat`, `Pack`, `PackCard`, `PackFace`, `PackSide`, `TextSegment`, plus `PACK_SCHEMA_VERSION = 1`.
   - `text.py` (pure functions):
     - `name_tokens(card)`: the full name, each face name, and the short name of a legendary ("Sheoldred, the Apocalypse" → "Sheoldred").
     - `segment_text(oracle_text, tokens, keywords) -> list[TextSegment]`: finds reminder parentheses, self-references (whole word, longest first), and cloze candidates from fixed word lists. Candidates must appear exactly once.
   - `build.py`: `build_card(card: Card, entry: MetaEntry | None = None) -> PackCard`, which adds `meta` only when an entry is passed, and `build_pack(format_name, cards) -> Pack`, which dedupes by `oracle_id` and sorts by name.
   - `writer.py`:
     - `canonical_json(obj) -> bytes`: `sort_keys`, compact separators, `ensure_ascii=False`.
     - `write_pack(out_dir, pack) -> ManifestFormat`: sha256, filename `<fmt>.<sha12>.json`, temp file then `os.replace`.
     - `write_symbols`, `write_manifest`, `load_previous_manifest(out_dir)`, `prune(out_dir, keep)`.
   - `service.py`:
     - **Not built now; this is the step to add when `EXPORT_META_FIELDS` is first set.** While no meta data is published, the exporter writes the cards `fetch_cards` returns and quirk 2 doesn't arise.
       `pair_meta_with_cards(conn, meta) -> tuple[list[tuple[MetaEntry, Card]], list[MetaEntry]]` **(fixes quirk 2)**. After `fetch_cards` fills the cache, it calls the existing `get_card_from_cache(conn, entry.lookup_name or entry.name)`. That reuses the alias table: face aliases cover Goldfish's "Fable of the Mirror-Breaker" (listed without its back face) and "Unholy Annex // Ritual Chamber" (with `lookup_name`), and the fuzzy aliases from `add_alias` also resolve.
     - `export_formats(conn, formats, out_dir) -> ExportReport`. Per format: `get_meta_cards` → `fetch_cards` → dedupe by `oracle_id` → if fewer than `EXPORT_MIN_CARDS` cards, fail **this format only** and carry forward the previous manifest entry with `stale: true` → build → write. Then write the symbols file (falling back to the previous one) and the manifest.
   - `__main__.py`: argparse `--out`, `--formats` (default: all formats in config), `--fixture-from DIR` (builds the golden fixture from raw JSON files without network access). Exit code 1 only when no format is publishable.
   - **Quirk 1** (`cards.name` holds a normalized key) needs no change. The exporter only reads `Card.name`, the display name from the JSON. Renaming the column to `name_key` stays an optional later cleanup.
   - **Quirk 3** in Phase 0–1: every printing-specific question is dropped (§6). Phase 2 picks a common printing for Pauper (below).
7. `schema/*.schema.json` (new). `pyproject.toml`: add `jsonschema` to the dev group.
8. **Tests:**
   - `tests/export/test_text.py`: segments rebuild the exact oracle text; redaction covers full name, face names and legendary short names; reminder text is never a cloze; tokens that appear twice are excluded.
   - `tests/export/test_build.py`: normal, transform, split (Room), class and planeswalker fixtures.
   - `tests/export/test_writer.py`: same input gives the same hash; atomic replace; previous entry carried forward; prune.
   - `tests/export/test_service.py`: cards deduped by `oracle_id`; no `meta` key in the output while `EXPORT_META_FIELDS` is empty; below-threshold format → stale carry-forward; uses the `conn` fixture and monkeypatched fetchers.
   - `tests/export/test_contract.py`: output validates against the schemas, and the exporter run on `tests/fixtures/scryfall/*.json` equals the committed `web/tests/fixtures/pack.fixture.json` (golden file shared with Vitest).
   - Additions to `tests/utils/test_request_with_retries.py` (`default_retry_after`), `tests/scryfall/test_scryfall_client.py` (pacing arguments passed, symbology) and `tests/models/test_card.py` (new fields, `gameplay_faces`, `image_sides`).
   - Fixture raw JSON for Hydroblast, Fable, Unholy Annex, Stormchaser's Talent, Sheoldred and Graveyard Trespasser, copied from `data/cards.db`.
9. Repo housekeeping: delete the `pwa/` placeholders. In `.gitignore` add `/web/public/data/`, `/web/node_modules/`, `/web/dist/`, `/web/test-results/`.

**Phase 2 (quirk 3, display printing for Pauper):**
- `db/init_db.py`: `SCHEMA_VERSION = 2`, adding `_migrate_to_v2` to create `display_printings(format TEXT, oracle_id TEXT, json TEXT NOT NULL, updated_at INTEGER NOT NULL, PRIMARY KEY(format, oracle_id))`.
- `scryfall/client.py`: `search_cards(query) -> dict | None`, hitting `/cards/search` with `unique=prints&order=released&dir=desc` at ≤ 2 req/s. A 404 means no match, which returns `None`, matching the existing semantics.
- `scryfall/repo.py` and `service.py`: `get_display_printing(conn, format_name, card) -> Card`. Query `oracleid:<id> r:common game:paper`, then `oracleid:<id> r:common` (some commons exist only on MTGO), then fall back to the default printing. Cache for 30 days, reusing the existing stale and failure-cooldown helpers.

**CI workflows:**
- `.github/workflows/ci.yml` (push and PR):
  - Python job: `uv sync --locked`, `uv run pytest`, `uv run mypy .`
  - Web job: `npm ci`, `npm run check` (`tsc`), `npm test` (Vitest), `npm run build`, Playwright on Chromium and WebKit, `lhci autorun`.
- `.github/workflows/deploy.yml` (push to main, cron `17 6 * * *`, `workflow_dispatch`; `permissions: pages: write, id-token: write`; `concurrency: pages`):
  1. `actions/cache/restore data/cards.db` (key `cards-db-${run_id}`, restore-keys `cards-db-`)
  2. `curl` the live `data/manifest.json` and the files it references into `web/public/data` (last-known-good; allowed to fail)
  3. `uv run python -m meta_morphis.export --out web/public/data --formats pauper`
  4. `actions/cache/save`
  5. `npm ci && npm run build` → `upload-pages-artifact web/dist` → `deploy-pages`
  
  One-time setup: Settings → Pages → Source = GitHub Actions.

---

## 5. Frontend

```
web/
  index.html  vite.config.ts  tsconfig.json  package.json  .nvmrc
  playwright.config.ts  lighthouserc.json
  assets/logo.svg                       # source for @vite-pwa/assets-generator (no WotC symbols)
  public/ icons/…  data/ (gitignored, written by the exporter)
  src/
    main.tsx  App.tsx  App.css  routes.tsx
    screens/   Onboarding  Home  Lesson  Results  Progress  CardDetail  Settings  About   (.tsx)
    components/ CardText  ArtPrompt  CardImage  OptionList  ManaCost  OracleText  Symbol
                FeedbackSheet  IntroCard  LessonProgress  StreakBadge  XpBadge  UnitPath
                UpdateToast  InstallHint  OfflineDownload  MetaUpdateBanner
    lib/
      engine/   rng.ts  types.ts  mana.ts  distractors.ts  srs.ts  lesson.ts  scoring.ts
                reconcile.ts  projection.ts
                questionTypes/ index.ts nameFromArt.ts nameFromText.ts manaCost.ts spellSpeed.ts
                               typeLine.ts powerToughness.ts oracleCloze.ts metaCopies.ts metaCompare.ts
      data/     types.ts  pack.ts (manifest/pack fetch + sha256 verify via SubtleCrypto)  db.ts  progress.ts  backup.ts
      platform/ sound.ts  haptics.ts  install.ts  storage.ts  dates.ts (local YYYY-MM-DD via Intl)
      state/    useSettings.ts  usePack.ts  useLesson.ts                # React hooks
    styles/    tokens.css (light/dark custom properties)  global.css
  tests/ unit/  e2e/  fixtures/pack.fixture.json (golden, produced by Python)
```
`lib/engine/` is **pure TypeScript**: no DOM, no React, no Dexie. That keeps it unit-testable.

**Routes** (hash-based; the answer feedback is a sheet inside Lesson, not a route, so the back button behaves):

| Route | Screen |
|---|---|
| `#/welcome` | What the app is, format picker, Fan Content notice. On iOS in a browser tab, a nudge to install first (see storage below). |
| `#/` | Home: unit path (5 units of 10 cards), streak, daily-goal ring, "Start lesson", "Review mistakes (n)", meta-update banner |
| `#/lesson/:mode` | `next`, `review` or `unit/:n` |
| `#/results/:lessonId` | XP, accuracy, cards learned, streak |
| `#/progress` | Mastery grid per card, plus a list of cards that left the meta |
| `#/card/:oracleId` | Full unaltered image(s), facts, artist, Scryfall link |
| `#/settings` | Format, daily goal, sound, haptics, theme, offline download, persisted-storage status, backup export/import, reset |
| `#/about` | Fan Content notice (verbatim), "Card data and images: Scryfall" (no logo), "Meta: MTGGoldfish, <date>", version |

**State flow**
1. Boot: open Dexie → load settings. If there's no `activeFormat`, go to `#/welcome`.
2. `pack.ts` loads the manifest (network with 3 s timeout, else cache) and then the pack (cache-first). It verifies the sha256 and builds an index by `oracle_id`.
3. Lesson: `composeLesson(index, items, today, seed)` → queue of `Question`s (pure).
4. On **Check**: `grade()` → `progress.recordAnswer()` runs one Dexie transaction that appends the review event and updates the item → FeedbackSheet → **Continue**.
5. At the end, write the lesson row → Results.

**Data updates:** on boot, and when the app becomes visible (at most once an hour), refetch the manifest. If a format's sha256 changed:
1. Fetch the new pack and verify it.
2. Hold it as pending, and apply it only between lessons.
3. Run `reconcile()`: meta facets whose answer changed are demoted to box ≤ 1.
4. Show the banner ("+2 new, −2 left the meta").
5. Prefetch any new images.

**App updates:** `registerType: 'prompt'`. `UpdateToast` offers "New version, tap to refresh"; the update also applies on the next cold start.

**Service worker** (vite-plugin-pwa `generateSW`):
- `base: '/meta-morphis/'`
- Precache `globPatterns: ['**/*.{js,css,html,svg,png,webmanifest}']` with `globIgnores: ['data/**']`. Data changes therefore never trigger an SW update.
- `navigateFallback: 'index.html'`

| Resource | Strategy | Cache |
|---|---|---|
| App shell | precache | workbox precache |
| `data/manifest.json` | NetworkFirst, `networkTimeoutSeconds: 3` | `mm-manifest` |
| `data/packs/*`, `data/symbols.*` | CacheFirst (immutable names), maxEntries 30 | `mm-data` |
| `cards.scryfall.io`, `svgs.scryfall.io` | CacheFirst, `cacheableResponse {statuses:[200]}`, maxEntries 1000, maxAge 180 d, `purgeOnQuotaError` | `mm-scryfall` |

Every `<img>` uses `crossorigin="anonymous"` so cached responses are CORS, not opaque. "Download for offline" runs automatically after the format is picked and can be re-run from Settings. It fetches every side's `card` and `art` image plus the used symbols, 4 at a time, with a progress bar; about 5 MB for Pauper. The next question's image is preloaded during the current one.

**Web app manifest:** `id: './'`, `start_url: './#/'`, `scope: './'`, `display: standalone`, theme and background colors, 192/512/maskable icons, and a 180 px `apple-touch-icon`. Viewport uses `viewport-fit=cover`; layout uses `env(safe-area-inset-*)` and `100dvh`.

**Platform facts (iOS 26, late 2026) and how we handle them**
- **Install:** since iOS 26, any site added to the Home Screen opens as a web app by default. iOS has no install prompt event, so `InstallHint` shows "Share → Add to Home Screen" once, after the first lesson. Chromium uses `beforeinstallprompt` behind a custom button.
- **Storage:** Home Screen web apps are exempt from Safari's 7-day deletion of script-written storage. Quota is about 60% of disk. `navigator.storage.persist()` is supported and decided automatically without a prompt. We call it after the first lesson and show the result in Settings.
- **⚠️ Separate storage:** the Home Screen app's storage is separate from Safari's (WebKit bug 181849), so progress made in a Safari tab does **not** follow you into the installed app. Mitigation: nudge installation on iOS at onboarding, and offer backup export/import as a JSON file, which also serves as manual transfer.
- **Notifications:** Web Push works for Home Screen apps since iOS 16.4, and Declarative Web Push since 18.4. Both need a server. The web has **no scheduled local notifications**, so streak reminders wait for Phase 4.
- **Haptics:** iOS doesn't support `navigator.vibrate`. The `<input switch>` workaround was patched in iOS 26.5, so haptics are Android-only and feature-detected. We use no workarounds.
- **Sound:** three short tones synthesized with Web Audio, so no audio assets. The audio context unlocks on the first tap. Where available, `navigator.audioSession.type = 'ambient'` so sound respects the silent switch and doesn't stop the user's music.
- **Native later:** the static build with hash routes drops straight into Capacitor for iOS. Android can use a Trusted Web Activity of the same URL through Bubblewrap/PWABuilder, which is cheap. A wrapped iOS app may face App Store review under guideline 4.2 (minimum functionality).

**Quality bars**

*Accessibility, WCAG 2.2 AA:*
- Options are a `radiogroup` with 48 px targets (2.5.8 requires at least 24 px). Keys `1`–`4` select, `Enter` checks or continues.
- Feedback uses an icon plus text plus color ("Correct!" / "Not quite: the answer is {1}{U}") in an `aria-live="assertive"` region. Focus moves to Continue.
- The feedback sheet never hides the focused element (2.4.11).
- Mana symbols get `aria-label` from Scryfall's `english` field.
- `prefers-reduced-motion` disables animations.
- Text contrast is at least 4.5:1 in both themes.
- Theme follows `prefers-color-scheme`, with an override in Settings.

*Performance budget (first cold load, Lighthouse mobile, Slow 4G, mid-range Android emulation):*
- Initial JS ≤ 90 KB gzip; CSS ≤ 15 KB gzip; no web fonts.
- Pack ≤ 60 KB gzip.
- LCP ≤ 2.5 s, TBT ≤ 200 ms, CLS ≤ 0.05.
- Lighthouse Performance ≥ 90, Accessibility ≥ 95.
- Enforced by `lighthouserc.json` assertions and resource budgets.

---

## 6. Quiz engine

**Question type interface** (`questionTypes/index.ts`):
```ts
interface QuestionTypeDef {
  id: QuestionTypeId; facet: Facet; tier: 1|2|3; scope: 'card'|'format';
  eligibleFaces(card: PackCard, ctx: PackCtx): number[];
  generate(card: PackCard, face: number, ctx: PackCtx, rng: Rng): Question | null; // null → can't build valid options
}
interface Option { key: string /* canonical value used for dedupe + grading */; display: OptionDisplay }
```

**Catalog**

| Type | Hides | Prompt shows | Answer from | Distractors | Valid for | Tier | Phase |
|---|---|---|---|---|---|---|---|
| `name_from_art` | name | `sides[0].art` + "Illustrated by {artist} · © Wizards of the Coast" | `name`; front-face name for transform | 3 pack cards ranked by similarity | every card with an art image | 1 | **1** |
| `name_from_text` | name | type line + text with `self` segments shown as "this card" (both halves for split, front face for transform) | `name` | similar pack cards; drop any whose redacted text equals the target's (functional reprints) | faces with text | 2 | **1** |
| `mana_cost` | one face's cost | `CardText` of that face with a "?" cost slot | `face.mana_cost` (key = sorted symbol multiset) | mana perturbations first, then same-cmc pack costs | faces with a non-empty cost (not lands or transform backs); **skip if the answer string appears in the visible text** | 2 | **1** |
| `spell_speed` | Instant/Sorcery | card text without the type line, **2 options** | `type_line` | the other one | instants and sorceries, including split halves | 1 | 2 |
| `type_line` | type line | card text without the type line | `face.type_line` | same-primary-type pack type lines; subtype swaps from the pack's vocabulary; adding/removing Legendary or Artifact | permanents | 2 | 2 |
| `power_toughness` | P/T | card text without P/T | `"p/t"` | ±1 on either value, ±1 on both, swapped | numeric P and T (not `*`) | 2 | 2 |
| `oracle_cloze` | one cloze segment | card text with that segment blanked | segment `t` | same-class word list (numbers ±1–2, verbs, card types, zones, colors, keywords in the pack); never one that makes the text equal another card's | `k` ∈ cloze classes | 3 | 2 |
| `meta_copies` | average copies | name + image, "How many copies does a typical {Format} deck run?" with 1/2/3/4 | `round(avg_copies)`, **only if** it is within 0.3 of the integer | the other integers | format-scoped; **needs `meta.avg_copies`, not published for now** | 2 | later |
| `meta_compare` | relative popularity | 2 cards, "Which is in more {Format} decks?" | higher `decks_pct` | binary; pair only when the gap is ≥ 8 points | format-scoped; **needs `meta.decks_pct`, not published for now** | 3 | later |
| `build_mana_cost` | cost (recall, not recognition) | tap symbols to build the cost | exact key | none | as `mana_cost` | 3 | 3 |
| `type_name` | name (recall) | art, type the name; grading uses a TS port of `normalize_name` plus Damerau-Levenshtein ≤ 2 | name tokens | none | all | 3 | 3 |

**Dropped:**
- Rarity, set, artist, flavor and release date: they depend on the printing (quirk 3) and teach nothing about play.
- Colors alone: redundant with the mana cost, and color indicators and devoid make it error-prone.
- Mana value alone: folded into the mana cost.
- Price: stale and off-topic.

**Distractors** (`distractors.ts`):
```
pickDistractors(target, pool, valueOf, similarity, perturb, need, rng):
  seen = { key(valueOf(target)) }; out = []
  ranked = pool − target
           |> map c → (similarity(target, c) + 0.15·rng(), valueOf(c))
           |> filter v ≠ null ∧ key(v) ∉ seen
           |> sortDesc
  for v in weightedSample(top 6 of ranked, need, rng): out.push(v); seen.add(key(v))
  for v in perturb(valueOf(target), rng) while |out| < need: if key(v) ∉ seen: out.push(v); seen.add(key(v))
  return |out| == need ? shuffle([valueOf(target), ...out], rng) : null
similarity(a, b) = 3·[same primary type] + 2·jaccard(colors) + 1·[|cmc diff| ≤ 1] + 0.5·[same unit]
```
Answers are always compared **by value key, never by card**. Two meta cards with the same P/T or cost can never produce two correct options.

**Mana perturbations** (`mana.ts`): parse `{X}{2}{U}{U}` into `{x, generic, hybrid[], pips[]}`. Operations, in preference order:
1. generic ±1 (never below 0)
2. swap a pip for generic, or generic for a pip of the same color
3. add or remove one pip of an existing color
4. change one pip to an adjacent color on the color wheel (last resort)

Synthetic costs are printed in canonical order: X, generic, then WUBRG. The dedupe key is the sorted multiset, so printed order never creates false duplicates.

**Text rendering:**
- `OracleText` splits on `\{[^}]+\}`, draws each symbol as an `<img>` with alt text from `english`, and falls back to a styled `{U}` text pill.
- Reminder segments are italic and muted.
- `self` segments show the name unless the name is hidden.
- Modal bullets and line breaks are kept.
- Transform cards: name-hiding questions use the front face only, and the back face appears on reveal.
- Split cards: `mana_cost` asks about one half, with that half's name visible.

**Facet unlocking (per card):**
- The intro screen (full image plus key facts, unscored) creates the tier-1 items.
- Tier-2 items are created when all of the card's tier-1 items reach box ≥ 2.
- Tier-3 items are created when all tier-2 items reach box ≥ 2.

**Card mastery (shown as 0–4 pips):**
- 0: new
- 1: introduced
- 2: some item in box ≥ 1
- 3: all tier-1 and tier-2 items in box ≥ 2
- 4: all eligible items in box ≥ 4

**Lesson composition** (`lesson.ts`; 10 scored questions):
```
composeLesson(pack, items, today, rng, size=10, maxNew=3):
  sched   = items where oracleId ∈ pack ∧ (format == null ∨ format == pack.format)
  due     = sched where dueDate ≤ today, sorted by (dueDate, box)
  newN    = |due| > 20 ? 0 : (|due| > 10 ? 1 : maxNew)
  newCards= first newN cards in teaching order with no items, from the lowest unlocked unit
  queue   = for c in newCards: [Intro(c), Q(c, tier-1 facet)]
  queue  += take(due, size − scored(queue))
  queue  += take(sched where box ≤ 2 ∧ not due, by lastReviewedAt asc, remaining)
  queue  += take(random sched where box ≥ 3, remaining)
  each item → generate(question type for its facet); null → skip and refill
  interleave so the same oracleId is never back to back; Intro stays right before its first question
```
- **Teaching order:** by `meta.rank` when the pack publishes it. Otherwise by `hash(deviceId + oracle_id)`: a shuffle that is fixed per device and per card, so a card entering or leaving the list never moves the others.
- **Units:** the teaching order, in chunks of 10. Unit n+1 unlocks when every card in unit n is introduced. Unlocked units are stored in `kv` and only ever go up, so a meta shift never re-locks the path. New cards that enter an unlocked unit are introduced first.
- **During a lesson:** a wrong answer reveals the correct one plus the full unaltered card image, and the item is re-asked once at the end. There are no hearts. A lesson is at most 14 questions.

**Leitner SRS** (`srs.ts`):
- Box intervals in days: `[0, 1, 3, 7, 16, 35]`.
- **Correct on the first try:** `box = min(box + 1, 5)`, and `dueDate = today + interval[box]`.
- **Correct only on the re-ask:** the box doesn't change, and the item is due tomorrow.
- **Wrong:** `box = 1`, `lapses++`, due tomorrow.
- **Binary questions** (2 options) can raise an item to box 3 at most, because of the 50% guess floor.
- **Meta facet whose answer changed in a new pack:** `box = min(box, 1)`, due today.

**XP, streak, goal** (`scoring.ts`):
- XP: +1 per correct first try, +10 for finishing a lesson, +5 for a perfect lesson.
- Daily goal: 20, 40 or 60 XP (default 20, about one lesson).
- **Streak** is *derived* from the `lessons` table: the number of consecutive local dates, ending today or yesterday, with at least one finished lesson. It is never stored as a counter, so a clock change can't corrupt it. If the clock goes backwards and dates arrive out of order, the latest date seen counts as "today". This mirrors how the backend already handles clock skew.
- Streak freeze: Phase 3.

**Reproducibility:** `seed = hash(deviceId + lessonId)` is stored on the lesson row. Dev and test builds also accept `?seed=` for repeatable runs.

---

## 7. Testing strategy

- **Python (pytest + mypy strict):** everything in §4.8. The golden test makes contract drift fail on both sides at once.
- **Engine unit tests (Vitest 5 + fast-check 4).** Property tests run over every fixture card × every question type × 500 seeds:
  - exactly one option is correct, and grading agrees with `correctIndex`
  - option keys are unique
  - the option count matches the type (4, or 2 for binary types)
  - **no leaks**: name tokens don't appear in the prompt of a name-hidden question; the cost string doesn't appear in the visible text of a cost question
  - `generate` returns `null` instead of invalid output
  
  Other unit tests:
  - Same seed gives the same lesson.
  - SRS transitions.
  - Local-date due math across DST and month and year boundaries.
  - Streak when the clock goes backwards.
  - `reconcile`: a card leaves (no writes), re-enters (old box kept), a meta answer changes (demoted).
  - **Projection:** `rebuildItems(reviews)` deep-equals the incrementally maintained items (the guarantee that makes sync possible).
  - Mana parsing, canonical order and perturbation.
- **Component tests:** `@testing-library/react` 16.3 for `OptionList` keyboard handling and `FeedbackSheet` focus.
- **E2E (Playwright 1.63):** projects `chromium`, `webkit`, `Pixel 7` and `iPhone 15` (WebKit), against `vite preview` with fixture data.
  - Onboarding → Pauper → offline download → seeded lesson → results; streak = 1 and XP correct.
  - Reload keeps progress.
  - **Offline:** after the first load, `context.setOffline(true)`, reload, and a lesson with images still works.
  - **App update:** serve build A, swap to build B → toast → refresh → new version, progress intact.
  - **Data update:** swap the manifest to a new pack hash → banner, progress kept, changed meta facet demoted.
  - **PWA assertions** (replacing Lighthouse's removed PWA category): manifest fields present, service worker controls the page, icons resolve, navigation works offline.
  - **Accessibility:** `@axe-core/playwright` on every screen with zero serious or critical issues, plus a keyboard-only lesson.
- **Lighthouse CI (`@lhci/cli` 0.15.1):** the performance and accessibility thresholds and budgets from §5, on every PR.
- **Manual check on a real iPhone, per release** (Playwright's WebKit is not iOS Safari):
  - install from Safari and launch standalone
  - airplane-mode lesson
  - force-quit and relaunch
  - safe areas and dark mode
  - sound with the silent switch on
  - backup export and import

---

## 8. Phased roadmap

**Phase 0: data pipeline and compliance (M)**
- 0.1 Scryfall compliance: pacing, 429 cooldown, User-Agent (S)
- 0.2 Pauper → `/all` (S)
- 0.3 Card model fields (S)
- 0.4 `meta_morphis/export` package, schemas, tests, golden fixture (M)
- 0.5 Housekeeping (S)
- 0.6 `ci.yml` Python job, plus a **dry run of the scheduled export** that uploads the pack as a workflow artifact. This proves Goldfish and Scryfall answer GitHub's runners. (S)

*Acceptance:*
- `uv run python -m meta_morphis.export --out /tmp/x --formats pauper pioneer` writes a manifest plus 2 packs that validate.
- A second run with the same data gives byte-identical packs and the same hashes.
- With the network off, it serves from cache and marks `stale` appropriately.
- pytest and mypy pass.
- The CLI `main.py` is unchanged.
- The CI dry run succeeds from GitHub runners.

**Phase 1: MVP on your phone (L)**
- Web scaffold; Pauper only.
- Question types: `name_from_art`, `mana_cost`, `name_from_text`.
- Intro cards, lesson composer, Leitner, XP, streak, daily goal.
- Dexie event log; offline download; service worker with update toast.
- Install hint and `persist()`; About and legal page; dark mode; accessibility.
- `deploy.yml` to Pages with the daily cron.

*Acceptance:*
- Installs and launches standalone on iOS 26 and Android Chrome.
- After "Download for offline", a full lesson works in airplane mode, images included.
- Progress survives force-quit and a data-pack update.
- Vitest, Playwright (Chromium and WebKit) and axe pass; Lighthouse thresholds met.
- The daily cron deploys new data without triggering an app update.

**Phase 2: breadth (M–L)**
- `spell_speed`, `type_line`, `power_toughness`, `oracle_cloze`.
- All 5 formats and a format switcher; progress is shared through `oracle_id`.
- Pauper display printing (schema v2).
- Meta-update banner; Progress and Card detail screens; backup export/import; sound and Android haptics.

*Acceptance:* every type passes the property tests on all five packs; switching formats keeps card-scoped progress; Pauper reveal images are common printings.

**Phase 3: depth (M)**
- `build_mana_cost`, `type_name`, rapid true/false review.
- Streak freeze; per-facet stats; Badging API (`setAppBadge`) for unmet goals on installed apps.
- Optional lands unit from Goldfish `/full/lands`.
- Widen the distractor pool from the Oracle Cards bulk file (23.5 MB gzipped JSONL, weekly, cached), **only if** answer logs show options are too easy to guess.

**Phase 4: optional (L)**
- Optional accounts and sync: upload events, e.g. Supabase or Cloudflare Worker + D1. Never required, per the Fan Content Policy.
- Streak reminders through Declarative Web Push: VAPID plus a scheduled sender. This adds the first server that stores user data, so it needs a privacy notice.
- Android TWA.
- MTGGoldfish meta data (rank, deck %, copies): set `EXPORT_META_FIELDS`, add the pairing step in `export/service.py`, and the app picks up rank-ordered teaching plus the `meta_copies` and `meta_compare` question types.
- **Replace MTGGoldfish with our own meta from tournament decklists (§9a).** Do this when we first want rank or deck % in the app, or before sharing the app publicly, whichever comes first.

---

## 9. Risks and mitigations

| Risk | Likelihood / impact | Mitigation |
|---|---|---|
| Goldfish's Terms of Use forbid republishing | High / high for a public launch | Personal circle only until resolved. Publish only the card list for now (`EXPORT_META_FIELDS = ()`), with attribution. Ask MTGGoldfish for permission before any wider sharing. Planned replacement: compute our own meta from public tournament decklists (§9a). |
| Fan Content Policy "games" clause is read strictly | Low / high | Present the app as a study trainer about Magic cards, with no non-Magic game mechanics. Verbatim notice; free; no required registration. Scryfall's Art Game is precedent. |
| Breaking Scryfall's rate limits gets the app banned | Certain today / high | Phase 0.1 fix (0.5 s pacing, 30 s 429 cooldown). The browser never calls the API. Images come from `*.scryfall.io`, which has no limits. |
| Goldfish markup changes | Medium / medium | The scraper already locates columns by `<th>` class and has `GOLDFISH_BAD_ROWS_LIMIT`. The SQLite cache serves stale meta; the exporter carries forward the last good pack with `stale: true`; the UI shows the data date; the CI run fails loudly. |
| Goldfish or Scryfall block GitHub runner IPs | Medium / medium | Found by the Phase 0.6 dry run. Fallback: run the exporter on your machine with a systemd timer and push the data, or use a self-hosted runner. |
| Scryfall API or image-URL changes (webp keys are new and "replace" the jpg ones) | Low / medium | Packs carry both `card` (webp) and `card_fallback` (jpg). The `onerror` fallback swaps to the jpg. Schema validation in CI. |
| iOS storage eviction, or Safari-tab vs Home Screen storage split | Medium / high (lost progress) | Nudge installation on iOS before progress builds up. `persist()`. Backup export/import. The event log enables a later sync. |
| Small pool (50 cards) makes quizzes repetitive | Medium / medium | Several facets per card; similarity-weighted random distractors; perturbation-based value distractors; tiers that unlock over time; Phase 3 recall formats; Oracle bulk widening only if data says so. |
| Meta shifts orphan progress | Certain / low | `oracle_id` keys; schedulability is computed; cards that leave keep their box and resume if they return; changed meta answers get demoted; banner explains it; units never re-lock. |
| Scheduled workflows auto-disable after 60 days with no repo activity (public repos) | Medium / medium | The app shows "Data as of <date>" and warns after 3 days. GitHub emails before disabling; re-enabling is one click. Optional keepalive action. |
| Bleeding-edge toolchain (Vite 8, vite-plugin-pwa 2.0 released 2026-10-03) | Medium / low | Pin exact versions in `package-lock.json`; Renovate or Dependabot weekly; TypeScript held at 6.0.x until 7 has been tried with this setup. |

---

## 9a. Planned replacement for MTGGoldfish: our own meta from tournament decklists

**Status:** planned, not built (decided 2026-10-10). MTGGoldfish stays the source until one of the triggers below.

**Idea.** Magic Online publishes the decklists from its events at <https://www.mtgo.com/decklists>. Instead of copying another site's ready-made ranking, we count the cards in those lists ourselves. The rank, deck % and copy counts are then our own calculation, not MTGGoldfish's compiled statistics, so `EXPORT_META_FIELDS` can be switched on without republishing their numbers.

**Where the data comes from.** Community archives on GitHub hold these decklists as JSON, one file per tournament:

| Archive | Status on 2026-10-10 | License |
|---|---|---|
| [fbettega/MTG_decklistcache](https://github.com/fbettega/MTG_decklistcache) | updated automatically, last on 2026-10-10 | GPL-3.0 |
| [Jiliac/MTGODecklistCache](https://github.com/Jiliac/MTGODecklistCache) | updated about weekly, last on 2026-10-05 | none stated |

The project both grew out of, Badaro/MTGODecklistCache, was archived in June 2025. If both stop, read mtgo.com directly.

File shape (fbettega, verified on a real file): `Tournament` (`Date`, `Name`, `Uri`, `Formats`), and `Decks[]`, each with `Mainboard[]` and `Sideboard[]` of `{Count, CardName}`. Files live under `Tournaments/MTGO/<yyyy>/<mm>/<dd>/<format>-….json`. The archive has 2026 files for all five formats; Pauper had 30 files in the first ten days of October 2026.

**Checked that it works.** Counting the 30 decks of the Pauper Challenge of 2026-10-10 gave Hydroblast 50%, Blue Elemental Blast 43%, Pyroblast 33%, Lórien Revealed 33%, Nihil Spellbomb 30%: the same cards that top the MTGGoldfish list.

**What to build (about 100 lines of Python).**
- A new source module beside `meta/scraper.py` that downloads one format's files for the last N days and returns the same `list[MetaEntry]` the scraper returns. Nothing downstream changes: `get_meta_cards`, the cache, `fetch_cards` and the export only need that list.
- Counting rule to decide then: window length (e.g. 30 days), main deck only or with sideboard, and `percent` = share of decks containing the card. `avg_copies` = mean count among decks that play it.
- Leave out basic lands. In the test above, Swamp and Island ranked near the top.
- Match names with the existing `normalize_name` (the lists spell "Lórien Revealed" with the accent).

**Known limits.**
- Both archives are small volunteer projects and can stop at any time.
- MTGO publishes the top finishers of Challenges and only undefeated League decks, so the numbers describe winning decks, not everything played.
- mtgo.com's terms of use have **not** been read yet. Do that before a public launch.

**Triggers to build it:** we want rank or deck % in the app, or we are about to share the app publicly.

---

## 10. Open questions for you

1. **MTGGoldfish permission.** Will you email MTGGoldfish now, or keep strictly to friends until you do? (Decided 2026-10-10: packs publish no rank, deck % or copy counts for now. The format keeps them optional, so they can be switched on later.)
2. **Name and icon.** Is "meta-morphis" the user-facing name in the manifest and the Fan Content notice? Do you have an icon idea? It can't use WotC symbols.

---

## Verification (end to end)

1. `uv run pytest && uv run mypy .`: every old and new Python test passes. Run `uv run python main.py` and confirm the CLI still works.
2. `uv run python -m meta_morphis.export --out web/public/data --formats pauper`, run twice → identical `packs/pauper.<sha>.json`. Inspect the manifest and validate it against `schema/`.
3. `cd web && npm ci && npm run check && npm test && npm run build && npx playwright test && npx lhci autorun`.
4. `npm run preview` on desktop: do onboarding and a lesson, then in DevTools go offline, reload, and finish a lesson. Check Application → Cache Storage for non-opaque entries in `mm-scryfall`.
5. Push to `main` → `deploy.yml` → open the Pages URL on an iPhone (iOS 26) and an Android phone. Install, airplane mode, lesson, force-quit, relaunch, and confirm progress is still there.
6. Trigger `workflow_dispatch` the next day: the manifest `generated_at` updates, the pack hash changes only if the meta changed, and the app shows no update toast.

## Sources

- Scryfall: [API overview and data/image terms](https://scryfall.com/docs/api) · [Rate limits](https://scryfall.com/docs/api/rate-limits) · [Card imagery](https://scryfall.com/docs/api/images) · [Bulk data](https://scryfall.com/docs/api/bulk-data) · [Card symbols](https://scryfall.com/docs/api/card-symbols)
- [WotC Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy)
- MTGGoldfish: [Terms of Use](https://www.mtggoldfish.com/policies/terms-of-use) · [robots.txt](https://www.mtggoldfish.com/robots.txt)
- WebKit: [WWDC25 / iOS 26 web apps](https://webkit.org/?p=16993) · [Storage policy](https://webkit.org/?p=14403) · [Bug 181849, Home Screen storage separate from Safari](https://bugs.webkit.org/show_bug.cgi?id=181849) · [Web Push on iOS](https://webkit.org/?p=13878) · [Declarative Web Push](https://webkit.org/?p=16535) · [Badging](https://webkit.org/?p=14112)
- iOS haptics: [no Vibration API on iOS](https://bugnet.io/blog/fix-web-game-vibrate-api-not-available-ios-safari) · [`<input switch>` workaround patched in 26.5](https://azukiazusa.dev/en/blog/ios-safari-web-haptics)
- [GitHub: scheduled workflows disabled after 60 days](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
- [Chrome: Lighthouse PWA category removed](https://developer.chrome.com/blog/update-install-criteria)
- Verified directly on 2026-10-06:
  - `npm view` versions and peer dependencies (vite 8.3.3, vite-plugin-pwa 2.0.0, dexie 4.4.6, vitest 5.0.3, @playwright/test 1.63.0, fast-check 4.10.2, ts-fsrs 5.4.2)
  - Verified on 2026-10-13 for the switch to React: react and react-dom 19.3.0, @vitejs/plugin-react 6.1.2 (peers vite ^8), react-router 8.4.0, @testing-library/react 16.3.3
  - `curl` headers on `cards.scryfall.io` and `svgs.scryfall.io` (`access-control-allow-origin: *`, one-year `max-age`)
  - Goldfish `/full/all` vs `/full/spells` compared with the repo's own `_parse_meta_table`
