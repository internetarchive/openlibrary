#!/usr/bin/env python3
"""
Test script to verify the cover selection fix prioritizes English language editions.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from openlibrary.solr.updater.work import WorkSolrBuilder
from openlibrary.solr.updater.edition import EditionSolrBuilder


def test_cover_selection_prioritizes_english():
    """Test that English editions are prioritized for cover selection."""
    
    # Mock work without its own cover
    work = {
        'key': '/works/OL123W',
        'type': {'key': '/type/work'},
        'title': 'Test Book',
        'covers': []  # No work-level cover
    }
    
    # Mock editions with different languages
    russian_edition = {
        'key': '/books/OL1M',
        'type': {'key': '/type/edition'},
        'title': 'Test Book (Russian)',
        'covers': [12345],  # Russian edition has cover
        'languages': [{'key': '/languages/rus'}]
    }
    
    english_edition = {
        'key': '/books/OL2M', 
        'type': {'key': '/type/edition'},
        'title': 'Test Book (English)',
        'covers': [67890],  # English edition has cover
        'languages': [{'key': '/languages/eng'}]
    }
    
    # Test case 1: Russian edition comes first in list
    editions_rus_first = [russian_edition, english_edition]
    
    # Create mock solr editions
    solr_editions_rus_first = [
        EditionSolrBuilder(russian_edition),
        EditionSolrBuilder(english_edition)
    ]
    
    # Mock the WorkSolrBuilder with Russian edition first
    class MockWorkSolrBuilder(WorkSolrBuilder):
        def __init__(self, work, editions, solr_editions):
            self._work = work
            self._editions = editions
            self._solr_editions = solr_editions
            self._authors = []
            self._ia_metadata = {}
            self._data_provider = None
            self._trending_data = {}
    
    builder = MockWorkSolrBuilder(work, editions_rus_first, solr_editions_rus_first)
    
    # The fix should select the English cover (67890) even though Russian comes first
    selected_cover = builder.cover_i
    print(f"Selected cover ID: {selected_cover}")
    print(f"Expected English cover ID: 67890")
    print(f"Russian cover ID: 12345")
    
    if selected_cover == 67890:
        print("✅ SUCCESS: English edition cover was prioritized!")
        return True
    else:
        print("❌ FAILED: English edition cover was not prioritized")
        return False


def test_fallback_to_non_english():
    """Test fallback when no English edition has a cover."""
    
    work = {
        'key': '/works/OL123W',
        'type': {'key': '/type/work'},
        'title': 'Test Book',
        'covers': []
    }
    
    # Only non-English editions with covers
    french_edition = {
        'key': '/books/OL3M',
        'type': {'key': '/type/edition'},
        'title': 'Test Book (French)',
        'covers': [11111],
        'languages': [{'key': '/languages/fre'}]
    }
    
    english_edition_no_cover = {
        'key': '/books/OL4M',
        'type': {'key': '/type/edition'},
        'title': 'Test Book (English)',
        'covers': [],  # No cover
        'languages': [{'key': '/languages/eng'}]
    }
    
    editions = [french_edition, english_edition_no_cover]
    solr_editions = [
        EditionSolrBuilder(french_edition),
        EditionSolrBuilder(english_edition_no_cover)
    ]
    
    class MockWorkSolrBuilder(WorkSolrBuilder):
        def __init__(self, work, editions, solr_editions):
            self._work = work
            self._editions = editions
            self._solr_editions = solr_editions
            self._authors = []
            self._ia_metadata = {}
            self._data_provider = None
            self._trending_data = {}
    
    builder = MockWorkSolrBuilder(work, editions, solr_editions)
    selected_cover = builder.cover_i
    
    print(f"\nFallback test - Selected cover ID: {selected_cover}")
    print(f"Expected French cover ID: 11111")
    
    if selected_cover == 11111:
        print("✅ SUCCESS: Fallback to non-English cover works!")
        return True
    else:
        print("❌ FAILED: Fallback logic not working")
        return False


if __name__ == '__main__':
    print("Testing cover selection fix...\n")
    
    test1_passed = test_cover_selection_prioritizes_english()
    test2_passed = test_fallback_to_non_english()
    
    print(f"\n{'='*50}")
    if test1_passed and test2_passed:
        print("🎉 ALL TESTS PASSED! The fix is working correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Please check the implementation.")
        sys.exit(1)
