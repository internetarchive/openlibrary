from unittest.mock import MagicMock, patch
from openlibrary.plugins.openlibrary.api import work_delete
import json
import pytest

"""
Test cases for the work_delete implementation using magic mock.
"""

BATCH_SIZE = 1000
TOTAL_EDITION_TEST_CASES = [0, 1, 500, 999, 1000, 1001, 1999, 2000, 2500]


class MockWork:
    def __init__(self, key):
        self.key = key


def create_mock_editions(num_editions):
    """
    Create mock edition dictionaries.
    """
    return [{'key': f'/books/OL{i}M', 'type': {'key': '/type/edition'}} 
            for i in range(num_editions)]

# Will run each of the test cases defined above
@pytest.mark.parametrize("num_editions", TOTAL_EDITION_TEST_CASES)
def test_delete_all_batching(num_editions):
    """
    Test that work_delete properly batches deletions.
    """
    work_key = '/works/OL123W'
    mock_work = MockWork(work_key)
    mock_editions = create_mock_editions(num_editions)

    save_many_calls = []
    
    def mock_save_many(payload, comment):
        save_many_calls.append({
            'payload': payload,
            'comment': comment,
            'size': len(payload)
        })
    
    mock_site = MagicMock()
    mock_site.get.return_value = mock_work
    mock_site.save_many = mock_save_many
    
    # Mock web.input
    mock_input = MagicMock()
    mock_input.get.return_value = None
    
    with patch('web.ctx') as mock_ctx, \
         patch('web.input', return_value=mock_input), \
         patch('openlibrary.plugins.openlibrary.api.can_write', return_value=True):
        
        mock_ctx.site = mock_site
        
        # Create work_delete instance and mock get_editions_of_work
        deleter = work_delete()
        deleter.get_editions_of_work = MagicMock(return_value=mock_editions)
        
        # Execute the POST method
        result = deleter.POST('OL123W')
        result_data = json.loads(result.rawtext)
        
        assert result_data['status'] == 'ok'
        assert result_data['editions_deleted'] == num_editions
        
        total_items = num_editions + 1  # +1 for the work
        expected_batches = (total_items + BATCH_SIZE - 1) // BATCH_SIZE

        assert result_data['batches'] == expected_batches
        assert len(save_many_calls) == expected_batches
        
        # The work and all the editions were deleted correctly
        all_deleted_keys = []
        for call in save_many_calls:
            all_deleted_keys.extend([item['key'] for item in call['payload']])
        
        for edition in mock_editions:
            assert edition['key'] in all_deleted_keys

        assert work_key in all_deleted_keys
        
        # None of the batches exceed the BATCH_SIZE
        for call in save_many_calls:
            assert call['size'] <= BATCH_SIZE

        # If some editions can fit in the same batch with the work, it should be only 1 batch
        if num_editions < BATCH_SIZE:
            assert len(save_many_calls) == 1
            assert work_key in [item['key'] for item in save_many_calls[0]['payload']]
        
        # If there are exactly BATCH_SIZE editions, work should be in separate batch
        elif num_editions == BATCH_SIZE:
            assert len(save_many_calls) == 2
            assert work_key in [item['key'] for item in save_many_calls[1]['payload']]