# TESTING: remove
# from icecream import ic

import json
import hashlib
from openlibrary import accounts
from openlibrary.core.imports import Batch


def generate_hash(data: bytes, length: int = 20):
    """
    Generate a SHA256 hash of data and truncate it to length.

    This is used to help uniquely identify a community_batch_import. Truncating
    to 20 characters gives about a 50% chance of collision after 1 billion
    community hash imports. According to ChatGPT, anyway. :)
    """
    hash = hashlib.sha256()
    hash.update(data)
    return hash.hexdigest()[:length]


def community_batch_import(raw_data: bytes) -> dict[str, str]:
    """
    Handle community batch imports. Required fields:
        TODO: List required fields.
        TODO: Explain how this works and why.
    """
    user = accounts.get_current_user()
    username = user.get_username()
    book_data = json.loads(raw_data)
    batch_name = f"cb-{generate_hash(raw_data)}"
    # Do Pydantic valildation here?

    # Give each item an `ia_id` of the form "isbn:an_isbn_from_the_item" and abuse `or` logic to
    # both update the item dict and then set it as the value for the 'data' key.
    batch_data = [
        {
            'ia_id': f'isbn:{isbn}',
            'data': item.update({'source_records': [f'cb:isbn:{isbn}']}) or item,
            'submitter': username,
        }
        for item in book_data
        if (isbn := item.get('isbn_13') or item.get('isbn_10'))
    ]

    # Or just use a loop to make the above more readable.
    # batch_data = []
    # for book in book_data:
    #     isbn = book.get('isbn_13') or book.get('isbn_10')
    #     if isbn:
    #         book.update({'source_records': [f'cb:isbn:{isbn}']})
    #         batch_data.append({
    #             'ia_id': f'isbn:{isbn}',
    #             'data': book,
    #             'submitter': username,
    #         })

    # ic(user)
    # ic(username)
    # ic(raw_data)
    # ic(book_data)
    # ic(user.keys())
    # ic(user.key)
    # ic(user.name)
    # ic(batch_name)
    # ic(book_data_with_ia_id)

    # Create the batch
    batch = Batch.find(batch_name) or Batch.new(name=batch_name, submitter=username)
    assert batch is not None
    result = batch.add_items(batch_data)
    if not result:
        return {'status': 'no items to add'}

    return {'status': result}
