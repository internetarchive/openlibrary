"""OpenLibrary schema."""
from openlibrary.core.schema import get_schema

if __name__ == "__main__":
    print get_schema().sql()
