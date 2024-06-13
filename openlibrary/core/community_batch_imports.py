from dataclasses import dataclass
import json
import hashlib

from json.decoder import JSONDecodeError

from pydantic import ValidationError
from pydantic_core import ErrorDetails
from openlibrary import accounts
from openlibrary.core.imports import Batch
from openlibrary.plugins.importapi.import_edition_builder import import_edition_builder
from openlibrary.catalog.add_book import (
    IndependentlyPublished,
    PublicationYearTooOld,
    PublishedInFutureYear,
    SourceNeedsISBN,
    validate_record,
)


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


@dataclass
class CbiErrorItem:
    """
    Represents a Community Batch Import error item, containing a line number and error message.

    As the JSONL in a community batch import file is parsed, it's validated and errors are
    recorded by line number and the error thrown, and this item represents that information,
    which is returned to the uploading patron.
    """

    line_number: int
    error_message: str


@dataclass
class CbiResult:
    """
    Represents the response item from community_batch_import().
    """

    batch: Batch | None = None
    errors: list[CbiErrorItem] | None = None


def format_pydantic_errors(
    errors: list[ErrorDetails], line_idx: int
) -> list[CbiErrorItem]:
    """
    Format a list of Pydantic errors into list[CbiErrorItem] for easier eventual HTML representation.
    """
    formatted_errors = []
    for error in errors:
        if loc := error.get("loc"):
            loc_str = ", ".join(map(str, loc))
        else:
            loc_str = ""
        msg = error["msg"]
        error_type = error["type"]
        error_message = f"{loc_str} field: {msg}. (Type: {error_type})"
        formatted_errors.append(
            CbiErrorItem(line_number=line_idx, error_message=error_message)
        )
    return formatted_errors


def community_batch_import(raw_data: bytes) -> CbiResult:
    """
    This process raw byte data from a JSONL POST to the community batch import endpoint.

    Each line in the JSONL file (i.e. import item) must pass the same validation as
    required for a valid import going through load().

    The return value has `batch` and `errors` attributes for the caller to use to
    access the batch and any errors, respectively. See CbiResult for more.

    The line numbers errors use 1-based counting because they are line numbers in a file.
    """
    user = accounts.get_current_user()
    username = user.get_username()
    batch_name = f"cb-{generate_hash(raw_data)}"
    errors: list[CbiErrorItem] = []
    dict_data = []

    for index, line in enumerate(raw_data.decode("utf-8").splitlines()):
        # Allow comments with `#` in these import records, even though they're JSONL.
        if line.startswith("#"):
            continue

        try:
            raw_record = json.loads(line)
            # Validate the JSON + convert to import rec format and use validation from load().
            edition_builder = import_edition_builder(init_dict=raw_record)
            validate_record(edition_builder.get_dict())

            # Add the raw_record for later processing; it still must go througd load() independently.
            dict_data.append(raw_record)
        except (
            JSONDecodeError,
            PublicationYearTooOld,
            PublishedInFutureYear,
            IndependentlyPublished,
            SourceNeedsISBN,
        ) as e:
            errors.append(CbiErrorItem(line_number=index + 1, error_message=str(e)))

        except ValidationError as e:
            errors.extend(format_pydantic_errors(e.errors(), index + 1))

    if errors:
        return CbiResult(errors=errors)

    # Format data for queueing via batch import.
    batch_data = [
        {
            'ia_id': item['source_records'][0],
            'data': item,
            'submitter': username,
        }
        for item in dict_data
    ]

    # Create the batch
    batch = Batch.find(batch_name) or Batch.new(name=batch_name, submitter=username)
    assert batch is not None
    batch.add_items(batch_data)

    return CbiResult(batch=batch)
