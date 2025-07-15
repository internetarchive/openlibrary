import json
import os
from typing import Any, Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)

# ----------------------------
# Configuration Constants
# ----------------------------

# maps user preference keys to their actual Solr field names used in backend queries.
FILTER_MAPPING = {
    "subjects": "subject_facet",
    "languages": "language",
    "formats": "has_fulltext",
    "publish_year": "publish_year",
    "publisher": "first_publisher",
    "author": "author_facet",
    "ratings": "ratings_average",
    "want_to_read": "want_to_read_count",
    # We could also account for availability,...
}

# Default carousel configurations
# TODO: For now I am still unsure how to implement this part to define the default query logic for each carousel
# below is an example
# you can consider switching this to a json file 
DEFAULT_CAROUSEL_CONFIGS = {
    "recently_returned": {
        "filters": {
            "has_fulltext": "true"
        },
        "sort": "last_modified_i desc",
        "limit": 50,
        "editionAware": True,
        "lazyLoad": True,
        "dropdownFacet": False
    }
}

# ----------------------------
# Utils
# ----------------------------

def parse_system_overrides(overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parses and validates system-level overrides for carousel filters #10512.
    Returns a normalized dictionary of overrides.
    """
    if not overrides:
        return {}
    # TODO: validate against system override schema
    if not isinstance(overrides, dict):
        logger.warning(f"Invalid system overrides format: {type(overrides)}")
        return {}

    supported_keys = set(FILTER_MAPPING.keys()) | {"sort", "limit"}
    validated_overrides = {}
    
    for key, value in overrides.items():
        if key not in supported_keys:
            logger.warning(f"Unsupported system override key: {key}")
            continue
        validated_overrides[key] = value
    
    return validated_overrides


def parse_user_preferences(request: Any) -> Dict[str, Any]:
    """
    Extracts and validates user preferences from the request object #10760.
    """
    try:
        prefs = {}
        
        # Try to get from user account settings first
        if hasattr(request, 'ctx') and hasattr(request.ctx, 'user'):
            user = request.ctx.user
            if user and hasattr(user, 'preferences'):
                prefs.update(user.preferences.get('book_filters', {}))
        
        # Try to get from session
        if hasattr(request, 'ctx') and hasattr(request.ctx, 'session'):
            session_prefs = request.ctx.session.get('book_preferences', {})
            if session_prefs:
                prefs.update(session_prefs)
        
        # Try to get from cookies 
        if hasattr(request, 'cookies'):
            cookie_prefs = request.cookies.get('book_preferences', '{}')
            try:
                cookie_data = json.loads(cookie_prefs)
                if isinstance(cookie_data, dict):
                    prefs.update(cookie_data)
            except (json.JSONDecodeError, TypeError):
                logger.debug("Failed to parse book preferences from cookies")
        
        return prefs or {}
    except Exception as e:
        logger.warning(f"Failed to parse user preferences: {e}")
        return {}


def validate_preferences(prefs: Dict[str, Any]) -> bool:
    """
    Validates a preferences dictionary against the expected schema.
    Returns True if valid, False otherwise.
    """
    if not isinstance(prefs, dict):
        return False
    
    # Check for valid structure
    valid_keys = set(FILTER_MAPPING.keys()) | {"sort", "limit", "exclude_subjects", "exclude_languages"}
    
    for key, value in prefs.items():
        if key not in valid_keys:
            logger.debug(f"Unknown preference key: {key}")
            continue
            
        # Validate specific field types
        if key in ["subjects", "languages", "exclude_subjects", "exclude_languages"]:
            if not isinstance(value, (list, tuple)):
                logger.debug(f"Invalid type for {key}: expected list, got {type(value)}")
                return False
        elif key == "limit":
            if not isinstance(value, int) or value < 1 or value > 200:
                logger.debug(f"Invalid limit value: {value}")
                return False
        elif key == "publish_year":
            if not isinstance(value, (str, int, list)):
                logger.debug(f"Invalid publish_year type: {type(value)}")
                return False
    
    return True

def normalize_filter_value(key: str, value: Any) -> str:
    """
    Normalizes filter values into Solr-compatible query format.
    """
    if key in ["subjects", "languages", "exclude_subjects", "exclude_languages"]:
        if isinstance(value, (list, tuple)):
            if key.startswith("exclude_"):
                # Create NOT query for exclusions
                return f"NOT ({' OR '.join(str(v) for v in value)})"
            else:
                return f"({' OR '.join(str(v) for v in value)})"
        else:
            return str(value)
    elif key == "publish_year":
        if isinstance(value, list) and len(value) == 2:
            return f"[{value[0]} TO {value[1]}]"
        elif isinstance(value, (int, str)):
            return str(value)
    elif key == "ratings":
        if isinstance(value, (int, float)):
            return f"[{value} TO *]"
        elif isinstance(value, list) and len(value) == 2:
            return f"[{value[0]} TO {value[1]}]"
    
    return str(value)

# ----------------------------
# Main Logic
# ----------------------------

def build_carousel_filters(
    carousel_id: str,
    system_overrides: Optional[Dict[str, Any]],
    user_preferences: Optional[Dict[str, Any]]
) -> Dict[str, str]:
    """
    Builds Open Library search filters for a given carousel, incorporating:
    - Base config (from carousel)
    - System overrides (#10512)
    - User preferences (#10760)
    Returns a dictionary of query parameters for use in search.json.
    """

    filters = {}

    # -------------------
    # Parameter validation
    # -------------------
    if not isinstance(carousel_id, str) or not carousel_id:
        raise ValueError("Invalid carousel_id")
    if system_overrides and not isinstance(system_overrides, dict):
        raise TypeError("system_overrides must be a dict or None")
    if user_preferences and not isinstance(user_preferences, dict):
        raise TypeError("user_preferences must be a dict or None")

    # ------------------------
    # Load base configuration
    # ------------------------
    base_config = get_carousel_config(carousel_id)  
    if not base_config:
        logger.warning(f"No config found for carousel: {carousel_id}")
        return {}

    # ---------------------------
    # Layered filtering strategy
    # ---------------------------
    merged_filters = merge_filters(
        base=base_config.get("filters", {}),
        override=parse_system_overrides(system_overrides),
        user=parse_user_preferences_object(user_preferences),
    )

    # -------------------------------
    # Convert filters to Solr format
    # -------------------------------
    solr_filters = {}
    
    # Handle special metadata fields
    if "sort" in merged_filters:
        solr_filters["sort"] = merged_filters["sort"]
    if "limit" in merged_filters:
        solr_filters["limit"] = str(merged_filters["limit"])
    
    # Convert filter fields to Solr query parameters
    for key, value in merged_filters.items():
        if key in ["sort", "limit"]:
            continue  # Already handled above
            
        # Map to Solr field name
        solr_field = FILTER_MAPPING.get(key, key)
        
        # Handle special cases
        if key == "formats":
            if "fulltext" in str(value).lower():
                solr_filters["has_fulltext"] = "true"
            elif "ebook" in str(value).lower():
                solr_filters["ebook_access"] = "public"
            else:
                solr_filters[solr_field] = str(value)
        elif key == "availability":
            if value == "available":
                solr_filters["availability"] = "available"
            elif value == "borrow":
                solr_filters["ia_collection_s"] = "internetarchivebooks"
            else:
                solr_filters[solr_field] = str(value)
        elif key in ["subjects", "languages"]:
            # Handle list values with OR logic
            normalized_value = normalize_filter_value(key, value)
            solr_filters[solr_field] = normalized_value
        elif key.startswith("exclude_"):
            # Handle exclusions
            base_key = key.replace("exclude_", "")
            solr_field = FILTER_MAPPING.get(base_key, base_key)
            normalized_value = normalize_filter_value(key, value)
            
            # Combine with existing filter if present
            if solr_field in solr_filters:
                solr_filters[solr_field] = f"({solr_filters[solr_field]}) AND {normalized_value}"
            else:
                solr_filters[solr_field] = normalized_value
        else:
            # Standard field mapping
            normalized_value = normalize_filter_value(key, value)
            solr_filters[solr_field] = normalized_value

    # Add default sorting if not specified
    if "sort" not in solr_filters:
        solr_filters["sort"] = base_config.get("sort", "score desc")
    
    # Add default limit if not specified
    if "limit" not in solr_filters:
        solr_filters["limit"] = str(base_config.get("limit", 50))

    logger.debug(f"Built filters for carousel '{carousel_id}': {solr_filters}")
    return solr_filters


# ----------------------------
# Helpers
# ----------------------------

def get_carousel_config(carousel_id: str) -> Dict[str, Any]:
    """
    Loads the base configuration for a carousel.
    """
    # TODO: Can you confirm which json file includes the base cofig for a carousel?
    config_path = os.path.join(os.path.dirname(__file__), "carousel_configs.json") #placeholder only
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                configs = json.load(f)
                if carousel_id in configs:
                    return configs[carousel_id]
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load carousel config from file: {e}")
    
    # Fall back to default configurations
    config = DEFAULT_CAROUSEL_CONFIGS.get(carousel_id)
    if config:
        return config.copy()
    
    # Generate minimal config for unknown carousels
    logger.info(f"Using minimal config for unknown carousel: {carousel_id}")
    return {
        "filters": {"availability": "available"},
        "sort": "score desc",
        "limit": 20
    }


def parse_user_preferences_object(prefs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validates and normalizes user preferences passed to the filter builder.
    """
    if not prefs:
        return {}
    
    if not validate_preferences(prefs):
        logger.warning("Invalid user preferences received, using defaults")
        return {}
    
    # Normalize preference values
    normalized_prefs = {}
    for key, value in prefs.items():
        if key in ["subjects", "languages", "exclude_subjects", "exclude_languages"]:
            # Ensure list format and filter empty values
            if isinstance(value, (list, tuple)):
                normalized_prefs[key] = [str(v).strip() for v in value if str(v).strip()]
            else:
                normalized_prefs[key] = [str(value).strip()] if str(value).strip() else []
        elif key == "limit":
            # Ensure reasonable limits
            normalized_prefs[key] = min(max(int(value), 1), 200)
        else:
            normalized_prefs[key] = value
    
    return normalized_prefs



def merge_filters(
    base: Dict[str, Any],
    override: Dict[str, Any],
    user: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Combines base, system override, and user preferences.
    Precedence: base < system override < user preferences
    """
    merged = base.copy()
    
    # Apply system overrides
    for key, value in override.items():
        if key in ["subjects", "languages"] and key in merged:
            # Merge lists for these fields
            if isinstance(merged[key], (list, tuple)) and isinstance(value, (list, tuple)):
                merged[key] = list(set(merged[key] + list(value)))
            else:
                merged[key] = value
        else:
            merged[key] = value
    
    # Apply user preferences (highest priority)
    for key, value in user.items():
        if key in ["subjects", "languages"] and key in merged:
            # For user preferences, replace completely unless it's an exclusion
            if key.startswith("exclude_"):
                # Keep exclusions separate
                merged[key] = value
            else:
                # User preferences override for positive filters
                merged[key] = value
        else:
            if key in merged and merged[key] != value:
                logger.debug(f"User preference '{key}' overrides previous value: {merged[key]} -> {value}")
            merged[key] = value
    
    return merged




def get_user_book_preferences(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieves stored user book preferences from the database or cache.
    This is a placeholder for integration with OpenLibrary's user system.
    """
    # TODO: Implement actual user preference retrieval
    # This would typically query the user's account settings
    if not user_id:
        return {}
    
    # Placeholder implementation
    return {
        "subjects": [],
        "languages": ["eng"],
        "exclude_subjects": [],
        "formats": ["has_fulltext"],
        "limit": 50
    }


def save_user_book_preferences(user_id: str, preferences: Dict[str, Any]) -> bool:
    """
    Saves user book preferences to the database.
    This is a placeholder only.
    """
    # TODO: Implement actual user preference saving
    # This would typically update the user's account settings
    if not validate_preferences(preferences):
        logger.error(f"Invalid preferences for user {user_id}")
        return False
    
    # Placeholder implementation
    logger.info(f"Saved preferences for user {user_id}: {preferences}")
    return True

# NEXT -> Phase 2:
# Frontend preference managment (preferences.js)

# NEXT -> Phase 3:
# Backend wiring + homepage handler updates

# NEXT -> Phase 4:
# Template implementation

# NEXT -> Phase 5:
# UI implementation