import json
from dataclasses import dataclass
from json.decoder import JSONDecodeError

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from openlibrary import accounts
from openlibrary.catalog.add_book import (
    IndependentlyPublished,
    PublicationYearTooOld,
    PublishedInFutureYear,
    SourceNeedsISBN,
    validate_record,
)
from openlibrary.core.imports import Batch
from openlibrary.plugins.importapi.import_edition_builder import import_edition_builder


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
    def from_pydantic_error(cls, line_number: int, error: ErrorDetails) -> "BatchImportError":
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


def batch_import(raw_data: bytes, import_status: str, batch_suffix: str | None = None) -> BatchResult:
    """
    This processes raw byte data from a JSONL POST to the batch import endpoint.

    Each line in the JSONL file (i.e. import item) must pass the same validation as
    required for a valid import going through load().

    The return value has `batch` and `errors` attributes for the caller to use to
    access the batch and any errors, respectively. See BatchResult for more.

    The line numbers errors use 1-based counting because they are line numbers in a file.

    import_status: "pending", "needs_review", etc.
    batch_suffix: optional name suffix; the batch is stored as "{username}:{batch_suffix}".
                  Defaults to "main", so repeated submissions land in the same batch.
    """
    user = accounts.get_current_user()
    username = user and user.get_username()
    if not username:
        raise ValueError("batch_import requires an authenticated user with a username")
    suffix = batch_suffix.strip() if batch_suffix and batch_suffix.strip() else "main"
    full_batch_name = f"{username}:{suffix}"
    errors: list[BatchImportError] = []
    raw_import_records: list[dict] = []

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

    # Format data for queueing via batch import.
    batch_data = [
        {
            "ia_id": item["source_records"][0],
            "data": item,
            "submitter": username,
            "status": import_status,
        }
        for item in raw_import_records
    ]

    # Create the batch
    batch = Batch.find(full_batch_name) or Batch.new(name=full_batch_name, submitter=username)
    batch.add_items(batch_data)

    return BatchResult(batch=batch)
