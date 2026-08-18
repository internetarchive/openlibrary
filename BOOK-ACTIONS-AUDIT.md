# Book Actions — audit, decisions, and state of play

> **Working document.** Started as a design audit of every action Open Library
> attaches to a book; now also tracks what has been implemented on the
> `action-button` branch, what the implementation proved wrong about the audit,
> and what overlapping work is in flight elsewhere in the project.
>
> Rendered version of the original audit:
> <https://claude.ai/code/artifact/114a4304-a464-4bbc-af1d-0a8971dc6d06>
>
> Audit written 10 Aug 2026 against `upstream/master` at `b9cab907f`.
> Ecosystem sweep (§15) is a point-in-time snapshot from the same day —
> **re-check PR states before acting on it.**

---

## Status at a glance

| Phase | Scope | State | Commit |
|---|---|---|---|
| **0** | Label vocabulary + state line | Done | `a91d0d4c9` |
| **1** | Logged-out default, one disclosure implementation | Done | `5ad066897` |
| **2** | Extract `BookActions`; Save in carousels | **Done** | `fcfd352f0`, + density commit |
| **3** | Surface intent replaces ad-hoc booleans | Not started | — |

Findings cleared: **F1, F2, F4, F5, F6, F7, F8, F9, F11, F12**.
Still open: **F3**, **F10** (half), **F13**, **F14**.

Nothing has been pushed or opened as a PR. Commit hashes above predate the
rebase onto `93af75078` (12 Aug); see `git log`.

---

## 1. Method & scope

Two passes.

**Source pass** followed the three components that actually decide what a book
shows: `macros/LoanStatus.html` (the access state machine),
`templates/my_books/dropper.html` (shelf and lists), and
`macros/SearchResultsWork.html` (the row shell that composes them). Every call
site of those three was enumerated — eleven templates — plus the two carousel
card templates, which bypass the row shell entirely.

**Live pass** captured production Open Library logged out, and the search-results
row of Goodreads, Hardcover, The StoryGraph, Libby/OverDrive, Google Books and
WorldCat, signed in where the product requires it.

**Out of scope:** author and list rows (different object type), the editor,
librarian merge tooling, affiliate/donation surfaces.

---

## 2. Action inventory

Twenty-seven actions can attach to a book, in four families. The families behave
differently: access actions are mutually exclusive and derived from data,
tracking actions are user state, outbound actions are always available, and
navigation actions are frequently disguised as the other three.

| Action | Family | What it does | Where it lives | Auth |
|---|---|---|---|---|
| Read | Access | Opens the IA bookreader for an open or already-borrowed item | `ReadButton.html` | No / loan |
| Borrow | Access | Checks out a lendable IA copy | `ReadButton.html` | Yes |
| Read (partner) | Access | Leaves for Gutenberg, Standard Ebooks, Runeberg, OpenStax, Cita, Wikisource, Direct | `book_providers/read_button.html` | No |
| Audiobook → **Listen** | Access | Opens a LibriVox / audio-format acquisition | `book_providers/read_button.html` | No |
| Listen | Access | Opens the reader with Read Aloud auto-started | `ReadButton.html` (menu) | No / loan |
| Preview | Access | archive.org theater iframe in a floater | `BookPreview.html` | No |
| Preview Only → *retired* | Access | Same action, relabelled to communicate a limitation | `BookPreview.html` | No |
| Special Access → **Read** | Access | Print-disabled exemption route into the reader | `ReadButton.html` | Yes |
| Join waitlist | Access | Joins the hold queue for a checked-out lendable | `LoanStatus.html` | Yes |
| Leave waitlist | Access | Exits the hold queue | `LoanStatus.html` | Yes |
| Checked Out → *retired* | Access | Nothing — linked to the work page | `LoanStatus.html` | No |
| Not in Library → *retired* | Access | Nothing — a `<span>` styled as a button | `NotInLibrary.html` (deleted) | No |
| Return book | Access | Ends an active loan early | `ReturnForm.html` | Yes |
| Locate → **Find in a library** | Access | Nearby-library finder for the edition | `LocateButton.html` | No |
| Download options | Access | Per-provider format list | `book_providers/*_download_options` | No |
| Search inside | Access | Full-text search within one book | `PreviewSearchInside.html` | No |
| Want to Read | Track | Shelf 1 | `my_books/primary_action.html` | Yes |
| Currently Reading | Track | Shelf 2 | `my_books/dropdown_content.html` | Yes |
| Already Read | Track | Shelf 3 | `my_books/dropdown_content.html` | Yes |
| Stopped Reading | Track | Shelf 4 | `my_books/dropdown_content.html` | Yes |
| Remove From Shelf | Track | Clears shelf state and any check-ins | `my_books/dropdown_content.html` | Yes |
| Add to list | Track | Toggles list membership; can create one | `lists/dropper_lists` | Yes |
| Check in | Track | Records a date finished; editable, deletable | `my_books/check_ins/*` | Yes |
| Rate | Track | 1–5 stars | `StarRatings.html` | Yes |
| Review | Track | Structured observations modal | `ObservationsModal.html` | Yes |
| Notes | Track | Private per-book notes | `NotesModal.html` | Yes |
| Share | Outbound | Share-link modal | `ShareModal.html` | No |
| Buy this book | Outbound | Affiliate: Better World Books, Amazon, more | `AffiliateLinks.html.jinja` | No |
| Check nearby libraries | Outbound | WorldCat lookup — a second, differently-labelled Locate | `WorldcatLink.html` | No |

