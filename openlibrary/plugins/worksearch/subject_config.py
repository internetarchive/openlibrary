"""Editorial content for featured subject pages.

This is a hand-curated "genre dashboard" layer that sits on top of the
data-driven subject page. It lets us show off the ideal genre-page experience
(rich description, a subgenre map, and curated bookstore-style collections)
for a small set of flagship subjects without requiring new schema or data.

Only a handful of subjects need entries here; every other subject falls back to
the generic, signal-driven intent rails in ``subjects.html``.

Each collection's ``query`` is a normal Open Library search query, so the books
are real and live. The *curation* — which collections exist, how they're framed,
the subgenre map, and the prose — is what's authored here. Award collections
(e.g. Hugo/Nebula) lean on award subject tags present in the catalog; where
coverage is thin they act as an illustrative mock of the target experience and
can later be replaced with hand-picked work lists via an optional ``works`` key.
"""

import web

__all__ = ["get_featured_subject"]


FEATURED_SUBJECTS: dict[str, dict] = {
    "science_fiction": {
        "tagline": (
            "Worlds reshaped by science and possibility — from near-future "
            "technothrillers to galaxy-spanning epics."
        ),
        "description": (
            "<p>Science fiction asks <em>what if?</em> and follows the answer "
            "wherever it leads: to distant planets, far futures, alternate "
            "histories, and the frontiers of the mind. At its best it uses the "
            "tools of the impossible to say something true about who we are and "
            "where we're headed.</p>"
            "<p>It's a sprawling genre. You'll find rigorous, idea-driven "
            "“hard” SF sitting beside pulpy space adventure, bleak "
            "dystopias beside hopeful futures, and quiet character studies "
            "beside wars across galaxies. Use the subgenres below to find the "
            "corner that fits the mood you're in.</p>"
        ),
        "flavors": [
            {
                "label": "Cerebral & idea-driven",
                "items": [
                    {"name": "Hard SF", "slug": "hard_science_fiction", "blurb": "Rigorous science, big ideas."},
                    {"name": "First Contact", "slug": "first_contact", "blurb": "Meeting the truly alien."},
                    {"name": "Time Travel", "slug": "time_travel", "blurb": "Paradoxes and second chances."},
                ],
            },
            {
                "label": "Epic & adventurous",
                "items": [
                    {"name": "Space Opera", "slug": "space_opera", "blurb": "Galaxy-spanning sweep."},
                    {"name": "Military SF", "slug": "military_science_fiction", "blurb": "War among the stars."},
                    {"name": "Space Exploration", "slug": "space_exploration", "blurb": "Out past the edge of the map."},
                ],
            },
            {
                "label": "Dark & cautionary",
                "items": [
                    {"name": "Dystopian", "slug": "dystopian", "blurb": "Futures that went wrong."},
                    {"name": "Post-Apocalyptic", "slug": "post-apocalyptic", "blurb": "After the fall."},
                    {"name": "Climate Fiction", "slug": "climate_fiction", "blurb": "Stories for a warming world."},
                ],
            },
            {
                "label": "Future & street-level",
                "items": [
                    {"name": "Cyberpunk", "slug": "cyberpunk", "blurb": "High tech, low life."},
                    {"name": "Dystopias", "slug": "science_fiction_dystopias", "blurb": "Boots on neon streets."},
                    {"name": "Artificial Intelligence", "slug": "artificial_intelligence", "blurb": "Minds we made."},
                ],
            },
        ],
        "collections": [
            {
                "title": "Hugo Award winners",
                "caption": "Science fiction's most celebrated honor, voted by fans.",
                "badge": "Award winner",
                "query": 'subject:"Hugo Award Winner" OR subject:"Hugo Award"',
                "sort": "readinglog",
            },
            {
                "title": "Nebula Award winners",
                "caption": "Chosen by the writers of the field themselves.",
                "badge": "Award winner",
                "query": 'subject:"Nebula Award Winner" OR subject:"Nebula Award"',
                "sort": "readinglog",
            },
            {
                "title": "Cyberpunk essentials",
                "caption": "Neon, networks, and corporate dystopia.",
                "query": "subject_key:cyberpunk",
                "sort": "readinglog",
            },
            {
                "title": "Short standalones",
                "caption": "Under ~350 pages, no series commitment — perfect for a first taste.",
                "query": "subject_key:science_fiction -series_name:* number_of_pages:[1 TO 350]",
                "sort": "readinglog",
            },
            {
                "title": "Just published",
                "caption": "The newest science fiction to land in the catalog.",
                "query": "subject_key:science_fiction",
                "sort": "new",
            },
            {
                "title": "Read it right now",
                "caption": "Borrow or read these instantly on Open Library.",
                "query": "subject_key:science_fiction",
                "sort": "readinglog",
                "has_fulltext_only": True,
            },
        ],
    },
    "fantasy": {
        "tagline": (
            "Magic, myth, and the impossible — from cozy found-family tales to "
            "grim empires and world-ending wars."
        ),
        "description": (
            "<p>Fantasy is the literature of wonder: secondary worlds, hidden "
            "magic, old gods, and quests that test who we are. It stretches from "
            "comforting, low-stakes stories to brutal, morally complex epics.</p>"
            "<p>“Fantasy” covers wildly different reading experiences, "
            "so the subgenres below are the real map of the territory — pick the "
            "flavor you're after.</p>"
        ),
        "flavors": [
            {
                "label": "Comforting",
                "items": [
                    {"name": "Cozy Fantasy", "slug": "cozy_fantasy", "blurb": "Low stakes, warmth, found family."},
                    {"name": "Fairy Tales", "slug": "fairy_tales", "blurb": "Old stories, retold."},
                ],
            },
            {
                "label": "Romantic",
                "items": [
                    {"name": "Romantasy", "slug": "romantic_fantasy", "blurb": "Romance with real fantasy stakes."},
                    {"name": "Paranormal", "slug": "paranormal_romance", "blurb": "Love among the supernatural."},
                ],
            },
            {
                "label": "Epic",
                "items": [
                    {"name": "High Fantasy", "slug": "high_fantasy", "blurb": "Big worlds, big quests."},
                    {"name": "Epic Fantasy", "slug": "epic_fantasy", "blurb": "Sweeping, multi-book sagas."},
                ],
            },
            {
                "label": "Dark & strange",
                "items": [
                    {"name": "Grimdark", "slug": "dark_fantasy", "blurb": "Morally grey, often brutal."},
                    {"name": "Urban Fantasy", "slug": "urban_fantasy", "blurb": "Magic in the modern city."},
                ],
            },
        ],
        "collections": [
            {
                "title": "Reader favorites",
                "caption": "The fantasy books Open Library readers love most.",
                "query": "subject_key:fantasy",
                "sort": "readinglog",
            },
            {
                "title": "Cozy fantasy",
                "caption": "Low-stakes, high-comfort — tea, magic, and found family.",
                "query": "subject_key:cozy_fantasy OR subject:\"Cozy fantasy\"",
                "sort": "readinglog",
            },
            {
                "title": "Short standalones",
                "caption": "Under ~400 pages and not part of a series.",
                "query": "subject_key:fantasy -series_name:* number_of_pages:[1 TO 400]",
                "sort": "readinglog",
            },
            {
                "title": "Just published",
                "caption": "Fresh fantasy, newest first.",
                "query": "subject_key:fantasy",
                "sort": "new",
            },
            {
                "title": "Read it right now",
                "caption": "Borrow or read these instantly on Open Library.",
                "query": "subject_key:fantasy",
                "sort": "readinglog",
                "has_fulltext_only": True,
            },
        ],
    },
}


def _slug_from_key(key: str) -> str:
    """`/subjects/science_fiction` -> `science_fiction` (plain subjects only)."""
    slug = web.lstrips(key.lower(), "/subjects/")
    # Featured editorial only applies to plain subjects, not person:/place:/time:
    if ":" in slug or "/" in slug:
        return ""
    return slug


def get_featured_subject(key: str) -> dict | None:
    """Return editorial content for a subject pseudo-key, or None.

    >>> bool(get_featured_subject("/subjects/science_fiction"))
    True
    >>> get_featured_subject("/subjects/person:plato") is None
    True
    """
    slug = _slug_from_key(key)
    return FEATURED_SUBJECTS.get(slug)
