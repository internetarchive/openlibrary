#!/usr/bin/env python3
"""Check for borrowable books in dev environment."""

from openlibrary.plugins.worksearch import search

# Check for any books with ebook access
solr = search.get_solr()
result = solr.select(
    'type:edition AND ebook_access:*', 
    fields=['key', 'title', 'ebook_access', 'ia'], 
    rows=10
)

print(f'Total books with ebook access: {result.get("num_found", 0)}')
print()

for doc in result.get('docs', [])[:5]:
    print(f'Key: {doc.get("key")}')
    print(f'Title: {doc.get("title", "No title")}')
    print(f'ebook_access: {doc.get("ebook_access")}')
    print(f'ia: {doc.get("ia")}')
    print('-' * 50)