**Navigation wearing action clothes:** the *N editions / N ebooks* links, the
edition-cover thumbnail strip, and the subject chips. All useful; none should be
styled like, or sit next to, a transactional control. See F13.

---

## 3. Surface inventory

Fourteen surfaces render a book. Eleven go through one shared row component;
three carousel templates bypass it and reimplement the card. That split is the
root cause of most of what follows.

| ID | Surface | Template | Shell | Intent |
|---|---|---|---|---|
| S1 | Search results | `work_search.html:162` | Row | Discover |
| S2 | Search inside results | `FulltextResults.html:15` | Row | Discover |
| S3 | Trending | `trending.html:31` | Row | Discover |
| S4 | Author page works | `type/author/view.html:169` | Row | Discover |
| S5 | List detail page | `type/list/view_body.html:125` | Row | Curate / manage |
| S6 | Reading log (shelf page) | `account/reading_log.html:96` | Row | Manage |
| S7 | Loan history | `account/loan_history.html:14` | Row | Recall |
| S8 | Reading-log stats | `stats/readinglog.html:67+` | Row | Analyse |
| S9 | Standard carousel (home, subject, publisher, related) | `books/custom_carousel_card.html` | Card | Discover |
| S10 | My Books carousel (desktop) | `account/mybooks.html:18` | Card | Manage |
| S11 | My Books showcase (mobile) | `books/mobile_carousel.html` | Card | Manage |
| S12 | Editions table | `books/edition-sort.html:93` | Table row | Choose a copy |
| S13 | Work / edition page databar | `macros/databarWork.html:39` | Sidebar | Commit |
| S14 | Grid layout (variant of S1, S6) | `legacy.css:1525` | Row (CSS) | Scan |

**Intent is the missing axis.** Surfaces cluster into three jobs — *discover*
(S1–S4, S9), *manage* (S5–S7, S10, S11), *commit* (S12, S13) — but nothing in
the code knows which job a surface is doing. Capability is decided instead by
six unrelated booleans threaded through `SearchResultsWork`: `cta`,
`include_dropper`, `secondary_action`, `listen`, `rating`, `decorations`.

---

## 4. The matrix — what we showed where (as audited, pre-changes)

`●` always shown · `○` conditional on data or auth · `·` not available

| Surface | Access | Preview (2nd) | Search inside | Shelve | Add to list | Check in | Rate | Review/Notes | Share | Buy | Locate | Remove |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| S1 Search | ● | ○ | · | ● | ● | ○ | · | · | · | · | ○ | · |
| S2 Search inside | ● | ○ | · | ● | ● | ○ | · | · | · | · | ○ | · |
| S3 Trending | ● | ○ | · | ● | ● | ○ | · | · | · | · | ○ | · |
| S4 Author | ● | ○ | · | ● | ● | ○ | · | · | · | · | ○ | · |
| S5 List page | ● | ○ | · | ● | ● | ○ | · | · | · | · | ○ | ● |
| S6 Reading log | ● | ○ | · | ○ | ○ | ○ | ● | · | · | · | ○ | · |
| S7 Loan history | ● | ○ | · | · | · | · | ● | · | · | · | ○ | · |
| S8 Stats | ● | ○ | · | · | · | · | · | · | · | · | ○ | · |
| S9 Carousel | ● | · | · | · | · | · | · | · | · | · | · | · |
| S10 My Books carousel | ● | · | · | · | · | · | · | · | · | · | · | · |
| S11 Mobile showcase | · | · | · | · | · | · | · | · | · | · | · | · |
| S12 Editions table | ● | · | · | · | · | · | · | · | · | · | ● | · |
| S13 Book page | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | · |
| S14 Grid | ● | ○ | · | ● | ● | · | · | · | · | · | ○ | · |

S14 hides rating and check-in via CSS, not template logic.

**In one sentence:** the two surfaces where a reader is most likely browsing
with intent to save — carousels (S9) and My Books carousels (S10) — are the only
two with a control that offer nothing but an access button.

---

## 5. Findings

