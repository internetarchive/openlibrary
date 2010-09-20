"""OpenLibrary schema."""
from openlibrary.core import schema

if __name__ == "__main__":
    print get_schema().sql()
