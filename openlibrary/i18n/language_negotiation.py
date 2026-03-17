"""
Language negotiation utilities for OpenLibrary.

Separates three distinct language mapping concerns:
1. UI locale - The language for Babel-based UI translations
2. Book language - The MARC21 language code for filtering book content
3. Wikipedia language - The best Wikipedia edition to link to

Each mapping considers the full Accept-Language header (BCP 47 tags with
quality values) rather than just the first language tag.
"""

import re
from dataclasses import dataclass

from babel.core import negotiate_locale

# Supported UI locales (matching the i18n translation directories)
SUPPORTED_UI_LOCALES = [
    'ar',
    'as',
    'bn',
    'cs',
    'de',
    'en',
    'es',
    'fr',
    'hi',
    'hr',
    'id',
    'it',
    'ja',
    'pl',
    'pt',
    'ro',
    'ru',
    'sc',
    'te',
    'tr',
    'uk',
    'zh',
]


@dataclass(frozen=True)
class ParsedLanguagePreference:
    """A single language preference from the Accept-Language header."""

    tag: str  # Full BCP 47 tag (e.g., 'zh-TW', 'pt-BR', 'en')
    language: str  # Primary language subtag (e.g., 'zh', 'pt', 'en')
    quality: float  # Quality factor (0.0 to 1.0)


def parse_accept_language(header: str) -> list[ParsedLanguagePreference]:
    """Parse the full Accept-Language header into a sorted list of preferences.

    Properly handles BCP 47 tags and quality values, returning all
    preferences sorted by quality (highest first).

    Args:
        header: The Accept-Language header value
            (e.g., 'pt-BR, pt;q=0.9, es-419;q=0.8, en;q=0.7')

    Returns:
        A list of ParsedLanguagePreference, sorted by quality descending.
    """
    if not header or not header.strip():
        return []

    preferences: list[ParsedLanguagePreference] = []
    re_split = re.compile(r',\s*')

    for token in re_split.split(header):
        token = token.strip()
        if not token or token.startswith('*'):
            continue

        # Split off any quality value (e.g., 'en-GB;q=0.8')
        parts = token.split(';')
        tag = parts[0].strip()
        quality = 1.0

        for param in parts[1:]:
            param = param.strip()
            if param.startswith('q='):
                try:
                    quality = float(param[2:])
                except ValueError:
                    quality = 0.0

        # Extract primary language subtag
        language = tag.split('-')[0].lower()

        preferences.append(
            ParsedLanguagePreference(
                tag=tag,
                language=language,
                quality=quality,
            )
        )

    # Sort by quality descending, stable sort preserves original order for ties
    preferences.sort(key=lambda p: p.quality, reverse=True)
    return preferences


def negotiate_ui_locale(
    preferences: list[ParsedLanguagePreference],
    available: list[str] | None = None,
) -> str | None:
    """Negotiate the best UI locale using Babel's negotiate_locale.

    Uses the full list of user language preferences to find the best match
    among available UI translations, considering all preferences rather
    than only the first one.

    Args:
        preferences: Parsed Accept-Language preferences (from parse_accept_language).
        available: Available UI locales. Defaults to SUPPORTED_UI_LOCALES.

    Returns:
        The best matching locale code (e.g., 'pt', 'es', 'zh'), or None.
    """
    if not preferences:
        return None

    if available is None:
        available = SUPPORTED_UI_LOCALES

    # Build the list of preferred locales from the full BCP 47 tags.
    # Include both the full tag and the primary subtag to allow region-aware
    # matching. e.g., 'pt-BR' -> try 'pt_BR' first (Babel uses underscores),
    # then 'pt'.
    preferred: list[str] = []
    for pref in preferences:
        # Convert BCP 47 hyphen format to Babel's underscore format
        babel_tag = pref.tag.replace('-', '_')
        if babel_tag != pref.language:
            preferred.append(babel_tag)
        preferred.append(pref.language)

    return negotiate_locale(preferred, available)


def get_preferred_wikipedia_languages(
    preferences: list[ParsedLanguagePreference],
) -> list[str]:
    """Get an ordered list of Wikipedia language codes to try.

    Wikipedia language codes are typically the same as BCP 47 primary
    language subtags, but some use region variants (e.g., 'zh-yue' for
    Cantonese Wikipedia). This returns a prioritized list of codes to
    check against available Wikipedia editions.

    Args:
        preferences: Parsed Accept-Language preferences.

    Returns:
        An ordered list of Wikipedia language codes to try, with the
        user's most preferred languages first.
    """
    if not preferences:
        return ['en']

    seen: set[str] = set()
    wiki_langs: list[str] = []

    for pref in preferences:
        # Try the full tag first (e.g., 'zh-yue' for Cantonese Wikipedia)
        full_tag = pref.tag.lower()
        if full_tag not in seen:
            seen.add(full_tag)
            wiki_langs.append(full_tag)

        # Also try the primary language subtag
        if pref.language not in seen:
            seen.add(pref.language)
            wiki_langs.append(pref.language)

    # Always fall back to English
    if 'en' not in seen:
        wiki_langs.append('en')

    return wiki_langs


def get_book_language_from_preferences(
    preferences: list[ParsedLanguagePreference],
) -> str | None:
    """Get the primary language subtag for book content filtering.

    Returns the primary language from the user's top preference,
    which can then be converted to a MARC21 code via convert_iso_to_marc().
    Unlike the old implementation, this preserves the full BCP 47 tag
    information so callers can use it for more precise language mapping
    (e.g., distinguishing 'zh-TW' from 'zh-HK').

    Args:
        preferences: Parsed Accept-Language preferences.

    Returns:
        The primary language subtag of the top preference (e.g., 'zh', 'pt'),
        or None if no preferences are available.
    """
    if not preferences:
        return None
    return preferences[0].language
