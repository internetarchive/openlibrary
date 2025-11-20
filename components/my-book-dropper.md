# My Books Dropper

The **My Books Dropper** is a reusable component that lets patrons categorize a book (at either Edition (default) or Work level) within the shelves ("Want to Read", "Currently Reading", "Already Read", and custom lists) of their personal library.

<img width="400"  alt="image" src="https://github.com/user-attachments/assets/dde8af06-5aed-4775-817b-dc4a87e5312a" />

## Usage

```html
<!-- Example: include the dropper in a template that has `page` available.
     The actual include mechanism depends on the template you're editing; a common pattern is to
     render the my_books/dropper.html fragment and pass page and edition_key as needed.

     PSEUDOCODE (adapt to the template language in the file you're editing):
     $include('my_books/dropper.html', page=page, edition_key=page.olid, async_load=False)
-->
$include('my_books/dropper.html', page=page, edition_key=page.olid, async_load=False)
```

## Where It's Used



## Technical 

The **My Books Dropper** -- primarily implemented in https://github.com/internetarchive/openlibrary/pull/8019 -- extends the generic Dropper comprised of a primary button and dropdown content. The template for the dropper takes a rendered HTML string for each of these.  The template also takes a additional classes as a string, enabling the dropper to be styled as needed. 

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

Partials (for async loading a patron's lists per dropper)
- TODO

Endpoints (for POSTing when various actions are taken within the dropper)
- TODO