| # | Finding | Severity | Status |
|---|---|---|---|
| F1 | Two mental models stacked in one column with no signal they differ | Blocker | Addressed structurally — `BookActions` |
| F2 | Carousels cannot save a book at all | Blocker | Fixed — §7a, §13 |
| F3 | My Books shelf carousels show the wrong verb ("Borrow" on *Currently Reading*) | Blocker | Open — Phase 3 |
| F4 | Logged-out readers offered "Add to List" instead of "Want to Read" | High | Fixed |
| F5 | The shelf button ships to the browser `disabled` | High | Fixed |
| F6 | The disclosure trigger is not a button and announces no state | High | Fixed |
| F7 | Button-shaped controls that do nothing | High | Fixed |
| F8 | "Locate" suppressed exactly where it is the only useful action | High | Fixed |
| F9 | Preview appears twice in the same row, under two names | Medium | Fixed |
| F10 | Two unrelated disclosure widgets, two implementations | Medium | Half — one implementation; a row can still show two carets |
| F11 | Overflow menu appears by accident of provider, not by design | Medium | Fixed |
| F12 | Ten labels for one slot, mixing verbs, nouns and statuses | Medium | Fixed |
| F13 | Nothing spent on what makes Open Library different | Medium | Open |
| F14 | Grid view hides capability with CSS instead of configuring it | Low | Open |

### Detail on the ones still open

**F3 — My Books shows the wrong verb.** *Currently Reading*, *Want to Read*,
*Already Read* and *Stopped Reading* on the My Books landing page render with
the standard carousel, so every cover carries "Borrow" or "Read". No way to move
a book between shelves from the page whose entire purpose is shelf management.
On mobile those shelves render with no controls whatsoever.

**F13 — the differentiators are invisible.** Full-text search inside a book and
the edition/format picker are the two capabilities no competitor in this scan
offers. In search results both are plain text links in the metadata block,
styled identically to the publication year.

**F14 — grid hides with CSS.** `.list-books--grid` hides the details block, the
star-rating form and the check-in prompt with `display: none`; the markup is
still generated and shipped, and two full-width buttons still dominate a card a
third of the width.

---

## 6. How six other products solve it

| Product | Primary control | Secondary | Inside the menu | Controls/row | Model |
|---|---|---|---|:-:|---|
| Hardcover | Split — *Want to Read ▾*, recoloured green with a check when set | None | 5 statuses, rating, review, journal, dates read, tags, add to list, privacy | 1 | Everything in one menu |
| Goodreads | Split — *Want to Read ▾*; outlined *Read ✎* when shelved | Split — *Shop this series ↗* | Shelves; separately "more options to get the book" | 2 | Track + commerce, separated |
| The StoryGraph | Split — *to read ▾* | Text — *mark as owned* | Status alternatives only | 2 | Deliberately minimal |
| Libby / OverDrive | Filled — *Borrow* / *Place a Hold* | Icon+text — *Add to wish list* | Kebab: sample, details, series, add to history, related | 2 + ⋮ | Access first, save second |
| Google Books | Chip — *Preview* | Chip — *More editions* | None | 2 | Low-commitment, no account state |
| WorldCat | None — the title is the action | Bookmark icon | None | 1 | Pure catalogue |
| **Open Library** | Filled — one of ten labels | Split — *Want to Read ▾* | 4 statuses, remove, lists, create | 2 full-width | Access *and* track, equally weighted |

**Three things all of them do that we didn't:**

1. **Exactly one disclosure per row.** Whatever doesn't fit goes into a single
   menu — never two competing ones. Hardcover puts nine action groups behind one caret.
2. **The saved state changes the button, visibly.** Hardcover recolours green
   with a check; Goodreads switches to outlined with a pencil. Open Library adds
   a small "✓" inside the same blue-grey button — the weakest state signal of the six.
3. **Secondary actions look secondary.** Nobody ships two full-width buttons of
   equal weight.

**And one thing only Libby shares with us:** it is the only comparable that is
also a lending library, facing the same tension between a transactional Borrow
and a lightweight save. Its answer — one filled access button, one quiet save,
one kebab — is the closest available precedent.

---

## 7. Options explored

| | Option | Verdict |
|---|---|---|
| A | Status quo, tidied — keep both full-width buttons, fix labels only | Cheapest; leaves F1 untouched, does nothing for carousels |
| B | One button, one menu (Hardcover) | Cleanest on paper. **Rejected:** buries Borrow behind a caret. Hardcover can collapse to one button because it has no access action to collapse |
| C | Horizontal pair — access full-width, save as a "+" icon | Unambiguous hierarchy; an unlabelled "+" is the least discoverable save control, and shelf state has nowhere to render |
| D | **Access + Save, one menu, state line between** | **Chosen shape** |
| E | Access + icon rail (save/list/rate/more) | Densest; four unlabelled icons is an i18n problem, and there's no shipped icon system to build on |
| F | Reveal on hover/focus | Calmest scanning; no hover on touch, and hides availability, which is a primary reason people scan our results |
| G | **Capability by surface intent** | **Chosen policy** — composes with D |

---

## 7a. Density — the axis the audit was missing

Decided 12 Aug, after the audit's option review. Option **D** (access + save,
one menu) is the roomy shape; option **C** (access + an icon disclosure) is the
same component with the labels dropped. They are not two designs — they are one
design at two densities, and the audit had no axis for that.

**Intent decides which actions exist. Density decides how much of them shows.**
A My Books carousel is `manage` *and* tight; a search row is `discover` *and*
roomy; a search row on a phone is `discover` *and* tight. One knob could not
express that.

