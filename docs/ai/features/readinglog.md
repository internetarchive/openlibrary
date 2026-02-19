# Reading Log Feature

The Reading Log feature allows Open Library users to track books they want to read, are currently reading, and have finished reading.

## Overview

The Reading Log consists of three preset shelves:

- **Want to Read** (ID: 1) - Books the user wants to read
- **Currently Reading** (ID: 2) - Books the user is currently reading
- **Already Read** (ID: 3) - Books the user has finished reading

Users can mark books as private or public in their account preferences.

## Key Files

### Core Models & Database

| File                                     | Purpose                                                                                                                                                                                                 |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `openlibrary/core/bookshelves.py`        | Core Bookshelves model and database operations. Contains `Bookshelves` class with methods like `add()`, `remove()`, `get_users_logged_books()`, `get_work_summary()`, `get_users_read_status_of_work()` |
| `openlibrary/core/bookshelves_events.py` | Reading check-in events (start/finish reading). Contains `BookshelvesEvents` class for tracking reading progress                                                                                        |
| `openlibrary/core/models.py`             | Defines `BookshelvesModel` and `BookshelvesEventsModel` classes                                                                                                                                         |

### API Endpoints

| File                                          | Purpose                                                                                                               |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `openlibrary/plugins/openlibrary/api.py:288`  | `work_bookshelves` class - GET/POST to `/works/OL{id}W/bookshelves.json` for adding/removing books and getting counts |
| `openlibrary/plugins/upstream/checkins.py:60` | `patron_check_ins` class - POST/DELETE to `/works/OL{id}W/check-ins` for reading progress events                      |
| `openlibrary/plugins/upstream/mybooks.py:303` | `public_my_books_json` class - GET `/people/{username}/books/{shelf}` for public reading logs                         |

### Page Handlers & Templates

| File                                                   | Purpose                                                                                                      |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| `openlibrary/plugins/upstream/mybooks.py`              | Page handlers for My Books UI: `mybooks_home`, `mybooks_readinglog`, `readinglog_yearly`, `readinglog_stats` |
| `openlibrary/templates/account/reading_log.html`       | Reading log page template                                                                                    |
| `openlibrary/templates/account/reading_log_notes.html` | Reading log notes template                                                                                   |
| `openlibrary/templates/my_books/dropdown_content.html` | Shelf selection dropdown in the UI                                                                           |

### Frontend JavaScript

| File                                          | Purpose                                                         |
| --------------------------------------------- | --------------------------------------------------------------- |
| `openlibrary/plugins/openlibrary/js/index.js` | Contains `syncReadingLogDropdown()` function for dropdown state |
| `openlibrary/plugins/openlibrary/js/live.js`  | Reading log related JavaScript                                  |
| `static/css/components/readinglog-stats.less` | Reading log stats styles                                        |
| `static/css/components/mybooks-dropper.less`  | Styles for the "Add to list" dropdown                           |

## Milestone Commits & PRs

| Commit      | PR     | Date     | Description                                                                                |
| ----------- | ------ | -------- | ------------------------------------------------------------------------------------------ |
| `fe4445053` | -      | Oct 2017 | Initial reading log implementation - Want to Read, Currently Reading, Already Read buttons |
| `49eaed112` | -      | 2019     | Adding `/books/already-read/year/{year}` page                                              |
| `5a81731cc` | -      | Feb 2020 | Add GET `/works/OL1W/bookshelves.json` API for bookshelf counts                            |
| `#7052`     | #7052  | ~2020    | Adds search capability to reading log                                                      |
| `#7115`     | #7115  | ~2020    | Manual reading log check-ins                                                               |
| `#7139`     | #7139  | ~2020    | My Books mobile redesign + carousels                                                       |
| `#7565`     | #7565  | ~2020    | Add 'Remove From Shelf' option                                                             |
| `#8539`     | #8539  | ~2021    | Remove legacy reading log dropper code + "My Books Dropper" feature flag                   |
| `#8628`     | #8628  | ~2021    | Boost search via reading log                                                               |
| `#8639`     | #8639  | ~2021    | Add year selector to "Already Read"                                                        |
| `#8821`     | #8821  | ~2021    | Show editions in reading log                                                               |
| `#8918`     | #8918  | ~2021    | Fix private reading log errors                                                             |
| `#9046`     | #9046  | ~2021    | Reduce default limit to 100                                                                |
| `#9519`     | #9553  | ~2022    | Update reading log shelf on star rating                                                    |
| `#11057`    | #11057 | ~2023    | Handle deleted books in reading log                                                        |
| `#11322`    | #11322 | ~2023    | Fix reading log exports                                                                    |

## Key Functions

### Bookshelves (openlibrary/core/bookshelves.py)

```python
# Add a book to a user's shelf
Bookshelves.add(username, bookshelf_id, work_id, edition_id=None)

# Remove a book from a user's shelf
Bookshelves.remove(username, work_id, bookshelf_id)

# Get paginated list of a user's logged books
Bookshelves.get_users_logged_books(user, shelf_key, page, limit, query)

# Get count of users on each shelf for a work
Bookshelves.get_work_summary(work_id)

# Get which shelf a user has placed a work on
Bookshelves.get_users_read_status_of_work(username, work_id)
```

### BookshelvesEvents (openlibrary/core/bookshelves_events.py)

```python
# Create a check-in event
BookshelvesEvents.create_event(username, work_id, edition_id, date_str, event_type)

# Update a check-in event
BookshelvesEvents.update_event(event_id, event_date, edition_id)

# Delete a check-in event
BookshelvesEvents.delete_by_id(event_id)

# Get user's yearly reading counts
BookshelvesEvents.get_user_yearly_read_counts(username)
```

## Database Schema

The reading log uses the following main tables:

- `bookshelves` - User bookshelf entries
- `bookshelf_events` - Reading check-in events (start/finish/progress)

See `openlibrary/sql/schema.sql` for the full schema.

## Feature Flags

Key feature flags (checked in `openlibrary/plugins/upstream/mybooks.py`):

- `enable_mybooks_dropper` - New "Add to list" dropdown functionality
- `compact_mode` - Compact display in carousels

## Related Documentation

- [Reading Log API Docs](/docs/apis/readinglog)
- [My Books Help](https://openlibrary.org/help/faq/using-library#readinglog)
- [Swagger Docs](/swagger/docs)
