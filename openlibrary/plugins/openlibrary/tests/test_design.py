"""Tests for the Cookbook registry behind /developers/design/cookbook."""

import json
import re
from pathlib import Path

from openlibrary.plugins.openlibrary.design import RECIPES, SECTIONS, RecipeContext, design_recipe, design_section

TEMPLATES = Path(__file__).parents[3] / "templates"


def test_every_recipe_has_a_template_and_a_route():
    for recipe in RECIPES:
        assert (TEMPLATES / RecipeContext(recipe=recipe).template).is_file()
        assert re.fullmatch(design_recipe.path, f"/developers/design/cookbook/{recipe.id}")


def test_every_section_has_a_template_and_a_route():
    for section in SECTIONS:
        assert (TEMPLATES / "design" / f"{section.id}.html.jinja").is_file()
        assert re.fullmatch(design_section.path, f"/developers/design/{section.id}")


def test_builder_books_are_json_the_page_can_parse():
    books = json.loads(RecipeContext(recipe=RECIPES[0]).books_json)
    assert books
    assert set(books[0]) == {"title", "author", "year", "cover"}