Density is **CSS**, not a template parameter, because the deciding factor is the
width of the column and no surface knows it. `.book-actions` is a query
container; the compact shape is an override on it, so browsers without container
queries (Safari < 16) keep the roomy shape rather than getting the wrong one.

### What changes when the container is narrow (≤ 150px)

| | Roomy | Narrow |
|---|---|---|
| Arrangement | Access above Save | Access and Save side by side |
| Access | Filled button + its own overflow caret | Filled button, **overflow dropped** |
| Save | Shelf-named split button + caret | The caret alone: **+**, or **✓** when shelved |
| Menu | Shelf · lists · everything | **Shelf and lists only** |
| State line | Every caption | Captions that add something the button doesn't |

**Decisions behind that table**

1. **One disclosure per book still holds.** The access button's overflow and the
   save menu cannot both fit, so the save menu takes the slot. Ways-to-read is
   one click away on the book page; the shelf is not reachable any other way
   from a carousel. This is what makes the `+` mean exactly one thing.
2. **The `+` opens the menu**; it is not a one-click *Want to Read*. Same
   affordance, same behaviour, both densities.
3. **A caption earns its line.** "Available to borrow" under *Borrow* and
   "Preview only" under *Preview* restate the verb and are marked
   `cta-state--restates-button`; the narrow rule hides them. "All copies are
   checked out", "Not available online", waitlist position and "On loan to you"
   stay — they are why the verb is what it is, and they are what lets a reader
   skip a row fast.
4. **Logged-out readers get the save control in carousels too**, per rule 3.
   The login-intent volume this adds is worth measuring (see §12).
5. **Rule 3 is amended.** "Always labelled" becomes "always present, always
   *named*" — the accessible name is on the trigger and does not change with
   the glyph.

Still open, deliberately: on a `manage` surface the shelf name should be the
card's state line (that is what fixes F3), and the shelf name is exactly what
the narrow shape drops. That needs the intent axis, so it lands with Phase 3.

## 8. The proposed model

> ### Buttons are verbs. States are text.
>
> If a label describes the book rather than what happens on click, it belongs on
> the state line.

One component — `BookActions` — with three slots and a declared surface intent.
Option D supplies the shape; option G supplies the policy.

**Slot 1 — Access (always).** Filled primary button. One verb from a closed
vocabulary of six: **Read · Borrow · Listen · Preview · Join waitlist · Find in
a library**. Never a status, never a noun, never a category name.

**Slot 2 — Save (when auth is possible).** Secondary split button. Label is the
current shelf, or *Want to Read* when unset — including when logged out. Never
*Add to List*. Its caret is the row's **only** disclosure. Built on
`<ol-button>` + `<ol-popover>`.

**Slot 3 — State line (a caption, not a control).** One line of muted text
carrying every fact that used to be a fake button.

### What goes in the menu

| Group | Items | Shown when |
|---|---|---|
| Shelf | Want to Read · Currently Reading · Already Read · Stopped Reading · Remove from shelf | Always (login intent when logged out) |
| Rate | Inline five-star control | Signed in |
| Lists | Existing lists as toggles · Create a new list · Use this work | Signed in |
| More ways to read | Listen · Preview · Search inside · Download options · Find in a library | Any the access slot did not take |
| Write | Review · Notes · Check in | Signed in, shelf set |
| Elsewhere | Share · Buy this book · All editions | Always |
| This list | Remove from this list · Edit note | Surface is a list page the reader owns |

### The four rules

1. **Buttons are verbs; states are text.**
2. **One disclosure per book.** Never two carets, never a caret and a kebab.
3. **The save control is always labelled and always present** where saving is
   possible — including carousels, including logged out.
4. **Surfaces declare intent, not capability.** `intent="manage"`, not
   `include_dropper=True, rating=…, cta=False`.

---

## 9. Access slot decision table

Mapped onto the states `get_lending_state()` already returns. **Shipped** copy
differs from the audit's proposal where the data doesn't exist — see §14.

| `lending_state` | Old label | Button (shipped) | State line (shipped) |
|---|---|---|---|
| `borrowed` | Read | **Read** | On loan to you |
| `open` | Read | **Read** | Free to read *(restates)* |
| `partner` (open access) | Read | **Read** | On {Provider} |
| `partner` (sample) | Preview | **Preview** | Preview only *(restates)* |
| `partner` (audio) | Audiobook | **Listen** | On {Provider} |
| `printdisabled` | Special Access | **Read** | Special access for patrons with print disabilities |
| `borrowable` | Borrow | **Borrow** | Available to borrow *(restates)* |
| `waitlist` (not waiting) | Join Waitlist | **Join waitlist** | Readers in line: {n} / You'll be next in line |
| `waitlist` (waiting) | Leave waiting list | **Leave waitlist** | You are #{n} of {m} on the waiting list |
| `checkedout` | Checked Out *(dead link)* | **Find in a library** | All copies are checked out |
| `preview_only` | Preview Only | **Preview** | Preview only *(restates)* |
| `locate` | Not in Library *(dead span)* | **Find in a library** | Not available online |

The last three are the states that previously shipped a button with no action.

