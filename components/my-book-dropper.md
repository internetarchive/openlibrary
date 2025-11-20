# My Books Dropper

The **My Books Dropper** (see https://github.com/internetarchive/openlibrary/pull/8019) is a reusable component that lets patrons categorize a book (at either Edition (default) or Work level) within the shelves ("Want to Read", "Currently Reading", "Already Read", and custom lists) of their personal library.

<img width="400"  alt="image" src="https://github.com/user-attachments/assets/dde8af06-5aed-4775-817b-dc4a87e5312a" />

## Usage

```html
$include('my_books/dropper.html', page=page, edition_key=page.olid, async_load=False)
```

## Where It's Used

Graphics, code snippets, and notes would be useful for each of the following:

1. Book Pages
2. Search Results*
3. Lists & Reading Log Shelves*
4. Author Pages Books*

*_many compact droppers rendered next to each item; these frequently rely on async inner loading to remain performant._

## Technical

The **My Books Dropper** -- implemented and DOCUMENTED in https://github.com/internetarchive/openlibrary/pull/8019 -- extends the generic Dropper comprised of a primary button and dropdown content. The template for the dropper takes a rendered HTML string for each of these.  The template also takes a additional classes as a string, enabling the dropper to be styled as needed.

![generic-dropper-parts](https://github.com/internetarchive/openlibrary/assets/28732543/3a4df71a-aa6c-42de-bb58-8880ef86f5db)

Visibility of the dropdown content can be changed by clicking the "dropclick" arrow.  If a patron clicks outside of the dropper component when the dropdown is visible, it will be hidden.  This functionality is business as usual (BAU).  What is new is that dropdown visibility can now be changed with 'toggle-dropper` and `close-dropper` events.  Using these new event is as easy as passing a reference to a child element of a dropper to the `fireDropperToggleEvent` and `fireDropperCloseEvent` functions, which dispatch the appropriate event from the given element to the parent dropper.

The new template for generic droppers is `/openlibrary/templates/lib/dropper.html`.  All BAU dropper functionality will automatically be added to components created using that template.

## Overview of Files

### Templates

Server-side templates that output the HTML structure and server-initialized pieces

  - my_books/dropper.html — main dropper template (structure/data attrs). See:
    https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/templates/my_books/dropper.html#L1-L24
    - Role: server-side dropper wrapper; computes seed keys, user lists (or placeholders for async load), CSS classes, and outputs initial dropdown markup.

  The generic dropper is defined by:
  - my_books/dropdown_content.html — the **generic** dropper dropdown **content** (reading-log forms / Want to Read buttons).
    https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/templates/my_books/dropdown_content.html#L18-L33
    - Role: actual forms and buttons for adding/removing from shelves (shelf IDs, hidden fields, etc).
  - lib/dropper.html — **generic** dropper wrapper used as the HTML skeleton for droppers.
    https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/templates/lib/dropper.html#L1-L22
    - Role: generic primary-button + dropdown HTML structure the My Books templates use.

  Internationalization for the My Books Dropper:
  - openlibrary/i18n/messages.pot and **i18n** language .po files (e.g., hi/messages.po) contain “Want to Read”, “Currently Reading”, and “Already Read” references (helpful to find template usages).
    https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/i18n/messages.pot#L1513-L1546

### CSS

https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/static/css/components/mybooks-dropper.less

### JavaScript

Client-side JS hydrates the dropper, wires actions, loads user lists asynchronously and manages UI state

  - plugins/openlibrary/js/my-books/MyBooksDropper.js
    https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/plugins/openlibrary/js/my-books/MyBooksDropper.js#L1-L21
    - Role: main class for each dropper instance. Hydrates dropper contents, starts loading animations, and coordinates the reading-list and reading-log subcomponents.
  - plugins/openlibrary/js/my-books/MyBooksDropper/ReadingLists.js
    https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/plugins/openlibrary/js/my-books/MyBooksDropper/ReadingLists.js#L92-L110
    - Role: list affordances (modify-list handlers, create-new-list modal link, show/hide lists).
  - plugins/openlibrary/js/my-books/MyBooksDropper/ReadingLogForms.js
    https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/plugins/openlibrary/js/my-books/MyBooksDropper/ReadingLogForms.js#L1-L30
    - Role: reading-log forms behavior and shelf constants (e.g., WANT_TO_READ / CURRENTLY_READING / ALREADY_READ).
  - plugins/openlibrary/js/index.js — site entry: lazy-loads the my-books chunk when .my-books-dropper exists.
    https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/plugins/openlibrary/js/index.js#L343-L364

### Backend

Partials (Server-side templates render the HTML fragments that populate the dropper dropdown) are used to async load a patron's lists per dropper when multiple droppers exist on a page and would otherwise be expensive/redundant to compete fetch data individually.

See `/partials.json?_component=MyBooksDropperLists`
The `ListService` client helper `getListPartials()` calls fetch(buildPartialsUrl('MyBooksDropperLists')) using `buildPartialsUrl` defined in `plugins/openlibrary/js/utils.js`.

Endpoints (for `POST`ing when various actions are taken within the dropper)

1. `<work_key>/bookshelves.json` to (re)shelf a book
  *  add/remove the current work/edition to/from a reading shelf (Want to Read / Currently Reading / Already Read)
  *  https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/plugins/openlibrary/api.py#L296-L362
2. `{listKey}/seeds.json` to add/remove books from/to a list
  * https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/plugins/openlibrary/lists.py#L586-L628
3. `/lists` to create a new list
  * https://github.com/internetarchive/openlibrary/blob/5d13f226cb61ccb4cbd8f74e3a01cd2e3dfa7675/openlibrary/plugins/openlibrary/lists.py#L309-L339

