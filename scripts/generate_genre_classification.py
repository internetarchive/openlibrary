#!/usr/bin/env python
"""Synthesizes genre.json for Genre Explorer (#13158) from the genres/subgenres
controlled vocabulary in https://github.com/Open-Book-Genome-Project/tags.

Produces a JSON array of ClassificationNode trees (same shape as ddc.json/lcc.json,
see openlibrary/components/LibraryExplorer/utils.js) with one top-level node per
genre and one child node per subgenre. Subgenres with multiple parent genres
(e.g. "Apocalyptic" under Horror, Sci-Fi, and Fantasy) appear once under each parent.

Usage:
    python scripts/generate_genre_classification.py
    python scripts/generate_genre_classification.py --source github --skip-counts
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TAGS_REPO_RAW_BASE = "https://raw.githubusercontent.com/Open-Book-Genome-Project/tags/main"
OL_SEARCH_URL = "https://openlibrary.org/search.json"
DEFAULT_OUTPUT = "openlibrary/components/LibraryExplorer/genre.json"

# Excluded from this prototype specifically (not a data/quality issue -- mek's call for
# this demo).
EXCLUDED_GENRES = {"Erotica"}

# Extra parent_genres for real vocabulary subgenres, on top of what the vocabulary itself
# lists -- demo-only, same spirit as DEMO_SUBGENRE_ADDITIONS below.
EXTRA_PARENT_GENRES: dict[str, list[str]] = {}

# Excluded despite passing resolve_subject_key's live check below: that check only
# verifies the *raw* subject_key count, but the app's actual default filters (the
# "Readable Only" toggle defaulting on -> has_fulltext:true, plus a first_publish_year:
# [1985 TO 9998] range genre mode has no UI control to change) bring every one of these
# to zero real, visible results -- confirmed twice against production with those filters
# applied. A shelf with a healthy raw count but zero results under the app's own defaults
# is worse for a demo than not showing it at all.
EXCLUDED_SUBGENRES = {"Kafkaesque", "Gonzo", "Greek tragedy"}

# Same normalization OL itself uses when indexing a subject string into the Solr
# subject_key facet (openlibrary/solr/updater/work.py: subject_name_to_key) -- lowercase,
# collapse runs of commas/spaces/underscores into one underscore. Notably this NEVER
# touches hyphens, whereas the tags vocabulary's own `slug` field pre-collapses spaces
# into hyphens (e.g. "True Crime" -> "true-crime") -- an incompatible convention that,
# unfixed, silently returns zero real books for several terms (confirmed live: true-crime,
# space-opera, family-saga, coming-of-age all undercounted or zero against production).
_RE_SUBJECT = re.compile("[, _]+")


def ol_subject_key(name: str) -> str:
    return _RE_SUBJECT.sub("_", name.lower()).strip("_")


# A couple of terms in the vocabulary are stylistic abbreviations/coinages that don't
# match OL's dominant real-world cataloging term at all (not a formatting issue --
# genuinely different words), confirmed live against production:
#   sci-fi*  -> 194 books, science_fiction* -> 28,101 (two orders of magnitude)
#   cli-fi*  -> 0 books,   climate_fiction* -> 20 ("Climate Fiction" is literally this
#               term's own definition text in the vocabulary)
# Narrow, explicit, and documented rather than a general guessed-synonym table.
KNOWN_SYNONYMS = {
    "Sci-Fi": "science fiction",
    "Cli-fi": "climate fiction",
}


# Supplementary subgenres for this prototype only -- NOT part of the real
# Open-Book-Genome-Project/tags vocabulary (that repo is read-only for this spike; these
# aren't submitted upstream). Added because several genres had 0-2 real subgenres, and
# mek asked for every genre to have at least 10. Every term below was individually
# verified live against production (openlibrary.org/search.json) to have real, non-trivial
# book counts before being included here -- terms that came back zero or negligible
# (e.g. "Sleuths", "Nonbinary people", "Shakespearean tragedy") were tried and dropped.
# Same shape as a real vocabulary subgenre tag (tag/slug/definition/parent_genres); goes
# through the same resolve_subject_key pipeline as the real data, so slugs are
# independently re-verified (not just trusted from this list) on every run.
DEMO_SUBGENRE_ADDITIONS = [
    {
        "tag": "Surrealism",
        "slug": "surrealism",
        "definition": "Dreamlike, illogical imagery and juxtapositions that defy waking-world causality",
        "parent_genres": ["Absurd"],
    },
    {
        "tag": "Existentialism",
        "slug": "existentialism",
        "definition": "Characters confronting a universe with no inherent meaning, forced to create their own",
        "parent_genres": ["Absurd", "Literary"],
    },
    {
        "tag": "Parody",
        "slug": "parody",
        "definition": "Imitates the style of another work or genre for comic or critical effect",
        "parent_genres": ["Absurd", "Comedy", "Humor", "Satire"],
    },
    {
        "tag": "Farce",
        "slug": "farce",
        "definition": "Improbable situations, physical comedy, and escalating misunderstandings",
        "parent_genres": ["Absurd", "Comedy", "Humor", "Satire"],
    },
    {
        "tag": "Black humor",
        "slug": "black_humor",
        "definition": "Finds comedy in death, suffering, and other traditionally grim subject matter",
        "parent_genres": ["Absurd", "Comedy", "Humor", "Satire"],
    },
    {
        "tag": "Theater of the absurd",
        "slug": "theater_of_the_absurd",
        "definition": "Characters and dialogue that abandon rational structure to dramatize meaninglessness",
        "parent_genres": ["Absurd"],
    },
    {
        "tag": "Nonsense literature",
        "slug": "nonsense_literature",
        "definition": "Wordplay, invented language, and logic-defying scenarios played for their own sake",
        "parent_genres": ["Absurd"],
    },
    {
        "tag": "Metafiction",
        "slug": "metafiction",
        "definition": "Self-consciously draws attention to its own fictional or constructed nature",
        "parent_genres": ["Absurd", "Literary"],
    },
    {
        "tag": "Slapstick",
        "slug": "slapstick",
        "definition": "Exaggerated physical comedy -- pratfalls, chases, and mishaps",
        "parent_genres": ["Absurd", "Comedy", "Humor"],
    },
    {"tag": "Kafkaesque", "slug": "kafkaesque", "definition": "Nightmarish bureaucracy and disorienting, powerless predicaments", "parent_genres": ["Absurd"]},
    {
        "tag": "Wit and humor",  # codespell:ignore wit
        "slug": "wit_and_humor",
        "definition": "Broad, general comic writing built on cleverness and turns of phrase",
        "parent_genres": ["Comedy", "Humor", "Satire"],
    },
    {
        "tag": "Mistaken identity",
        "slug": "mistaken_identity",
        "definition": "Confusion over who a character really is drives the plot's comic complications",
        "parent_genres": ["Comedy", "Humor"],
    },
    {
        "tag": "Romantic comedy",
        "slug": "romantic_comedy",
        "definition": "Courtship complications played for laughs, resolved with the couple together",
        "parent_genres": ["Comedy", "Humor"],
    },
    {
        "tag": "Screwball comedy",
        "slug": "screwball_comedy",
        "definition": "Fast-paced, witty battle-of-the-sexes comedy with eccentric characters",
        "parent_genres": ["Comedy", "Humor"],
    },
    {
        "tag": "Comedy of manners",
        "slug": "comedy_of_manners",
        "definition": "Satirizes the customs and pretensions of a particular social class",
        "parent_genres": ["Comedy", "Humor"],
    },
    {
        "tag": "Absurdist fiction",
        "slug": "absurdist_fiction",
        "definition": "Illogical premises played straight, exposing the absurdity of convention",
        "parent_genres": ["Humor", "Satire"],
    },
    {
        "tag": "Dystopias",
        "slug": "dystopias",
        "definition": "Oppressive societies whose flaws critique real-world politics and institutions",
        "parent_genres": ["Satire"],
    },
    {"tag": "Irony", "slug": "irony", "definition": "A gap between what's said or expected and what's actually true or happens", "parent_genres": ["Satire"]},
    {
        "tag": "Political satire",
        "slug": "political_satire",
        "definition": "Mocks specific politicians, parties, or systems of government",
        "parent_genres": ["Satire"],
    },
    {
        "tag": "Mock-heroic",
        "slug": "mock-heroic",
        "definition": "Grand, epic style applied to trivial subject matter for comic contrast",
        "parent_genres": ["Satire"],
    },
    {
        "tag": "Social satire",
        "slug": "social_satire",
        "definition": "Skewers the customs, hypocrisies, and manners of a society or class",
        "parent_genres": ["Satire"],
    },
    {
        "tag": "Survival",
        "slug": "survival",
        "definition": "Characters pitted against a hostile environment with few resources",
        "parent_genres": ["Action", "Adventure"],
    },
    {"tag": "Revenge", "slug": "revenge", "definition": "A wronged character single-mindedly pursues retribution", "parent_genres": ["Action", "Tragedy"]},
    {
        "tag": "Superheroes",
        "slug": "superheroes",
        "definition": "Costumed figures with extraordinary powers battling equally extraordinary threats",
        "parent_genres": ["Action"],
    },
    {
        "tag": "Assassins",
        "slug": "assassins",
        "definition": "Professional killers, their targets, and the tradecraft of the hit",
        "parent_genres": ["Action", "Thriller"],
    },
    {
        "tag": "War stories",
        "slug": "war_stories",
        "definition": "Combat and its human toll, from the battlefield to the home front",
        "parent_genres": ["Action", "Drama", "Tragedy"],
    },
    {
        "tag": "Vigilantes",
        "slug": "vigilantes",
        "definition": "Characters who take justice into their own hands outside the law",
        "parent_genres": ["Action", "Western"],
    },
    {
        "tag": "Martial arts fiction",
        "slug": "martial_arts_fiction",
        "definition": "Combat discipline, training, and honor codes central to the plot",
        "parent_genres": ["Action"],
    },
    {
        "tag": "Military fiction",
        "slug": "military_fiction",
        "definition": "Life, strategy, and combat within organized armed forces",
        "parent_genres": ["Action"],
    },
    {"tag": "Mercenaries", "slug": "mercenaries", "definition": "Soldiers for hire operating outside formal military allegiance", "parent_genres": ["Action"]},
    {
        "tag": "Heist",
        "slug": "heist",
        "definition": "An elaborate, meticulously planned theft and the crew that pulls it off",
        "parent_genres": ["Action", "Crime"],
    },
    {"tag": "Explorers", "slug": "explorers", "definition": "Journeys into uncharted or little-known territory", "parent_genres": ["Adventure"]},
    {"tag": "Pirates", "slug": "pirates", "definition": "Seafaring outlaws, plunder, and life outside maritime law", "parent_genres": ["Adventure"]},
    {"tag": "Shipwrecks", "slug": "shipwrecks", "definition": "Disaster at sea and the struggle to survive its aftermath", "parent_genres": ["Adventure"]},
    {
        "tag": "Treasure troves",
        "slug": "treasure_troves",
        "definition": "The search for hidden riches, and what characters risk to find them",
        "parent_genres": ["Adventure"],
    },
    {
        "tag": "Sea stories",
        "slug": "sea_stories",
        "definition": "Life and peril aboard ships, from crew dynamics to the sea itself",
        "parent_genres": ["Adventure"],
    },
    {
        "tag": "Wilderness survival",
        "slug": "wilderness_survival",
        "definition": "Characters stripped of civilization's comforts, relying on skill and grit",
        "parent_genres": ["Adventure"],
    },
    {"tag": "Jungles", "slug": "jungles", "definition": "Dense, unforgiving terrain as both setting and antagonist", "parent_genres": ["Adventure"]},
    {"tag": "Trials", "slug": "trials", "definition": "Courtroom proceedings and the drama of arguing a case", "parent_genres": ["Crime"]},
    {"tag": "Prisons", "slug": "prisons", "definition": "Life, power struggles, and survival behind bars", "parent_genres": ["Crime"]},
    {
        "tag": "Organized crime",
        "slug": "organized_crime",
        "definition": "Criminal enterprises run with hierarchy, ritual, and business discipline",
        "parent_genres": ["Crime"],
    },
    {"tag": "Mafia", "slug": "mafia", "definition": "Organized crime families bound by loyalty, ritual, and violence", "parent_genres": ["Crime"]},
    {
        "tag": "Serial murderers",
        "slug": "serial_murderers",
        "definition": "A killer with a repeating pattern, and the hunt to identify and stop them",
        "parent_genres": ["Crime", "Mystery", "Thriller"],
    },
    {"tag": "Gangsters", "slug": "gangsters", "definition": "Career criminals and the underworld hierarchies they climb", "parent_genres": ["Crime"]},
    {
        "tag": "Noir fiction",
        "slug": "noir_fiction",
        "definition": "Cynical, morally ambiguous crime stories in a shadowy urban setting",
        "parent_genres": ["Crime", "Mystery"],
    },
    {
        "tag": "Police procedural",
        "slug": "police_procedural",
        "definition": "The methodical, realistic process of investigating a crime from the inside",
        "parent_genres": ["Crime", "Mystery"],
    },
    {
        "tag": "Domestic fiction",
        "slug": "domestic_fiction",
        "definition": "Family relationships and household life as the central drama",
        "parent_genres": ["Drama", "Literary"],
    },
    {"tag": "Legal stories", "slug": "legal_stories", "definition": "Lawyers, cases, and the machinery of the justice system", "parent_genres": ["Drama"]},
    {
        "tag": "Political fiction",
        "slug": "political_fiction",
        "definition": "Power, government, and ideology drive the central conflict",
        "parent_genres": ["Drama", "Thriller"],
    },
    {
        "tag": "Medical fiction",
        "slug": "medical_fiction",
        "definition": "Hospitals, illness, and the ethical weight of medical decisions",
        "parent_genres": ["Drama"],
    },
    {
        "tag": "Kings and rulers",
        "slug": "kings_and_rulers",
        "definition": "The burdens and intrigues of monarchy and absolute power",
        "parent_genres": ["Historical"],
    },
    {
        "tag": "Immigrants",
        "slug": "immigrants",
        "definition": "Displacement, assimilation, and building a new life in an unfamiliar place",
        "parent_genres": ["Historical"],
    },
    {"tag": "Slavery", "slug": "slavery", "definition": "The brutal history and legacy of human bondage", "parent_genres": ["Historical"]},
    {
        "tag": "Biographical fiction",
        "slug": "biographical_fiction",
        "definition": "Fictionalized accounts of real historical figures' lives",
        "parent_genres": ["Historical"],
    },
    {"tag": "Plague", "slug": "plague", "definition": "Epidemic disease reshaping society and testing individual characters", "parent_genres": ["Historical"]},
    {"tag": "Vikings", "slug": "vikings", "definition": "Norse seafarers, raiders, and settlers of the early medieval period", "parent_genres": ["Historical"]},
    {"tag": "Ancient Rome", "slug": "ancient_rome", "definition": "The politics, warfare, and daily life of the Roman world", "parent_genres": ["Historical"]},
    {"tag": "Ancient Egypt", "slug": "ancient_egypt", "definition": "Pharaohs, pyramids, and the civilization of the Nile", "parent_genres": ["Historical"]},
    {
        "tag": "Regency fiction",
        "slug": "regency_fiction",
        "definition": "Early 19th-century England's manners, courtship, and social hierarchy",
        "parent_genres": ["Historical", "Romance"],
    },
    {
        "tag": "Ancient civilizations",
        "slug": "ancient_civilizations",
        "definition": "Early societies and empires long since vanished",
        "parent_genres": ["Historical"],
    },
    {"tag": "Vampires", "slug": "vampires", "definition": "Undead bloodsuckers, their curses, and those who hunt or love them", "parent_genres": ["Horror"]},
    {
        "tag": "Supernatural",
        "slug": "supernatural",
        "definition": "Forces and beings that defy natural law intrude on the ordinary world",
        "parent_genres": ["Horror"],
    },
    {"tag": "Ghost stories", "slug": "ghost_stories", "definition": "The dead returning to haunt, warn, or torment the living", "parent_genres": ["Horror"]},
    {"tag": "Werewolves", "slug": "werewolves", "definition": "Humans cursed to transform into monstrous, primal beasts", "parent_genres": ["Horror"]},
    {"tag": "Zombies", "slug": "zombies", "definition": "The reanimated dead and the collapse of society in their wake", "parent_genres": ["Horror"]},
    {
        "tag": "Occult fiction",
        "slug": "occult_fiction",
        "definition": "Rituals, curses, and forces beyond mainstream religion or science",
        "parent_genres": ["Horror"],
    },
    {
        "tag": "Gender identity",
        "slug": "gender_identity",
        "definition": "A character's internal sense of their own gender and its expression",
        "parent_genres": ["LGBTQ+"],
    },
    {
        "tag": "Gay men fiction",
        "slug": "gay_men_fiction",
        "definition": "Stories centering gay men's lives, relationships, and identity",
        "parent_genres": ["LGBTQ+"],
    },
    {
        "tag": "Queer theory",
        "slug": "queer_theory",
        "definition": "Critical examination of sexuality and gender as social constructs",
        "parent_genres": ["LGBTQ+"],
    },
    {
        "tag": "Homosexuality",
        "slug": "homosexuality",
        "definition": "Same-sex attraction and relationships as central subject matter",
        "parent_genres": ["LGBTQ+"],
    },
    {
        "tag": "Sexual minorities",
        "slug": "sexual_minorities",
        "definition": "Experiences of those outside heterosexual, cisgender norms",
        "parent_genres": ["LGBTQ+"],
    },
    {"tag": "Same-sex marriage", "slug": "same-sex_marriage", "definition": "Legal and social recognition of same-sex partnerships", "parent_genres": ["LGBTQ+"]},
    {"tag": "Bisexuals", "slug": "bisexuals", "definition": "Characters attracted to more than one gender", "parent_genres": ["LGBTQ+"]},
    {
        "tag": "Intersex people",
        "slug": "intersex_people",
        "definition": "Characters born with sex characteristics outside typical male/female binaries",
        "parent_genres": ["LGBTQ+"],
    },
    {"tag": "Drag queens", "slug": "drag_queens", "definition": "Performance, glamour, and identity through drag culture", "parent_genres": ["LGBTQ+"]},
    {"tag": "Gay fiction", "slug": "gay_fiction", "definition": "Stories centering gay characters and community", "parent_genres": ["LGBTQ+"]},
    {"tag": "Lesbian fiction", "slug": "lesbian_fiction", "definition": "Stories centering lesbian characters and relationships", "parent_genres": ["LGBTQ+"]},
    {
        "tag": "Transgender fiction",
        "slug": "transgender_fiction",
        "definition": "Stories centering transgender characters and experience",
        "parent_genres": ["LGBTQ+"],
    },
    {
        "tag": "Postmodernism",
        "slug": "postmodernism",
        "definition": "Fragmented narrative, irony, and skepticism toward grand narratives",
        "parent_genres": ["Literary"],
    },
    {
        "tag": "Autobiographical fiction",
        "slug": "autobiographical_fiction",
        "definition": "Fiction drawn closely from the author's own lived experience",
        "parent_genres": ["Literary"],
    },
    {
        "tag": "Stream of consciousness fiction",
        "slug": "stream_of_consciousness_fiction",
        "definition": "Prose that mimics the unfiltered, associative flow of a character's thoughts",
        "parent_genres": ["Literary"],
    },
    {
        "tag": "Private investigators",
        "slug": "private_investigators",
        "definition": "Independent detectives working outside official police channels",
        "parent_genres": ["Mystery"],
    },
    {"tag": "Missing persons", "slug": "missing_persons", "definition": "A disappearance drives the investigation and its stakes", "parent_genres": ["Mystery"]},
    {"tag": "Women detectives", "slug": "women_detectives", "definition": "Female investigators leading the case", "parent_genres": ["Mystery"]},
    {"tag": "Cold cases", "slug": "cold_cases", "definition": "Long-unsolved crimes reopened with new evidence or perspective", "parent_genres": ["Mystery"]},
    {
        "tag": "Forensic scientists",
        "slug": "forensic_scientists",
        "definition": "Physical evidence and lab science drive the investigation",
        "parent_genres": ["Mystery"],
    },
    {"tag": "Murder investigation", "slug": "murder_investigation", "definition": "The step-by-step process of solving a killing", "parent_genres": ["Mystery"]},
    {"tag": "Suspects", "slug": "suspects", "definition": "A pool of possible culprits, each with motive and opportunity", "parent_genres": ["Mystery"]},
    {
        "tag": "Folklore",
        "slug": "folklore",
        "definition": "Traditional stories, customs, and beliefs passed down through a culture",
        "parent_genres": ["Mythology"],
    },
    {"tag": "Legends", "slug": "legends", "definition": "Traditional stories popularly believed to have a historical basis", "parent_genres": ["Mythology"]},
    {"tag": "Greek mythology", "slug": "greek_mythology", "definition": "The gods, heroes, and monsters of ancient Greece", "parent_genres": ["Mythology"]},
    {
        "tag": "Arthurian romances",
        "slug": "arthurian_romances",
        "definition": "King Arthur, the Round Table, and the knights of Camelot",
        "parent_genres": ["Mythology"],
    },
    {
        "tag": "Norse mythology",
        "slug": "norse_mythology",
        "definition": "The gods, giants, and cosmology of pre-Christian Scandinavia",
        "parent_genres": ["Mythology"],
    },
    {
        "tag": "Celtic mythology",
        "slug": "celtic_mythology",
        "definition": "The gods, heroes, and otherworlds of Celtic tradition",
        "parent_genres": ["Mythology"],
    },
    {"tag": "Egyptian mythology", "slug": "egyptian_mythology", "definition": "The gods and cosmology of ancient Egypt", "parent_genres": ["Mythology"]},
    {"tag": "Roman mythology", "slug": "roman_mythology", "definition": "The gods and legends of ancient Rome", "parent_genres": ["Mythology"]},
    {
        "tag": "Fairy tales",
        "slug": "fairy_tales",
        "definition": "Traditional stories of magic, wonder, and moral instruction",
        "parent_genres": ["Mythology", "Fantasy"],
    },
    {"tag": "Gods", "slug": "gods", "definition": "Deities and their dealings with mortals", "parent_genres": ["Mythology"]},
    {
        "tag": "Dragons",
        "slug": "dragons",
        "definition": "Great mythic beasts, often guarding treasure or terrorizing kingdoms",
        "parent_genres": ["Mythology", "Fantasy"],
    },
    {"tag": "Fables", "slug": "fables", "definition": "Short, often animal-centered tales that teach a moral lesson", "parent_genres": ["Mythology"]},
    {
        "tag": "Chinese mythology",
        "slug": "chinese_mythology",
        "definition": "The gods, immortals, and legends of Chinese tradition",
        "parent_genres": ["Mythology"],
    },
    {"tag": "Marriage fiction", "slug": "marriage_fiction", "definition": "The dynamics, strains, and rewards of married life", "parent_genres": ["Romance"]},
    {"tag": "Contemporary romance", "slug": "contemporary_romance", "definition": "Love stories set in the present day", "parent_genres": ["Romance"]},
    {
        "tag": "Historical romance",
        "slug": "historical_romance",
        "definition": "Love stories set against a well-realized historical backdrop",
        "parent_genres": ["Romance"],
    },
    {
        "tag": "Paranormal romance",
        "slug": "paranormal_romance",
        "definition": "Romance entangled with supernatural beings or powers",
        "parent_genres": ["Romance"],
    },
    {
        "tag": "Romantic suspense",
        "slug": "romantic_suspense",
        "definition": "A love story woven through a thriller or mystery plot",
        "parent_genres": ["Romance"],
    },
    {"tag": "Kidnapping", "slug": "kidnapping", "definition": "An abduction and the desperate effort to resolve it", "parent_genres": ["Thriller"]},
    {
        "tag": "Conspiracies",
        "slug": "conspiracies",
        "definition": "A hidden plot uncovered, often reaching into powerful institutions",
        "parent_genres": ["Thriller"],
    },
    {
        "tag": "Terrorism fiction",
        "slug": "terrorism_fiction",
        "definition": "Plots involving politically or ideologically motivated violence",
        "parent_genres": ["Thriller"],
    },
    {
        "tag": "Spy stories",
        "slug": "spy_stories",
        "definition": "Espionage, tradecraft, and the double-crosses of intelligence work",
        "parent_genres": ["Thriller"],
    },
    {"tag": "Sabotage", "slug": "sabotage", "definition": "Deliberate disruption or destruction from within", "parent_genres": ["Thriller"]},
    {
        "tag": "Fate and fatalism",
        "slug": "fate_and_fatalism",
        "definition": "Characters powerless against a predetermined, inevitable outcome",
        "parent_genres": ["Tragedy"],
    },
    {"tag": "Betrayal", "slug": "betrayal", "definition": "A trusted bond broken, with devastating consequences", "parent_genres": ["Tragedy"]},
    {
        "tag": "Grief fiction",
        "slug": "grief_fiction",
        "definition": "Mourning and loss as the central emotional weight of the story",
        "parent_genres": ["Tragedy"],
    },
    {"tag": "Death", "slug": "death", "definition": "Mortality confronted directly as a central theme", "parent_genres": ["Tragedy"]},
    {"tag": "Suicide", "slug": "suicide", "definition": "A character's death by their own hand, and its aftermath", "parent_genres": ["Tragedy"]},
    {"tag": "Honor", "slug": "honor", "definition": "A code of conduct whose defense or violation drives the plot", "parent_genres": ["Tragedy"]},
    {"tag": "Greek tragedy", "slug": "greek_tragedy", "definition": "Classical dramatic structure built on hubris and downfall", "parent_genres": ["Tragedy"]},
    {"tag": "Curses", "slug": "curses", "definition": "A supernatural affliction shaping a character's doomed path", "parent_genres": ["Tragedy"]},
    {"tag": "Madness", "slug": "madness", "definition": "A character's descent into mental unraveling", "parent_genres": ["Tragedy"]},
    {
        "tag": "Frontier and pioneer life",
        "slug": "frontier_and_pioneer_life",
        "definition": "Settlers building a life on the edge of the known territory",
        "parent_genres": ["Western"],
    },
    {"tag": "Cowboys", "slug": "cowboys", "definition": "Cattle herders and the working life of the open range", "parent_genres": ["Western"]},
    {"tag": "Ranch life", "slug": "ranch_life", "definition": "Daily life and labor running a cattle or horse ranch", "parent_genres": ["Western"]},
    {"tag": "Outlaws", "slug": "outlaws", "definition": "Criminals living outside the law of the frontier", "parent_genres": ["Western"]},
    {"tag": "Sheriffs", "slug": "sheriffs", "definition": "Frontier lawmen keeping (or failing to keep) order", "parent_genres": ["Western"]},
    {"tag": "Ghost towns", "slug": "ghost_towns", "definition": "Abandoned settlements and the boom-and-bust of frontier towns", "parent_genres": ["Western"]},
    {"tag": "Cattle drives", "slug": "cattle_drives", "definition": "Long overland cattle herds and the hardships of the trail", "parent_genres": ["Western"]},
    {"tag": "Gunfighters", "slug": "gunfighters", "definition": "Quick-draw duels and the reputations built or lost by them", "parent_genres": ["Western"]},
    {"tag": "Gold rush", "slug": "gold_rush", "definition": "Prospectors and boomtowns chasing sudden mineral wealth", "parent_genres": ["Western"]},
    {"tag": "Bounty hunters", "slug": "bounty_hunters", "definition": "Trackers paid to bring in fugitives, dead or alive", "parent_genres": ["Western"]},
    {"tag": "Wagon trains", "slug": "wagon_trains", "definition": "Overland convoys of settlers crossing dangerous territory", "parent_genres": ["Western"]},
    {"tag": "Homesteading", "slug": "homesteading", "definition": "Claiming and working new land to build a self-sufficient life", "parent_genres": ["Western"]},
    {"tag": "Magic", "slug": "magic", "definition": "Supernatural power exercised through will, ritual, or innate ability", "parent_genres": ["Fantasy"]},
    {"tag": "Witches", "slug": "witches", "definition": "Practitioners of magic, often at odds with the society around them", "parent_genres": ["Fantasy"]},
    {"tag": "Wizards", "slug": "wizards", "definition": "Learned or innate masters of magic and its rules", "parent_genres": ["Fantasy"]},
    {"tag": "Elves", "slug": "elves", "definition": "A mythical people known for grace, magic, and long life", "parent_genres": ["Fantasy"]},
    {
        "tag": "Urban fantasy",
        "slug": "urban_fantasy",
        "definition": "Magic and mythical beings hidden within a modern city setting",
        "parent_genres": ["Fantasy"],
    },
    {"tag": "High fantasy", "slug": "high_fantasy", "definition": "Epic stakes in a fully invented secondary world", "parent_genres": ["Fantasy"]},
    {
        "tag": "Sword and sorcery",
        "slug": "sword_and_sorcery",
        "definition": "Personal-scale adventure blending swordplay and magic",
        "parent_genres": ["Fantasy"],
    },
]


def load_vocabulary(tag_type: str, source: str, tags_repo: Path) -> list[dict]:
    if source == "local":
        path = tags_repo / "tag_types" / tag_type / "vocabulary.json"
        data = json.loads(path.read_text())
    else:
        url = f"{TAGS_REPO_RAW_BASE}/tag_types/{tag_type}/vocabulary.json"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    return data["tags"]


_count_cache: dict[str, int] = {}


def fetch_subject_count(slug: str) -> int:
    """Real, live book count for a subject_key slug, via the same subject_key facet
    /subjects pages already use (openlibrary/plugins/worksearch/subjects.py).
    """
    if slug in _count_cache:
        return _count_cache[slug]
    q = urllib.parse.urlencode({"q": f"subject_key:{slug}*", "limit": 0})
    try:
        with urllib.request.urlopen(f"{OL_SEARCH_URL}?{q}", timeout=10) as resp:
            count = json.loads(resp.read())["numFound"]
    except (urllib.error.URLError, TimeoutError, KeyError) as e:
        print(f"  warn: count lookup failed for {slug!r} ({e}); using 0", file=sys.stderr)
        count = 0
    _count_cache[slug] = count
    time.sleep(0.1)  # be polite to the public API
    return count


def resolve_subject_key(tag: dict, with_counts: bool) -> tuple[str, int]:
    """Picks the best-matching real subject_key for a vocabulary entry, live-checking
    candidates rather than trusting the vocabulary's own `slug` blindly (see
    ol_subject_key's docstring/KNOWN_SYNONYMS above for why that's necessary).
    Returns (slug, count). With --skip-counts, trusts the vocabulary's own slug as-is.
    """
    if not with_counts:
        return tag["slug"], 0

    candidate_dict = dict.fromkeys(
        [  # dict.fromkeys: dedup while preserving order
            ol_subject_key(KNOWN_SYNONYMS[tag["tag"]]) if tag["tag"] in KNOWN_SYNONYMS else None,
            ol_subject_key(tag["tag"]),
            tag["slug"],
            # Some catalogers used a space ("Post apocalyptic") rather than a hyphenated
            # compound ("Post-apocalyptic") for the same term, and OL's rule maps a space to
            # "_" but leaves a literal hyphen alone -- so both spellings can independently
            # exist in real data for a hyphenated term. Confirmed live: post-apocalyptic* is
            # undercounted 46 vs 61 for post_apocalyptic*.
            tag["slug"].replace("-", "_") if "-" in tag["slug"] else None,
        ]
    )
    candidates = [c for c in candidate_dict if c]

    best_slug, best_count = tag["slug"], -1
    for slug in candidates:
        count = fetch_subject_count(slug)
        if count > best_count:
            best_slug, best_count = slug, count
    if best_slug != tag["slug"]:
        print(f"  {tag['tag']!r}: vocabulary slug {tag['slug']!r} -> {best_slug!r} ({best_count} books)", file=sys.stderr)
    return best_slug, best_count


def build_genre_tree(genres: list[dict], subgenres: list[dict], with_counts: bool) -> list[dict]:
    genre_by_tag = {g["tag"]: g for g in genres}
    # `query` is embedded directly into the Solr query in Shelf.vue (`subject_key:${query}`), so it
    # must always be a bare slug -- real subject_key values have no genre/subgenre path structure.
    # `hierarchyQuery` is ancestor-prefixed (only BookRoom.vue's JS-side jumpTo resolution reads it) so
    # a subgenre that appears under multiple parents (e.g. Apocalyptic under Horror/Sci-Fi/Fantasy)
    # resolves to the right parent instead of whichever one hierarchyFind happens to visit first.
    genre_slug = {}
    nodes_by_slug = {}
    for g in genres:
        resolved_slug, count = resolve_subject_key(g, with_counts)
        genre_slug[g["tag"]] = resolved_slug
        nodes_by_slug[g["slug"]] = {
            "name": g["tag"],
            "short": resolved_slug,
            "query": f"{resolved_slug}*",
            "hierarchyQuery": f"{resolved_slug}*",
            "count": count,
            "children": [],
        }

    for sg in subgenres:
        if sg["tag"] in EXCLUDED_SUBGENRES:
            continue
        parents = sg.get("parent_genres", []) + EXTRA_PARENT_GENRES.get(sg["tag"], [])
        resolved_slug, count = resolve_subject_key(sg, with_counts)
        for parent_tag in parents:
            parent = genre_by_tag.get(parent_tag)
            if parent is None:
                print(f"  warn: subgenre {sg['tag']!r} references unknown parent genre {parent_tag!r}", file=sys.stderr)
                continue
            nodes_by_slug[parent["slug"]]["children"].append(
                {
                    "name": sg["tag"],
                    "short": resolved_slug,
                    "query": f"{resolved_slug}*",
                    "hierarchyQuery": f"{genre_slug[parent_tag]}/{resolved_slug}*",
                    "count": count,
                }
            )

    tree = []
    for g in genres:
        node = nodes_by_slug[g["slug"]]
        if not node["children"]:
            del node["children"]
        tree.append(node)
    return tree


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--source",
        choices=["local", "github"],
        default="local",
        help="Read vocabulary.json from a local ~/Projects/tags checkout (default) or fetch fresh from GitHub main.",
    )
    parser.add_argument(
        "--tags-repo",
        type=Path,
        default=Path("~/Projects/tags").expanduser(),
        help="Path to a local Open-Book-Genome-Project/tags checkout (used when --source=local).",
    )
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument(
        "--skip-counts", action="store_true", help="Skip live Solr/search.json count lookups (fast iteration; counts will be 0, vocabulary slugs used as-is)."
    )
    args = parser.parse_args()

    print(f"Loading genres/subgenres vocabulary from {args.source}...", file=sys.stderr)
    genres = [g for g in load_vocabulary("genres", args.source, args.tags_repo) if g["tag"] not in EXCLUDED_GENRES]
    subgenres = load_vocabulary("subgenres", args.source, args.tags_repo) + DEMO_SUBGENRE_ADDITIONS
    print(f"  {len(genres)} genres, {len(subgenres)} subgenres ({len(DEMO_SUBGENRE_ADDITIONS)} demo-only additions)", file=sys.stderr)

    if not args.skip_counts:
        print("Fetching live subject counts from openlibrary.org/search.json (subject_key facet)...", file=sys.stderr)
    tree = build_genre_tree(genres, subgenres, with_counts=not args.skip_counts)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(tree, indent=2) + "\n")
    print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