*(restates)* marks a caption that only re-says the button's verb. Those carry
`cta-state--restates-button` and are hidden inside `@container book-actions
(max-width: 150px)`, so carousels show only the captions that add something.
"Free to read" is one of them: nothing on Open Library is ever paid, so the
distinction a reader is actually drawing is Read vs Borrow, and the button says
that already. The partner captions drop "free" for the same reason and name a
destination instead — the one fact the button never carries — so they stay
visible at every density.

---

## 10. Per-surface configuration (Phase 3 target)

| Surface | `intent` | Leads with | Second control | Menu groups | Extras |
|---|---|---|---|---|---|
| S1–S4 Search, trending, author | `discover` | Access | Save (labelled) | All | State line |
| S9 Carousel | `discover` | Access | Save (labelled) | Shelf, lists, more ways to read | Hydrated client-side |
| S5 List page (owner) | `manage` | Access | Save | All + *This list* | Note editor |
| S5 List page (visitor) | `discover` | Access | Save | All | — |
| S6 Reading log (owner) | `manage` | **Save (shelf leads)** | Access | All | Inline rating, check-in |
| S10 My Books carousel | `manage` | **Save (shelf leads)** | Access | Shelf, write | Check-in date on state line |
| S11 Mobile showcase | `manage` | **Save (shelf leads)** | — | Shelf | Currently renders nothing |
| S7 Loan history | `manage` | Access | Save | All | Inline rating |
| S12 Editions table | `commit` | Access | — | More ways to read | Format & download |
| S13 Book page | `commit` | Access | Save | All | Search inside, buy, share stay explicit |
| S14 Grid | inherits | Access | Save | All | Compact size, not hidden markup |
| S8 Stats | `discover` | Access | — | — | Read-only |

**"Shelf leads"** means the two slots swap emphasis on a `manage` surface: Save
takes the filled primary style and the shelf name as its label, Access drops to
secondary. On *Currently Reading* that turns each card's control from "Borrow"
into "Currently Reading ▾" — one click from "Already Read", which is what that
page exists to support. This is the structural fix for F3.

---

## 11. Rollout & measurement

### Phase 0 — label vocabulary and the state line ✅ `a91d0d4c9`
Templates only. Clears F5 · F7 · F8 · F9 · F12.

### Phase 1 — logged-out default, one disclosure ✅ `5ad066897`
Clears F4 · F6 · F10 (partial) · F11.

### Phase 2 — extract `BookActions`, put it in carousels ✅
`fcfd352f0` extracted the component and wired the row shell. The density commit
put it in carousel cards, both render paths (inline and the load-more /
lazy-carousel partials), with shelf status bulk-loaded once per carousel.
Clears F1 · F2.

### Phase 3 — surface intent ⬜
Add `intent` to `BookActions`; migrate all fourteen call sites; retire `cta`,
`include_dropper`, `secondary_action`, `listen`, `rating`, `decorations`; give
the grid a compact size instead of `display: none`.
Clears F3 · F13 · F14.

### Measurement

Hooks exist: `data-ol-link-track` emits `CTAClick|{Action}`,
`ReadingLog|{Shelf}`, `BookCarousel|CTAClick|{key}`. Two additions make the
phases comparable — add the **slot** (`Access` / `Save` / `Menu`) and the
**surface intent** to the track value.

| Metric | Baseline | Expected direction |
|---|---|---|
| Shelf adds per 1,000 carousel impressions | Zero — the control does not exist | Up, from nothing |
| Borrow / Read click-through per result row | Phase 0 must not move it | Flat or up; a drop means the state line stole weight |
| Locate clicks from search results | Zero — "Not in Library" was not clickable | Up, from nothing |
| Login-intent completions from Save | Existing `js-login-intent` funnel | Up, now the label matches the resumed action |

---

## 12. Risks & open questions

**Risks**

- **More login prompts.** Save on every carousel card increases login-intent
  interceptions for logged-out readers. Worth an experiment; the fallback is to
  render Save in carousels only when a session exists.
- **Label width and i18n.** "Find in a library" and "Currently Reading" are long.
  They fit carousel cards at desktop widths (verified); narrow viewports unchecked.
- **Losing a real signal.** "Not in Library" was blunt but honest, and some
  readers used it to skip rows fast. The state line must stay distinct enough to
  serve that scanning behaviour.
- **Translation debt.** Nine translated strings retired; thirteen new ones need a pass.

**Open questions**

1. Should *Buy this book* ever appear in a search-result menu? Goodreads leads
   with commerce; we confine it to the book page. Policy call.
2. Does rating belong inline on `manage` surfaces, or in the menu everywhere for
   consistency? Hardcover: menu. Goodreads: inline.
3. Is *Stopped Reading* worth a top-level shelf slot given its usage?
4. Should the editions table get a Save control at edition granularity, or does
   shelving stay work-level?

---

## 13. What has been implemented

Branch `action-button`, off `upstream/master` at `b9cab907f`. Three commits, no PR.

