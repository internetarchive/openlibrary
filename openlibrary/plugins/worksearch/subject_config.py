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
        "tagline": ("Worlds reshaped by science and possibility — from near-future technothrillers to galaxy-spanning epics."),
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
                    {"name": "Hard SF", "slug": "hard_science_fiction", "icon": "atom", "blurb": "Rigorous science, big ideas."},
                    {"name": "First Contact", "slug": "first_contact", "icon": "satellite-dish", "blurb": "Meeting the truly alien."},
                    {"name": "Time Travel", "slug": "time_travel", "icon": "hourglass", "blurb": "Paradoxes and second chances."},
                ],
            },
            {
                "label": "Epic & adventurous",
                "items": [
                    {"name": "Space Opera", "slug": "space_opera", "icon": "rocket", "blurb": "Galaxy-spanning sweep."},
                    {"name": "Military SF", "slug": "military_science_fiction", "icon": "swords", "blurb": "War among the stars."},
                    {"name": "Space Exploration", "slug": "space_exploration", "icon": "telescope", "blurb": "Out past the edge of the map."},
                ],
            },
            {
                "label": "Dark & cautionary",
                "items": [
                    {"name": "Dystopian", "slug": "dystopian", "icon": "eye", "blurb": "Futures that went wrong."},
                    {"name": "Post-Apocalyptic", "slug": "post-apocalyptic", "icon": "radiation", "blurb": "After the fall."},
                    {"name": "Climate Fiction", "slug": "climate_fiction", "icon": "thermometer-sun", "blurb": "Stories for a warming world."},
                ],
            },
            {
                "label": "Future & street-level",
                "items": [
                    {"name": "Cyberpunk", "slug": "cyberpunk", "icon": "cpu", "blurb": "High tech, low life."},
                    {"name": "Dystopias", "slug": "science_fiction_dystopias", "icon": "building-2", "blurb": "Boots on neon streets."},
                    {"name": "Artificial Intelligence", "slug": "artificial_intelligence", "icon": "bot", "blurb": "Minds we made."},
                ],
            },
        ],
        "collections": [
            {
                "title": "Reader favorites",
                "caption": "The science fiction Open Library readers return to most.",
                "query": "subject_key:science_fiction",
                "sort": "readinglog",
            },
            {
                "title": "Hugo Award winners",
                "caption": "Science fiction's most celebrated honor, voted by fans.",
                "badge": "Award winner",
                "query": 'subject:"Hugo Award" OR subject:"Hugo Awards"',
                "sort": "readinglog",
            },
            {
                "title": "Nebula Award winners",
                "caption": "Chosen by the writers of the field themselves.",
                "badge": "Award winner",
                "query": 'subject:"Nebula Award" OR subject:"Nebula Awards"',
                "sort": "readinglog",
            },
            {
                "title": "Cyberpunk essentials",
                "caption": "Neon, networks, and corporate dystopia.",
                "query": 'subject_key:cyberpunk OR subject:"Cyberpunk"',
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
        "tagline": ("Magic, myth, and the impossible — from cozy found-family tales to grim empires and world-ending wars."),
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
                    {"name": "Cozy Fantasy", "slug": "cozy_fantasy", "icon": "house", "blurb": "Low stakes, warmth, found family."},
                    {"name": "Fairy Tales", "slug": "fairy_tales", "icon": "wand-sparkles", "blurb": "Old stories, retold."},
                ],
            },
            {
                "label": "Romantic",
                "items": [
                    {"name": "Romantasy", "slug": "romantic_fantasy", "icon": "heart", "blurb": "Romance with real fantasy stakes."},
                    {"name": "Paranormal", "slug": "paranormal_romance", "icon": "ghost", "blurb": "Love among the supernatural."},
                ],
            },
            {
                "label": "Epic",
                "items": [
                    {"name": "High Fantasy", "slug": "high_fantasy", "icon": "castle", "blurb": "Big worlds, big quests."},
                    {"name": "Epic Fantasy", "slug": "epic_fantasy", "icon": "mountain", "blurb": "Sweeping, multi-book sagas."},
                ],
            },
            {
                "label": "Dark & strange",
                "items": [
                    {"name": "Grimdark", "slug": "dark_fantasy", "icon": "skull", "blurb": "Morally grey, often brutal."},
                    {"name": "Urban Fantasy", "slug": "urban_fantasy", "icon": "building-2", "blurb": "Magic in the modern city."},
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
                "query": 'subject_key:cozy_fantasy OR subject:"Cozy fantasy"',
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
    "romance": {
        "tagline": ("Love at the center, a happy ending guaranteed — from slow-burn historicals to steamy contemporaries and everything between."),
        "description": (
            "<p>Romance is the literature of relationships and emotional payoff. "
            "Its one firm promise — a happy or hopeful ending — is exactly what "
            "lets it take big emotional risks along the way.</p>"
            "<p>What changes wildly from book to book is the <em>texture</em>: the "
            "heat level, the trope, the setting, and how much angst you're in the "
            "mood for. The flavors below are the fastest way to the right shelf.</p>"
        ),
        "flavors": [
            {
                "label": "By setting",
                "items": [
                    {"name": "Contemporary", "slug": "contemporary_romance", "icon": "coffee", "blurb": "Here and now."},
                    {"name": "Historical", "slug": "historical_romance", "icon": "crown", "blurb": "Regency ballrooms and beyond."},
                    {"name": "Paranormal", "slug": "paranormal_romance", "icon": "ghost", "blurb": "Love among the supernatural."},
                ],
            },
            {
                "label": "By heat",
                "items": [
                    {"name": "Sweet / closed-door", "slug": "clean_romance", "icon": "heart", "blurb": "Chemistry, no explicit scenes."},
                    {"name": "Steamy", "slug": "erotic_romance", "icon": "flame", "blurb": "Turn up the temperature."},
                ],
            },
            {
                "label": "By mood",
                "items": [
                    {"name": "Romantic comedy", "slug": "romantic_comedy", "icon": "laugh", "blurb": "Banter and laughs."},
                    {"name": "Romantic suspense", "slug": "romantic_suspense", "icon": "venetian-mask", "blurb": "Love with the stakes high."},
                ],
            },
        ],
        "collections": [
            {
                "title": "Reader favorites",
                "caption": "The romances Open Library readers love most.",
                "query": "subject_key:romance",
                "sort": "readinglog",
            },
            {
                "title": "Historical romance",
                "caption": "Dukes, scandal, and slow-burn longing.",
                "query": 'subject_key:historical_romance OR subject:"Historical romance"',
                "sort": "readinglog",
            },
            {
                "title": "Paranormal romance",
                "caption": "Vampires, shifters, and fated mates.",
                "query": 'subject_key:paranormal_romance OR subject:"Paranormal romance"',
                "sort": "readinglog",
            },
            {
                "title": "Short & sweet standalones",
                "caption": "Under ~350 pages, no series to commit to.",
                "query": "subject_key:romance -series_name:* number_of_pages:[1 TO 350]",
                "sort": "readinglog",
            },
            {
                "title": "Just published",
                "caption": "The newest romance in the catalog.",
                "query": "subject_key:romance",
                "sort": "new",
            },
            {
                "title": "Read it right now",
                "caption": "Borrow or read these instantly on Open Library.",
                "query": "subject_key:romance",
                "sort": "readinglog",
                "has_fulltext_only": True,
            },
        ],
    },
    "mystery": {
        "tagline": ("A puzzle, a crime, a secret to crack — from gentle cozies to pulse-pounding psychological thrillers."),
        "description": (
            "<p>Mystery is the genre of questions and answers: a wrong to set "
            "right, clues to follow, and the satisfaction of a solution. It runs "
            "from warm, low-violence “cozies” to bleak noir and twisty domestic "
            "suspense.</p>"
            "<p>Readers usually know the <em>intensity</em> they want before the "
            "plot — gentle and puzzle-like, or dark and tense. Start with a flavor "
            "below.</p>"
        ),
        "flavors": [
            {
                "label": "Gentle & puzzle-like",
                "items": [
                    {"name": "Cozy mystery", "slug": "cozy_mystery", "icon": "coffee", "blurb": "Amateur sleuths, low gore."},
                    {"name": "Detective", "slug": "detective_and_mystery_stories", "icon": "search", "blurb": "Classic whodunits."},
                ],
            },
            {
                "label": "Gritty & hardboiled",
                "items": [
                    {"name": "Noir", "slug": "noir_fiction", "icon": "moon", "blurb": "Shadows and moral grey."},
                    {"name": "Police procedural", "slug": "police_procedural", "icon": "fingerprint", "blurb": "The case, step by step."},
                ],
            },
            {
                "label": "Twisty & tense",
                "items": [
                    {"name": "Psychological thriller", "slug": "psychological_thriller", "icon": "brain", "blurb": "Unreliable narrators."},
                    {"name": "Legal thriller", "slug": "legal_thriller", "icon": "gavel", "blurb": "The courtroom as battlefield."},
                ],
            },
        ],
        "collections": [
            {
                "title": "Reader favorites",
                "caption": "The mysteries Open Library readers can't put down.",
                "query": "subject_key:mystery OR subject_key:detective_and_mystery_stories",
                "sort": "readinglog",
            },
            {
                "title": "Edgar Award winners",
                "caption": "The genre's top honor, from the Mystery Writers of America.",
                "badge": "Award winner",
                "query": 'subject:"Edgar Award" OR subject:"Edgar Awards"',
                "sort": "readinglog",
            },
            {
                "title": "Cozy mysteries",
                "caption": "Small towns, big secrets, very little gore.",
                "query": 'subject_key:cozy_mystery OR subject:"Cozy mysteries"',
                "sort": "readinglog",
            },
            {
                "title": "Short standalones",
                "caption": "Under ~350 pages and not part of a series.",
                "query": "subject_key:mystery -series_name:* number_of_pages:[1 TO 350]",
                "sort": "readinglog",
            },
            {
                "title": "Just published",
                "caption": "The newest mysteries in the catalog.",
                "query": "subject_key:mystery",
                "sort": "new",
            },
            {
                "title": "Read it right now",
                "caption": "Borrow or read these instantly on Open Library.",
                "query": "subject_key:mystery",
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
