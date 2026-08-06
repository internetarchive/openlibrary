"""Seed a local dev instance with a populated social activity feed.

The stock ``load-patron-data.sh`` seeds the ``openlibrary`` account only, so
there is no second patron to follow and no social graph at all -- which makes
the activity feed impossible to look at locally. On top of that, the ~35 works
in a fresh dev Solr have no cover IDs, so even a populated feed renders as a
column of grey boxes.

This script fixes both: it indexes a set of real, cover-bearing works into the
local Solr core, creates several patrons with public reading logs, and gives
them reading-log events, ratings, lists, and a follow graph.

Run it from inside a worktree once the stack is up::

    docker compose run --rm home python scripts/dev-instance/seed_social_feed.py

Pass ``--viewer`` to control who ends up following the seeded patrons (defaults
to the ``openlibrary`` dev account), and ``--no-follows`` to leave the viewer
following nobody, which is how you exercise the public/not-following feed.
"""

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import web

from openlibrary.accounts import RunAs
from openlibrary.accounts.model import OpenLibraryAccount
from openlibrary.core import db
from openlibrary.core.follows import PubSub
from openlibrary.core.likes import Likes
from openlibrary.setup import setup_for_script
from openlibrary.utils.request_context import site

SOLR_URL = "http://solr:8983/solr/openlibrary"