**`5ad066897` — one disclosure implementation, on `ol-popover`**
Dropper caret `<a href="javascript:;">` → real `<button>` slotted into
`<ol-popover>`. Read button `<details>` → the same component. `Dropper` bridges
to the popover rather than owning open/close, so `onOpen`/`onClose` fire for
Escape and outside clicks too. Removed the `is_carousel` analytics-string test,
`initGenericDroppers`, jQuery `slideToggle`, the hand-toggled `.arrow.up` class.
Fixed a stacking bug where `isolation: isolate` + a `z-index` scoped the fixed
panel to its own row. Fixed the create-list modal stealing focus back to the caret.

**`a91d0d4c9` — buttons are verbs, states are text**
Six-verb vocabulary; state line; `Find in a library` wired into the works branch
with a two-tier destination; `NotInLibrary.html` deleted; duplicate preview
trigger removed; shelf forms work without JS via `redir`; waitlist position now
shows on search rows.

**`fcfd352f0` — one component for the action column, and one shelf query**
`macros/BookActions.html`; search rows wired through it; the read-status N+1
fixed (see §14).

**Density, and Save in carousels (F2)**
`.book-actions` became a query container with a `__layout` child — a container
query cannot style the element it queries, so the arrangement needs its own
element. The compact shape hides the shelf button, turns the disclosure trigger
into a `+`/`✓`, drops the access overflow and the restating captions. Carousel
cards now render `BookActions`; `custom_carousel.html` and `CarouselCardPartial`
both bulk-load shelf status with `add_read_statuses()` and pass the work-level
doc down, since a card may be showing an edition. The check-in prompt is off in
carousels — it costs a query per book.

Four things had to be fixed to make a dropper work inside a card:

- `page-home.css`, `page-subject.css` and `page-book.css` never imported the
  dropper's CSS, because until now a carousel card had no dropper.
  `book-actions.css` imports what the action column needs and the page bundles
  ask for it by one line; the bundler dedupes.
- `.carousel button { position: absolute }` — a pre-hydration hack for slick's
  injected arrows, which now live in `<ol-carousel>`'s shadow DOM — was taking
  every button in a card out of flow and stacking the whole shelf menu on one
  line. Scoped to `.carousel > button`.
- The menu hides whichever shelf the primary button already offers. With the
  primary button off screen, an unshelved book offered every shelf *except*
  "Want to Read". The narrow rule puts it back.
- `container-type` applies layout containment, so it was worth checking whether
  it traps `position: fixed` panels the way a transformed track does. Probed in
  Chrome: it does not.

**Test coverage added:** `openlibrary/tests/test_book_action_disclosures.py`
(12 tests — disclosure structure, label vocabulary with a guard against drift,
action-column grouping, precomputed shelf status). `tests/unit/js/droppers.test.js`
rewritten against a stand-in `<ol-popover>`.

**Unverified:** the mobile bottom-tray presentation of the dropper, and
`ol-popover`'s focus restore. Browser automation input broke mid-session and
never recovered — both need a manual pass.

---

## 14. Corrections the implementation forced on the audit

The audit was written from a source read. Seven things it got wrong or missed:

1. **There are no copy counts.** `AvailabilityStatus` has `num_waitlist` but
   nothing like "1 of 3 copies available" — that proposed state line is not
   renderable. Borrowable books say "Available to borrow".

2. **`ol-menu-popover` is the wrong base.** It takes a declarative `items` array
   of mutually-exclusive choices and cannot host the dropper's forms, checkboxes
   and async list content. The right base is `<ol-popover>`, which takes
   arbitrary slotted content.

3. **F8 is not a ten-line fix.** The locate route resolves an edition's OCLC/ISBN
   and needs an edition key. Works search does **not** ask Solr for
   `edition_key`, and `get_doc()` reshapes what it does return. With only the
   edition path, 13 of 21 rows on a sample page had *no button at all* — worse
   than the dead span. Shipped answer: edition route when a key resolves,
   WorldCat title+author search otherwise. Better fix later: a work-level locate
   route, or the Solr field.

4. **Two doc shapes reach `LoanStatus`.** Raw Solr dicts (carousels) and the
   `web.storage` that `get_doc()` builds (search, trending, author). They spell
   authors and edition keys differently; both must be checked.

5. **F5 is not "remove `disabled`".** Doing only that would make pre-hydration
   clicks POST and land the patron on raw JSON — worse than the current silent
   nothing. The endpoint supports `redir`, so the forms carry it and the fetch
   path strips it from the `FormData`.

6. **The carousel blocker is not caching.** `gather_lazy_carousel_data`
   memoizes the Solr *data*, and the HTML renders per request — so per-user state
   is fine. The real blocker is layout, and it is hard:

   ```
   fixedProbeLandedAt: { x: 187, y: -203 }   // should be { x: 0, y: 0 }
   trackTransform:     "matrix(1, 0, 0, 1, 0, 0)"
   containerIsolation: "isolate"
   ```

   `.slick-track` carries a transform. *Any* transform makes an element the
   containing block for `position: fixed` descendants, so `ol-popover`'s panel is
   measured against the track, not the viewport — it renders ~200px off and
   clipped. `.carousel-container`'s `isolation: isolate` would independently
   scope the panel's z-index.

   **Fix, since shipped elsewhere:** promote the panel to the **top layer** via
   the native Popover API, with a `position: fixed` fallback below Safari 17.
   That is **PR #13324** (`popover/fix/top-layer`), open. Separately **PR
   #13220** rebuilds `ol-carousel` on native scroll snapping and removes the
   transform. Either one unblocks this; the branch merges #13324 because the
   panel has to clear the carousel *and* the section below it. **This branch
   cannot ship before #13324 lands.**

