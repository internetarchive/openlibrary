"""
Tests for scripts/migrations/fix_unicode_html_entities.py
"""

from scripts.migrations.fix_unicode_html_entities import get_field_updates, has_entities


class TestHasEntities:
    """Tests for the has_entities helper function."""

    def test_detects_numeric_entity(self):
        """Numeric character references like &#1057; are detected."""
        assert has_entities("&#1057;") is True

    def test_detects_hex_entity(self):
        """Hex character references like &#x41; are detected."""
        assert has_entities("&#x41;") is True

    def test_detects_named_entity(self):
        """Named entities like &amp; are detected."""
        assert has_entities("&amp;") is True

    def test_clean_string_returns_false(self):
        """Plain Unicode strings with no entities return False."""
        assert has_entities("Сергей") is False

    def test_empty_string_returns_false(self):
        """Empty strings return False."""
        assert has_entities("") is False


class TestGetFieldUpdates:
    """Tests for the get_field_updates function."""

    def test_fixes_plain_string_field(self):
        """HTML entities in plain string fields are unescaped."""
        record = {"title": "&#1057;&#1077;&#1088;&#1075;&#1077;&#1081;"}
        updates = get_field_updates(record)
        assert updates == {"title": "Сергей"}

    def test_fixes_dict_field_value(self):
        """HTML entities in the value of a dict field are unescaped."""
        record = {
            "description": {
                "type": "/type/text",
                "value": "&#1057;&#1077;&#1088;&#1075;&#1077;&#1081; was a writer.",
            }
        }
        updates = get_field_updates(record)
        assert updates == {
            "description": {
                "type": "/type/text",
                "value": "Сергей was a writer.",
            }
        }

    def test_dict_field_preserves_type_key(self):
        """Fixing a dict field value preserves the type key."""
        record = {
            "description": {
                "type": "/type/text",
                "value": "&#1057;",
            }
        }
        updates = get_field_updates(record)
        assert updates["description"]["type"] == "/type/text"

    def test_fixes_list_of_dict_items(self):
        """HTML entities in list items are unescaped; clean items pass through."""
        record = {
            "table_of_contents": [
                {"type": "/type/toc_item", "value": "&#1057;&#1077;&#1088;&#1075;&#1077;&#1081;"},
                {"type": "/type/toc_item", "value": "Clean chapter"},
            ]
        }
        updates = get_field_updates(record)
        assert updates["table_of_contents"][0]["value"] == "Сергей"
        assert updates["table_of_contents"][1]["value"] == "Clean chapter"

    def test_clean_record_returns_empty(self):
        """Records with no HTML entities return an empty updates dict."""
        record = {
            "title": "Clean Title",
            "description": {"type": "/type/text", "value": "Clean description."},
            "notes": "No entities here",
        }
        updates = get_field_updates(record)
        assert updates == {}

    def test_ignores_list_with_no_entities(self):
        """Lists containing no HTML entities produce no updates."""
        record = {
            "table_of_contents": [
                {"type": "/type/toc_item", "value": "Chapter One"},
            ]
        }
        updates = get_field_updates(record)
        assert updates == {}

    def test_fixes_multiple_fields(self):
        """Multiple fields with entities are all fixed; clean fields are excluded."""
        record = {
            "title": "&#1057;&#1077;&#1088;&#1075;&#1077;&#1081;",
            "notes": "clean",
            "description": {
                "type": "/type/text",
                "value": "&#1057;&#1077;&#1088;&#1075;&#1077;&#1081; was a writer.",
            },
        }
        updates = get_field_updates(record)
        assert updates["title"] == "Сергей"
        assert updates["description"]["value"] == "Сергей was a writer."
        assert "notes" not in updates
