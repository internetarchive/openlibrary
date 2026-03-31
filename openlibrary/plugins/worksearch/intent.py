import re
from typing import Any

class QueryClassifier:
    """
    A lightweight intent classification layer to extract structured data
    (e.g., ISBNs, Publishing Years) from raw query strings before they
    reach the Solr parsing layer.
    """
    
    # Matches ISBN-10 and ISBN-13 formats with optional hyphens/spaces.
    ISBN_REGEX = re.compile(
        r"(?:\bISBN(?:-1[03])?:? )?(?=[-0-9 ]{17}$|[-0-9X ]{13}$|[0-9X]{10}$)(?:97[89][- ]?)?[0-9]{1,5}[- ]?[0-9]+[- ]?[0-9]+[- ]?[0-9X]\b",
        re.IGNORECASE
    )
    
    # Matches a valid publishing year in the range 1400 - 2026.
    YEAR_REGEX = re.compile(r"\b(1[4-9]\d{2}|20[0-1]\d|202[0-6])\b")

    @classmethod
    def parse_intent(cls, raw_q: str) -> dict[str, Any]:
        """
        Parses a raw search query and extracts high-confidence structured
        fields, returning the remaining query text.
        
        :param raw_q: The original search string provided by the user.
        :return: A dictionary containing extracted fields and the residual 'q'.
        """
        extracted = {}
        residual_q = raw_q

        if not residual_q:
            return {"q": residual_q}

        # 1. Extract ISBN
        isbn_match = cls.ISBN_REGEX.search(residual_q)
        if isbn_match:
            # Strip formatting to match the underlying Solr schema requirements
            isbn_clean = isbn_match.group(0).replace('-', '').replace(' ', '').strip()
            # Handle edge case where "ISBN:" prefix is included
            if isbn_clean.lower().startswith("isbn"):
                isbn_clean = isbn_clean[4:].strip(':')
            
            extracted['isbn'] = isbn_clean
            # Remove the detected ISBN from the residual text
            residual_q = cls.ISBN_REGEX.sub('', residual_q)

        # 2. Extract Publish Year
        year_match = cls.YEAR_REGEX.search(residual_q)
        if year_match:
            extracted['publish_year'] = year_match.group(0).strip()
            residual_q = cls.YEAR_REGEX.sub('', residual_q)

        # 3. Clean and finalize the residual query
        # Replace multiple spaces with a single space and strip edges
        extracted['q'] = re.sub(r'\s+', ' ', residual_q).strip()

        return extracted