7. **An N+1 nobody had noticed.** `work_search.html` bulk-loads shelf statuses
   via `add_read_statuses()` — one query stamping `readinglog` on every doc — and
   `my_books/dropper.html` then discarded it and called
   `get_patrons_work_read_status()` per book. **Twenty redundant queries on every
   logged-in search page**, in production. Fixed in `fcfd352f0`. A second N+1
   remains: `get_latest_read_date()` per book for the check-in prompt.

---

## 15. Ecosystem — overlapping work in flight

> Snapshot as of 10 Aug 2026, from a sweep of open issues and PRs.
> **Re-check states before acting.** Not independently verified in this branch.

### The headline

**Mek and Sadashii are actively rewriting the same access-button code this audit
targets, right now, with a different vocabulary.** PRs **#12867 → #13113** (CTA-card
consolidation, from issue **#12826**) and **#12914** vs **#12191** (two competing
implementations of the Locate rename, from **#12105**) all modify
`LoanStatus.html`, `ReadButton.html` and `databarWork.html` — the exact files in
Phase 0/1. They are not hostile to the audit's goals, but they encode different
answers to the same questions, and whichever lands first sets the baseline the
other has to rebase onto.

### Where outstanding work supports the audit

- **#8582 — "Add Want to Read dropper to carousels."** Open since 2023, blocked
  on *Needs: Designs*. This is **F2 / Phase 2**. The audit is literally the design
  document this issue has been waiting on — the strongest evidence of existing
  demand, and Phase 2 closes it.
- **#13179 / PR #13289 — borrowable-edition boosting in `get_best_edition`.**
  Complementary and upstream: it reduces how often the access slot lands on a dead
  state at all, while the audit fixes what a dead state looks like when
  unavoidable. No file overlap.
- **#9039 — dropper state inconsistent between search results and book page.**
  A single `BookActions` with one client-side hydration path (Phase 2) is the
  structural fix for this class of bug.
- **#11615 — unify per-provider download-options templates.** Directly helps the
  menu's *More ways to read → Download options* group: one template to slot in
  instead of seven. **Worth landing before Phase 1** so the menu builds on it.
- **#8884 — search-inside preview card in search results.** Aligned with F13.
  The audit gives it a home: the *More ways to read* group plus the state line.
- **#13240 — UI-modernization epic** explicitly names inconsistent buttons; the
  audit slots under it as the book-actions workstream.

**Merged baseline that helps:** **#12764** (preserve intent) is what makes the F4
fix pay off — the clicked label now matches the resumed action, which should move
the **#13261 / #13264** login-funnel numbers. **#13116 / #13029** (aria-labels)
are carried forward and superseded by the `ol-popover` swap, which adds the
`aria-expanded` / `aria-controls` those fixes couldn't.

### Where they conflict

**PR #12867 (CTA card consolidation) — the big one.** Three direct contradictions:

1. It **suppresses Locate outside the book page** and shows "Not in Library"
   instead — the exact opposite of F8, which wires "Find in a library" into the
   works branch precisely because "Not in Library" is a dead `<span>` on the most
   common search result.
2. It renames Preview to **"Search Inside Preview"** — a compound noun outside
   the closed six-verb vocabulary.
3. It and its follow-on **#13113** add a **second disclosure** (a Buy
   `ol-popover`) next to the Borrow dropdown on the book page, violating rule 2
   (one disclosure per book). Its unavailable-state treatment (grey "Not
   Available" + Buy promoted to primary) also puts a status back in the button slot.

**#12914 vs #12191 vs the audit — three labels for one slot.** "Check WorldCat",
"Check Options" and "Find in a library" are all in flight for the same button.
Both PRs add per-surface conditionals to `LoanStatus.html` (guaranteed merge
conflicts with Phase 0), and both keep the split the audit is trying to remove —
different behaviour on book page vs everywhere else, decided by ad-hoc
conditionals rather than surface intent. The underlying issue **#12105** (route
Locate on-site instead of straight to WorldCat) is *compatible* — it only changes
the verb's destination — but the label needs one decision, not three.

**PR #12349 (loan-limit disabled button).** Replaces Borrow with a disabled
"Loan Limit Reached" button — a status wearing button clothes, the precise
antipattern of F7. The audit's answer: keep Borrow rendered per the decision
table, put "You've reached your 5-loan limit" on the state line. Stale and
awaiting submitter input, so a redirecting comment costs little.