# Real works pulled from production, trimmed to the fields the feed renders.
# Hard-coded rather than fetched so seeding works offline and is deterministic.
WORKS = [
    {
        "key": "/works/OL59800W",
        "title": "The Left Hand of Darkness",
        "author_name": ["Ursula K. Le Guin"],
        "author_key": ["OL31353A"],
        "cover_i": 10618463,
        "first_publish_year": 1969,
        "ia": ["lefthandofdarkne0000ursu_l8k8"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL12509193M"],
    },
    {
        "key": "/works/OL50548W",
        "title": "Beloved",
        "author_name": ["Toni Morrison"],
        "author_key": ["OL31120A"],
        "cover_i": 8261367,
        "first_publish_year": 1987,
        "ia": ["umiowana0000morr"],
        "has_fulltext": True,
        "ebook_access": "borrowable",
        "edition_key": ["OL58886319M"],
    },
    {
        "key": "/works/OL35616W",
        "title": "Kindred",
        "author_name": ["Octavia E. Butler", "SparkNotes"],
        "author_key": ["OL30802A", "OL2964716A"],
        "cover_i": 8745330,
        "first_publish_year": 1979,
        "ia": ["kindred00butl"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL40478931M"],
    },
    {
        "key": "/works/OL17762217W",
        "title": "Pachinko",
        "author_name": ["Min Jin Lee"],
        "author_key": ["OL2711131A"],
        "cover_i": 8044605,
        "first_publish_year": 2017,
        "ia": ["pachinko0000leem"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL62183991M"],
    },
    {
        "key": "/works/OL59038W",
        "title": "Never Let Me Go",
        "author_name": ["Kazuo Ishiguro"],
        "author_key": ["OL28493A"],
        "cover_i": 1047334,
        "first_publish_year": 2005,
        "ia": ["nuncameabandones0000ishi"],
        "has_fulltext": True,
        "ebook_access": "borrowable",
        "edition_key": ["OL62330757M"],
    },
    {
        "key": "/works/OL19074847W",
        "title": "The Overstory",
        "author_name": ["Richard Powers", "Richard Powers"],
        "author_key": ["OL873686A", "OL13933197A"],
        "cover_i": 8758252,
        "first_publish_year": 2018,
        "ia": [],
        "has_fulltext": False,
        "ebook_access": "no_ebook",
        "edition_key": ["OL53265567M"],
    },
    {
        "key": "/works/OL16819897W",
        "title": "Braiding Sweetgrass",
        "author_name": ["Robin Wall Kimmerer"],
        "author_key": ["OL2937464A"],
        "cover_i": 7281575,
        "first_publish_year": 2013,
        "ia": ["braidingsweetgra0000robi"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL51172427M"],
    },
    {
        "key": "/works/OL20893680W",
        "title": "Piranesi",
        "author_name": ["Susanna Clarke"],
        "author_key": ["OL1387961A"],
        "cover_i": 10226290,
        "first_publish_year": 2020,
        "ia": [],
        "has_fulltext": False,
        "ebook_access": "no_ebook",
        "edition_key": ["OL57673802M"],
    },
    {
        "key": "/works/OL17202418W",
        "title": "Station Eleven",
        "author_name": ["Emily St. John Mandel"],
        "author_key": ["OL6538530A"],
        "cover_i": 7369961,
        "first_publish_year": 2014,
        "ia": ["stationeleven0000mand"],
        "has_fulltext": False,
        "ebook_access": "unclassified",
        "edition_key": ["OL45686302M"],
    },
    {
        "key": "/works/OL17363125W",
        "title": "The Fifth Season",
        "author_name": ["N. K. Jemisin"],
        "author_key": ["OL6575473A"],
        "cover_i": 8133598,
        "first_publish_year": 2015,
        "ia": ["fifthseason0000jemi_x1j4"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL26354343M"],
    },
    {
        "key": "/works/OL20150260W",
        "title": "Normal People",
        "author_name": ["Sally Rooney"],
        "author_key": ["OL7919580A"],
        "cover_i": 8794265,
        "first_publish_year": 2018,
        "ia": ["normalpeople0000roon_o9w7"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL59102236M"],
    },
    {
        "key": "/works/OL17797130W",
        "title": "A Gentleman in Moscow",
        "author_name": ["Amor Towles"],
        "author_key": ["OL7018678A"],
        "cover_i": 11326818,
        "first_publish_year": 2016,
        "ia": ["mosikeshenshigen0000towl"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL35368976M"],
    },
    {
        "key": "/works/OL18139176W",
        "title": "Educated",
        "author_name": ["Tara Westover"],
        "author_key": ["OL7421324A"],
        "cover_i": 8314077,
        "first_publish_year": 2018,
        "ia": ["isbn_9780593091876"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL53223020M"],
    },
    {
        "key": "/works/OL17345497W",
        "title": "The Sympathizer",
        "author_name": ["Viet Thanh Nguyen", "Francois Chau"],
        "author_key": ["OL1603399A", "OL9108410A"],
        "cover_i": 7913176,
        "first_publish_year": 2015,
        "ia": ["sympathizer0000nguy_o2a7"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL59214628M"],
    },
    {
        "key": "/works/OL18012166W",
        "title": "Circe",
        "author_name": ["Madeline Miller"],
        "author_key": ["OL1926056A"],
        "cover_i": 8739376,
        "first_publish_year": 2018,
        "ia": [],
        "has_fulltext": False,
        "ebook_access": "no_ebook",
        "edition_key": ["OL59123703M"],
    },
    {
        "key": "/works/OL20883297W",
        "title": "Klara and the Sun",
        "author_name": ["Kazuo Ishiguro"],
        "author_key": ["OL28493A"],
        "cover_i": 10648686,
        "first_publish_year": 2019,
        "ia": [],
        "has_fulltext": False,
        "ebook_access": "no_ebook",
        "edition_key": ["OL32165942M"],
    },
    {
        "key": "/works/OL20149336W",
        "title": "Exhalation",
        "author_name": ["Ted Chiang"],
        "author_key": ["OL1604887A"],
        "cover_i": 8793546,
        "first_publish_year": 2014,
        "ia": [],
        "has_fulltext": False,
        "ebook_access": "no_ebook",
        "edition_key": ["OL59886250M"],
    },
    {
        "key": "/works/OL16809803W",
        "title": "The Goldfinch",
        "author_name": ["Donna Tartt", "Katia Benovich"],
        "author_key": ["OL841112A", "OL15020935A"],
        "cover_i": 8771366,
        "first_publish_year": 2013,
        "ia": ["eljilguero0000tart"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL59742038M"],
    },
    {
        "key": "/works/OL25344431W",
        "title": "Lessons in Chemistry",
        "author_name": ["Bonnie Garmus"],
        "author_key": ["OL9587269A"],
        "cover_i": 12725772,
        "first_publish_year": 2022,
        "ia": [],
        "has_fulltext": False,
        "ebook_access": "no_ebook",
        "edition_key": ["OL51144311M"],
    },
    {
        "key": "/works/OL26004554W",
        "title": "Tomorrow, and Tomorrow, and Tomorrow",
        "author_name": ["Gabrielle Zevin"],
        "author_key": ["OL1394023A"],
        "cover_i": 12859975,
        "first_publish_year": 2022,
        "ia": [],
        "has_fulltext": False,
        "ebook_access": "no_ebook",
        "edition_key": ["OL62085818M"],
    },
    {
        "key": "/works/OL27052926W",
        "title": "Demon Copperhead",
        "author_name": ["Barbara Kingsolver"],
        "author_key": ["OL221083A"],
        "cover_i": 13141227,
        "first_publish_year": 2022,
        "ia": [],
        "has_fulltext": False,
        "ebook_access": "no_ebook",
        "edition_key": ["OL52941158M"],
    },
    {
        "key": "/works/OL25916696W",
        "title": "Trust",
        "author_name": ["Hernán Díaz"],
        "author_key": ["OL7526140A"],
        "cover_i": 12742248,
        "first_publish_year": 2022,
        "ia": [],
        "has_fulltext": False,
        "ebook_access": "no_ebook",
        "edition_key": ["OL39551233M"],
    },
    {
        "key": "/works/OL20799434W",
        "title": "The Vanishing Half",
        "author_name": ["Brit Bennett", "Brit Bennett"],
        "author_key": ["OL7487872A", "OL13624874A"],
        "cover_i": 10095692,
        "first_publish_year": 2020,
        "ia": ["isbn_9780349702803"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL60348427M"],
    },
    {
        "key": "/works/OL17795349W",
        "title": "Homegoing",
        "author_name": ["Yaa Gyasi"],
        "author_key": ["OL7400941A"],
        "cover_i": 8081171,
        "first_publish_year": 2016,
        "ia": ["homegoingnovel0000gyas_e0x6"],
        "has_fulltext": True,
        "ebook_access": "printdisabled",
        "edition_key": ["OL42965822M"],
    },
]


# Patrons the viewer can follow. `itemname` drives the avatar URL; these are
# real archive.org accounts so the images resolve instead of 404ing.
PATRONS = [
    {"username": "ada_reads", "displayname": "Ada", "itemname": "@mek"},
    {"username": "marginalia", "displayname": "Marginalia", "itemname": "@jimchamp"},
    {"username": "stacks_and_stacks", "displayname": "Stacks", "itemname": "@openlibrary"},
    {"username": "nightowl_reader", "displayname": "Night Owl", "itemname": "@cdrini"},
    {"username": "dogeared", "displayname": "Dog-eared", "itemname": "@scottbarnes"},
    {"username": "quiet_shelf", "displayname": "Quiet Shelf", "itemname": "@seabelis"},
]

# Bookshelf ids, mirroring Bookshelves.PRESET_BOOKSHELVES.
WANT_TO_READ = 1
CURRENTLY_READING = 2
ALREADY_READ = 3

LISTS = [
    ("Books that rewired my brain", 4),
    ("Slow reads for a long winter", 5),
    ("Speculative fiction that earns it", 4),
]


def solr_index(works, verbose=True):
    """Index the work docs into the local Solr core so feed enrichment finds them."""
    docs = [
        {
            "key": w["key"],
            "type": "work",
            "title": w["title"],
            "author_name": w["author_name"],
            "author_key": w["author_key"],
            "cover_i": w["cover_i"],
            "first_publish_year": w["first_publish_year"],
            "ia": w["ia"],
            "has_fulltext": w["has_fulltext"],
            "ebook_access": w["ebook_access"],
            "edition_key": w["edition_key"],
            "seed": [w["key"]],
        }
        for w in WORKS
    ]
    payload = json.dumps(docs).encode()
    req = urllib.request.Request(
        f"{SOLR_URL}/update?commit=true",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
    except urllib.error.URLError as e:
        sys.exit(f"Could not reach Solr at {SOLR_URL}: {e}\nIs the solr service up?")
    if verbose:
        print(f"Indexed {len(docs)} works into Solr")


def ensure_works(verbose=True):
    """Create the Infogami author and work records for the seeded books.

    Solr alone is enough to *render* a feed card, but not enough to link one:
    the work pages 404, and saving a list whose seeds point at works Infogami
    has never seen fails outright with a `KeyError` on the seed key.
    """
    docs = []
    seen_authors = set()
    for work in WORKS:
        for name, key in zip(work["author_name"], work["author_key"], strict=False):
            author_key = f"/authors/{key}"
            if author_key in seen_authors or site.get().get(author_key):
                continue
            seen_authors.add(author_key)
            docs.append({"key": author_key, "type": {"key": "/type/author"}, "name": name})

        if site.get().get(work["key"]):
            continue
        docs.append(
            {
                "key": work["key"],
                "type": {"key": "/type/work"},
                "title": work["title"],
                "covers": [work["cover_i"]],
                "authors": [{"type": {"key": "/type/author_role"}, "author": {"key": f"/authors/{key}"}} for key in work["author_key"]],
            }
        )

    if not docs:
        if verbose:
            print("Works and authors already present")
        return

    with RunAs("openlibrary"):
        site.get().save_many(docs, comment="Seeded by seed_social_feed.py")
    if verbose:
        print(f"Created {len(docs)} author/work records")


def work_id(work):
    """`/works/OL59800W` -> 59800, the integer the reading-log tables store."""
    return int(work["key"].removeprefix("/works/OL").removesuffix("W"))


def ensure_patron(patron):
    """Create the /people/<username> record and mark the reading log public."""
    username = patron["username"]
    email = f"{username}@example.com"

    # Check the account rather than the /people/ record: a run that died between
    # register and activate leaves an account with no thing behind it, and
    # `create` would then raise `email_registered` forever after.
    if account := OpenLibraryAccount.get_by_email(email):
        print(f"  {username} already exists")
    else:
        OpenLibraryAccount.create(
            username=username,
            email=email,
            password="openlibrary",
            displayname=patron["displayname"],
            verified=True,
        )
        account = OpenLibraryAccount.get_by_email(email)
        print(f"  created {username}")

    if account and account.status != "active":
        site.get().activate_account(username=username)
        print(f"  activated {username}")

    # A patron whose reading log is private is filtered straight back out of the
    # public feed, so this is not optional decoration. `create` already does this
    # for brand new accounts; re-applying it keeps re-runs idempotent.
    if user := site.get().get(f"/people/{username}"):
        with RunAs(username):
            user.save_preferences({"public_readlog": "yes"})

    # Link an archive.org itemname so User.get_avatar_url resolves to a real image.
    if account and not account.get("internetarchive_itemname"):
        account.internetarchive_itemname = patron["itemname"]
        account._save()


def seed_events(rng, viewer, verbose=True):
    """Write reading-log, rating, and follow rows for every seeded patron."""
    oldb = db.get_db()
    now = datetime.now(UTC).replace(tzinfo=None)

    oldb.query(
        "DELETE FROM bookshelves_books WHERE username IN $names",
        vars={"names": [p["username"] for p in PATRONS]},
    )
    oldb.query(
        "DELETE FROM ratings WHERE username IN $names",
        vars={"names": [p["username"] for p in PATRONS]},
    )

    shelves = [WANT_TO_READ, CURRENTLY_READING, ALREADY_READ]
    events = 0
    ratings = 0

    for patron in PATRONS:
        username = patron["username"]
        # Spread each patron's books across shelves so the feed shows a mix of
        # event types rather than a wall of "added to Want to Read".
        for work in rng.sample(WORKS, rng.randint(4, 7)):
            shelf = rng.choice(shelves)
            # Timestamps fan out over the last three weeks so relative dates
            # ("2h", "3d", "1w") exercise every branch of the compact formatter.
            minutes_ago = rng.randint(5, 60 * 24 * 21)
            created = now - timedelta(minutes=minutes_ago)
            oldb.insert(
                "bookshelves_books",
                username=username,
                work_id=work_id(work),
                bookshelf_id=shelf,
                edition_id=None,
                private=False,
                created=created,
                updated=created,
            )
            events += 1

            # Only already-read books get a rating, which is the real-world shape.
            if shelf == ALREADY_READ and rng.random() < 0.7:
                oldb.insert(
                    "ratings",
                    username=username,
                    work_id=work_id(work),
                    rating=rng.randint(3, 5),
                    edition_id=None,
                    created=created + timedelta(minutes=5),
                    updated=created + timedelta(minutes=5),
                )
                ratings += 1

    if verbose:
        print(f"Seeded {events} reading-log events and {ratings} ratings")


def seed_follows(viewer, verbose=True):
    for patron in PATRONS:
        PubSub.subscribe(viewer, patron["username"])
    if verbose:
        print(f"{viewer} now follows {len(PATRONS)} patrons")


def clear_follows(viewer, verbose=True):
    for patron in PATRONS:
        PubSub.unsubscribe(viewer, patron["username"])
    if verbose:
        print(f"{viewer} now follows nobody (public-feed mode)")


def seed_lists(rng, verbose=True):
    """Give a few patrons real lists, so list-shaped feed events have something to point at."""
    created = 0
    for idx, (name, size) in enumerate(LISTS):
        patron = PATRONS[idx % len(PATRONS)]
        username = patron["username"]
        user = site.get().get(f"/people/{username}")
        if not user:
            continue
        seeds = [{"key": w["key"]} for w in rng.sample(WORKS, size)]
        with RunAs(username):
            if any(lst.name == name for lst in user.get_lists(limit=50)):
                print(f"  list {name!r} already exists")
                continue
            # `new_list` only builds the doc -- nothing is persisted until the
            # caller saves it.
            lst = user.new_list(name=name, description="", tags=[], seeds=seeds)
            lst._save(comment="Seeded by seed_social_feed.py")
            created += 1
            print(f"  created list {name!r} for {username}")
    if verbose:
        print(f"Seeded {created} lists")


def seed_likes(rng, verbose=True):
    """Have patrons like each other's lists, so the feed shows like events."""
    lists = []
    for patron in PATRONS:
        if user := site.get().get(f"/people/{patron['username']}"):
            lists.extend((patron["username"], lst.key) for lst in user.get_lists(limit=50))

    if not lists:
        if verbose:
            print("No lists to like yet")
        return

    oldb = db.get_db()
    now = datetime.now(UTC).replace(tzinfo=None)
    liked = 0
    for patron in PATRONS:
        # Nobody likes their own list.
        candidates = [key for owner, key in lists if owner != patron["username"]]
        for key in rng.sample(candidates, min(len(candidates), rng.randint(1, 2))):
            if Likes.patron_liked(patron["username"], key):
                continue
            Likes.like(patron["username"], key)
            # `Likes.like` stamps CURRENT_TIMESTAMP, so without this every like
            # lands in the same second and a whole page of them buries the
            # reading-log events at the top of the feed.
            created = now - timedelta(minutes=rng.randint(5, 60 * 24 * 21))
            oldb.query(
                "UPDATE likes SET created=$created, modified=$created WHERE username=$username AND key=$key",
                vars={"created": created, "username": patron["username"], "key": key},
            )
            liked += 1
    if verbose:
        print(f"Seeded {liked} likes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--viewer",
        default="openlibrary",
        help="Account that ends up following the seeded patrons (default: openlibrary)",
    )
    parser.add_argument(
        "--no-follows",
        action="store_true",
        help="Leave the viewer following nobody, to exercise the public feed",
    )
    parser.add_argument("--seed", type=int, default=20242, help="RNG seed, for reproducible data")
    parser.add_argument(
        "--config",
        default="conf/openlibrary.yml",
        help="Path to the Open Library config (default: conf/openlibrary.yml)",
    )
    args = parser.parse_args()

    # Scripts run outside a request, so the `site` ContextVar the models read
    # from is unset until this runs.
    setup_for_script(args.config)

    # Infogami records the writer's IP into `transaction.ip`, a Postgres `inet`
    # column. Outside a request that is the empty string, which Postgres rejects
    # -- every write 500s with `invalid input syntax for type inet`.
    web.ctx.ip = "127.0.0.1"

    rng = random.Random(args.seed)

    solr_index(WORKS)
    ensure_works()

    print("Creating patrons:")
    for patron in PATRONS:
        ensure_patron(patron)

    seed_events(rng, args.viewer)

    print("Creating lists:")
    seed_lists(rng)
    seed_likes(rng)

    if args.no_follows:
        clear_follows(args.viewer)
    else:
        seed_follows(args.viewer)

    print(f"\nDone. Visit /people/{args.viewer}/books to see the feed.")


if __name__ == "__main__":
    main()
