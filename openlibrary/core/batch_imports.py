import hashlib
import json
from dataclasses import dataclass
from json.decoder import JSONDecodeError
from typing import TYPE_CHECKING

from pydantic import ValidationError

from openlibrary import accounts
from openlibrary.catalog.add_book import (
    IndependentlyPublished,
    PublicationYearTooOld,
    PublishedInFutureYear,
    SourceNeedsISBN,
    validate_record,
)
from openlibrary.core.edit_submissions import (
    is_edit_submission,
    validate_edit_submission,
)
from openlibrary.core.imports import Batch
from openlibrary.plugins.importapi.import_edition_builder import import_edition_builder

if TYPE_CHECKING:
    from pydantic_core import ErrorDetails


def generate_hash(data: bytes, length: int = 20):
    """
    Generate a SHA256 hash of data and truncate it to length.

    This is used to help uniquely identify a batch_import. Truncating
    to 20 characters gives about a 50% chance of collision after 1 billion
    hash imports. According to ChatGPT, anyway. :)
    """
    hash = hashlib.sha256()
    hash.update(data)
    return hash.hexdigest()[:length]


@dataclass
class BatchImportError:
    """
    Represents a Batch Import error item, containing a line number and error message.

    As the JSONL in a batch import file is parsed, it's validated and errors are
    recorded by line number and the error thrown, and this item represents that information,
    which is returned to the uploading patron.
    """

    line_number: int
    error_message: str

    @classmethod
    def from_pydantic_error(cls, line_number: int, error: ErrorDetails) -> BatchImportError:
        """Create a BatchImportError object from Pydantic's ErrorDetails."""
        if loc := error.get("loc"):
            loc_str = ", ".join(map(str, loc))
        else:
            loc_str = ""
        msg = error["msg"]
        error_type = error["type"]
        error_message = f"{loc_str} field: {msg}. (Type: {error_type})"

        return BatchImportError(line_number=line_number, error_message=error_message)


@dataclass
class BatchResult:
    """
    Represents the response item from batch_import().
    """

    batch: Batch | None = None
    errors: list[BatchImportError] | None = None


def _edit_ia_id(record: dict) -> str:
    """Synthetic import_item identifier for an edit submission.

    Edit submissions have no ``source_records``, so they cannot reuse the
    import keying. ``edit:{key}:{hash}`` keeps the row recognisable as an edit
    and unique per distinct patch within a batch.
    """
    patch_hash = generate_hash(json.dumps(record, sort_keys=True).encode("utf-8"), length=12)
    return f"edit:{record['key']}:{patch_hash}"


def batch_import(raw_data: bytes, import_status: str) -> BatchResult:
    """
    This processes raw byte data from a JSONL POST to the batch import endpoint.

    Each line in the JSONL file (i.e. import item) must pass the same validation as
    required for a valid import going through load().

    The return value has `batch` and `errors` attributes for the caller to use to
    access the batch and any errors, respectively. See BatchResult for more.

    The line numbers errors use 1-based counting because they are line numbers in a file.

    import_status: "pending", "needs_review", etc.
    """
    user = accounts.get_current_user()
    username = user.get_username() if user else None
    batch_name = f"batch-{generate_hash(raw_data)}"
    errors: list[BatchImportError] = []
    raw_import_records: list[dict] = []

    for index, line in enumerate(raw_data.decode("utf-8").splitlines()):
        # Allow comments with `#` in these import records, even though they're JSONL.
        if line.startswith("#"):
            continue

        try:
            raw_record = json.loads(line)

            # An edit submission targets an existing record (it carries a `key`
            # + base version `v`). It is a patch to be played on a specific
            # version of the live document, not a new-record import, so it is
            # validated for edit shape rather than run through the import
            # edition builder. See openlibrary.core.edit_submissions (#14750).
            if is_edit_submission(raw_record):
                if edit_errors := validate_edit_submission(raw_record):
                    errors.extend(BatchImportError(line_number=index + 1, error_message=msg) for msg in edit_errors)
                else:
                    raw_import_records.append(raw_record)
                continue

            # Validate the JSON + convert to import rec format and use validation from load().
            edition_builder = import_edition_builder(init_dict=raw_record)
            validate_record(edition_builder.get_dict())

            # Add the raw_record for later processing; it still must go througd load() independently.
            raw_import_records.append(raw_record)
        except (
            JSONDecodeError,
            PublicationYearTooOld,
            PublishedInFutureYear,
            IndependentlyPublished,
            SourceNeedsISBN,
        ) as e:
            errors.append(BatchImportError(line_number=index + 1, error_message=str(e)))

        except ValidationError as e:
            errors.extend([BatchImportError.from_pydantic_error(line_number=index + 1, error=error) for error in e.errors()])

    if errors:
        return BatchResult(errors=errors)

    # Format data for queueing via batch import. New-record imports are keyed
    # by their first source record; edit submissions have no source record, so
    # they are keyed by a synthetic `edit:{key}:{hash}` ia_id (the hash of the
    # patch keeps two distinct edits to the same record from colliding on the
    # unique (batch_id, ia_id) key).
    batch_data = [
        {
            "ia_id": _edit_ia_id(item) if is_edit_submission(item) else item["source_records"][0],
            "data": item,
            "submitter": username,
            "status": import_status,
        }
        for item in raw_import_records
    ]

    # Create the batch
    batch = Batch.find(batch_name) or Batch.new(name=batch_name, submitter=username)
    batch.add_items(batch_data)

    return BatchResult(batch=batch)