**PR #13282 (Continue Reading read-tracking JS).** Hooks click listeners onto the
Read/Preview buttons. This branch rewrote `ReadButton`'s markup
(`<details>` → `<ol-popover>`); whichever merges second must re-verify selectors.
The Continue Reading carousels (**#13281**, **#13283**, issues **#13272 / #13273**)
also build new My Books carousels — the surface Phase 3 redeclares as
*manage / shelf-leads* (F3). Not contradictory, but they are pouring new cards
into the shell we are about to replace; they should consume `BookActions` rather
than add another bespoke card.

**Analytics coordination (#13261 / #13264).** This branch deletes the
`ReadingLog|AddToList` track value, and Phase 0 removes buttons that currently
emit `CTAClick` events. Fine — but the measurement plan depends on stable
baselines, so the tracking-slot additions should land *with* Phase 0, and whoever
owns #13264 should know the event vocabulary is about to shift.

---

## 16. Recommended next actions

**Coordination first — this is time-sensitive.**

1. **Post the audit on #12826 before #12867 / #13113 merge.** That design issue is
   marked *Needs: Design Feedback / Needs: Staff Decision* — it is the venue where
   the Locate-suppression and second-disclosure decisions get made, and right now
   they are being made without the audit's evidence.
2. **Force one decision on the Locate label** across #12105 / #12191 / #12914.
   "Find in a library" wired to whatever destination #12105 picks satisfies everyone.
3. **Attach the audit to #8582** to unblock it as Phase 2's tracking issue.
4. **Comment on #12349** proposing state-line treatment instead of a disabled button.
5. **Land #11615 first**; sequence Phase 1's `ReadButton` changes against #13282's selectors.

**Then, on this branch:**

6. Manually check the mobile bottom tray and focus restore (§13, unverified),
   and the narrow shape at phone widths — only desktop card widths were measured.
7. Land **#13324** (top layer). It gates F2; this branch merges it locally.
8. Phase 3 — the intent axis. It is what fixes F3, and it is what lets a
   `manage` card spend its state line on the shelf name (§7a).

---

## Appendix: file map

| Path | Owns | Phase |
|---|---|---|
| `openlibrary/core/lending.py:1051` | `get_lending_state()` — the 9 access states | Unchanged |
| `openlibrary/macros/BookActions.html` | **New.** The action column | 2, 3 |
| `openlibrary/macros/LoanStatus.html` | Access state → template dispatch, state line | 0, 1, 2 |
| `openlibrary/macros/ReadButton.html` | Read / Borrow / Listen + overflow | 0, 1 |
| `openlibrary/macros/LocateButton.html` | Find in a library, two-tier destination | 0 |
| `openlibrary/macros/NotInLibrary.html` | *Deleted* | 0 |
| `openlibrary/macros/BookPreview.html` | Preview | 0 |
| `openlibrary/macros/PreviewSearchInside.html` | Preview + Search inside pair | 3 |
| `openlibrary/templates/book_providers/read_button.html` | Partner-provider access + host-naming caption | 0, 1 |
| `openlibrary/templates/my_books/primary_action.html` | Shelf button label, logged-out branch, `redir` | 0, 1 |
| `openlibrary/templates/my_books/dropdown_content.html` | Menu contents, `redir` | 0, 1 |
| `openlibrary/templates/my_books/dropper.html` | Shelf state, precomputed-status params | 2 |
| `openlibrary/templates/lib/dropper.html` | Disclosure shell (`ol-popover`) | 1 |
| `openlibrary/macros/SearchResultsWork.html` | Row shell for S1–S8, S14 | 0, 2, 3 |
| `openlibrary/templates/books/custom_carousel_card.html` | Card shell for S9, S10 | 2, 3 |
| `openlibrary/templates/books/mobile_carousel.html` | Card shell for S11 | 3 |
| `openlibrary/templates/books/edition-sort.html` | Editions table rows | 3 |
| `openlibrary/macros/databarWork.html` | Book page sidebar | 3 |
| `openlibrary/components/lit/OlPopover.js` | Disclosure behaviour; **needs top layer for F2** | 2 |
| `openlibrary/components/lit/OLButton.js` | Button variants | Reuse |
| `static/css/components/generic-dropper.css` | Dropper + read-button overflow | 0, 1 |
| `static/css/components/buttonCta.css` | `.cta-btn`, `.cta-state` | 0 |
| `static/css/components/book-actions.css` | **New.** Action-column layout and the density rule | 2 |
| `static/css/components/carousel.css` | Card shell; the `> button` scoping fix | 2 |
| `static/css/page-{home,subject,book}.css` | Bundles that render a book and now need the dropper | 2 |
| `static/css/legacy.css:1525` | Grid-layout suppression | 3 — remove |
| `openlibrary/plugins/openlibrary/js/dropper/Dropper.js` | Bridge to `ol-popover` | 1 |
| `openlibrary/plugins/openlibrary/js/my-books/MyBooksDropper/*` | Shelf forms, check-ins, lists | 1, 2 |
| `openlibrary/tests/test_book_action_disclosures.py` | **New.** Macro-level regression tests | 0, 1, 2 |
