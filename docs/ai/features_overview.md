# Features Overview

This document provides a high-level inventory of Open Library's main features. Use this as a starting point when developing or modifying any feature.

## What is Open Library?

Open Library (openlibrary.org) is an open, editable library catalog by the Internet Archive. It provides:

- A catalog of every book ever published
- Borrowing of ebooks to logged-in users
- User collections (lists, reading logs)
- Community editing and curation

## Feature Inventory

| Feature                | Plugin/Controller                                       | Model                                                             | README                                                                                                |
| ---------------------- | ------------------------------------------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Home                   | `openlibrary/plugins/openlibrary/home.py`               | —                                                                 | —                                                                                                     |
| My Books / Reading Log | `openlibrary/plugins/upstream/mybooks.py`               | `openlibrary/core/bookshelves.py`                                 | [Developing the Reading Log](https://docs.openlibrary.org/5_Projects/Developing-the-Reading-Log.html) |
| Books (Works/Editions) | `openlibrary/plugins/books/code.py`                     | —                                                                 | —                                                                                                     |
| Authors                | `openlibrary/plugins/worksearch/code.py`                | —                                                                 | —                                                                                                     |
| Subjects               | `openlibrary/plugins/worksearch/subjects.py`            | —                                                                 | —                                                                                                     |
| Lists                  | `openlibrary/plugins/openlibrary/lists.py`              | —                                                                 | —                                                                                                     |
| Trending               | `openlibrary/plugins/openlibrary/home.py`               | —                                                                 | —                                                                                                     |
| Library Explorer       | `openlibrary/plugins/openlibrary/js/LibraryExplorer.js` | —                                                                 | —                                                                                                     |
| Borrowing/Loans        | `openlibrary/plugins/upstream/borrow.py`                | `openlibrary/core/lending.py`                                     | —                                                                                                     |
| Fulltext Search        | `openlibrary/plugins/worksearch/code.py`                | —                                                                 | —                                                                                                     |
| Barcode Scanner        | `openlibrary/plugins/worksearch/code.py`                | —                                                                 | —                                                                                                     |
| Account/Profile        | `openlibrary/plugins/upstream/account.py`               | —                                                                 | —                                                                                                     |
| Following/Activity     | `openlibrary/plugins/upstream/account.py`               | `openlibrary/core/follows.py`                                     | —                                                                                                     |
| Add Book               | `openlibrary/plugins/upstream/addbook.py`               | —                                                                 | —                                                                                                     |
| Reading Goals          | `openlibrary/plugins/upstream/yearly_reading_goals.py`  | `openlibrary/core/yearly_reading_goals.py`                        | —                                                                                                     |
| Ratings/Reviews        | —                                                       | `openlibrary/core/ratings.py`, `openlibrary/core/observations.py` | —                                                                                                     |
| Admin                  | `openlibrary/plugins/admin/code.py`                     | `openlibrary/core/admin.py`                                       | —                                                                                                     |

---

For general development guidance (where to find routes, templates, models, tests), see [docs/ai/README.md](README.md).

---

_This is a living document. Add feature documentation as you learn them._
