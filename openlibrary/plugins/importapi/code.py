"""Open Library Import API"""

import base64
import json
import logging
import re
import urllib
from typing import Any

import lxml.etree
import web
from lxml import etree
from pydantic import ValidationError

from infogami.infobase.client import ClientException
from infogami.plugins.api.code import add_hook
from openlibrary import accounts, records
from openlibrary.catalog import add_book
from openlibrary.catalog.get_ia import get_from_archive_bulk, get_marc_record_from_ia
from openlibrary.catalog.marc.marc_binary import MarcBinary, MarcException
from openlibrary.catalog.marc.marc_xml import MarcXml
from openlibrary.catalog.marc.parse import read_edition
from openlibrary.catalog.utils import get_non_isbn_asin
from openlibrary.core import ia
from openlibrary.plugins.importapi import (
    import_edition_builder,
    import_opds,
    import_rdf,
    import_validator,
)
from openlibrary.plugins.openlibrary.code import can_write
from openlibrary.plugins.upstream.utils import (
    LanguageMultipleMatchError,
    LanguageNoMatchError,
    get_abbrev_from_full_lang_name,
    get_location_and_publisher,
    safeget,
)
from openlibrary.utils.isbn import get_isbn_10s_and_13s, to_isbn_13

MARC_LENGTH_POS = 5
logger = logging.getLogger('openlibrary.importapi')


class DataError(ValueError):
    pass


class BookImportError(Exception):
    def __init__(self, error_code, error='Invalid item', **kwargs):
        self.error_code = error_code
        self.error = error
        self.kwargs = kwargs


def parse_meta_headers(edition_builder):
    # parse S3-style http headers
    # we don't yet support augmenting complex fields like author or language
    # string_keys = ['title', 'title_prefix', 'description']

    re_meta = re.compile(r'HTTP_X_ARCHIVE_META(?:\d{2})?_(.*)')
    for k, v in web.ctx.env.items():
        m = re_meta.match(k)
        if m:
            meta_key = m.group(1).lower()
            edition_builder.add(meta_key, v, restrict_keys=False)


def parse_data(data: bytes) -> tuple[dict | None, str | None]:
    """
    Takes POSTed data and determines the format, and returns an Edition record
    suitable for adding to OL.

    :param bytes data: Raw data
    :return: (Edition record, format (rdf|opds|marcxml|json|marc)) or (None, None)
    """
    data = data.strip()
    if b'<?xml' in data[:10]:
        root = etree.fromstring(
            data, parser=lxml.etree.XMLParser(resolve_entities=False)
        )
        if root.tag == '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF':
            edition_builder = import_rdf.parse(root)
            format = 'rdf'
        elif root.tag == '{http://www.w3.org/2005/Atom}entry':
            edition_builder = import_opds.parse(root)
            format = 'opds'
        elif root.tag == '{http://www.loc.gov/MARC21/slim}record':
            if root.tag == '{http://www.loc.gov/MARC21/slim}collection':
                root = root[0]
            rec = MarcXml(root)
            edition = read_edition(rec)
            edition_builder = import_edition_builder.import_edition_builder(
                init_dict=edition
            )
            format = 'marcxml'
        else:
            raise DataError('unrecognized-XML-format')
    elif data.startswith(b'{') and data.endswith(b'}'):
        obj = json.loads(data)

        # Only look to the import_item table if a record is incomplete.
        # This is the minimum to achieve a complete record. See:
        # https://github.com/internetarchive/openlibrary/issues/9440
        # import_validator().validate() requires more fields.
        minimum_complete_fields = ["title", "authors", "publish_date"]
        is_complete = all(obj.get(field) for field in minimum_complete_fields)
        if not is_complete:
            isbn_10 = safeget(lambda: obj.get("isbn_10", [])[0])
            isbn_13 = safeget(lambda: obj.get("isbn_13", [])[0])
            identifier = to_isbn_13(isbn_13 or isbn_10 or "")

            if not identifier:
                identifier = get_non_isbn_asin(rec=obj)

            if identifier:
                supplement_rec_with_import_item_metadata(rec=obj, identifier=identifier)

        edition_builder = import_edition_builder.import_edition_builder(init_dict=obj)
        format = 'json'
    elif data[:MARC_LENGTH_POS].isdigit():
        # Marc Binary
        if len(data) < MARC_LENGTH_POS or len(data) != int(data[:MARC_LENGTH_POS]):
            raise DataError('no-marc-record')
        record = MarcBinary(data)
        edition = read_edition(record)
        edition_builder = import_edition_builder.import_edition_builder(
            init_dict=edition
        )
        format = 'marc'
    else:
        raise DataError('unrecognised-import-format')

    parse_meta_headers(edition_builder)
    return edition_builder.get_dict(), format


def supplement_rec_with_import_item_metadata(
    rec: dict[str, Any], identifier: str
) -> None:
    """
    Queries for a staged/pending row in `import_item` by identifier, and if found,
    uses select metadata to supplement empty fields in `rec`.

    Changes `rec` in place.
    """
    from openlibrary.core.imports import (  # noqa: PLC0415
        ImportItem,
    )  # Evade circular import.  # noqa: PLC0415, RUF100

    import_fields = [
        'authors',
        'description',
        'isbn_10',
        'isbn_13',
        'number_of_pages',
        'physical_format',
        'publish_date',
        'publishers',
        'title',
        'source_records',
    ]

    if import_item := ImportItem.find_staged_or_pending([identifier]).first():
        import_item_metadata = json.loads(import_item.get("data", '{}'))
        for field in import_fields:
            if field == "source_records":
                rec[field].extend(import_item_metadata.get(field))
            if not rec.get(field) and (staged_field := import_item_metadata.get(field)):
                rec[field] = staged_field


class importapi:
    """/api/import endpoint for general data formats."""

    def error(self, error_code, error='Invalid item', **kwargs):
        content = {'success': False, 'error_code': error_code, 'error': error}
        content.update(kwargs)
        raise web.HTTPError('400 Bad Request', data=json.dumps(content))

    def POST(self):
        web.header('Content-Type', 'application/json')
        if not can_write():
            raise web.HTTPError('403 Forbidden')

        i = web.input()
        preview = i.get('preview') == 'true'
        data = web.data()

        try:
            edition, _ = parse_data(data)

        except (DataError, json.JSONDecodeError) as e:
            return self.error(str(e), 'Failed to parse import data')
        except ValidationError as e:
            return self.error('invalid-value', str(e).replace('\n', ': '))

        if not edition:
            return self.error('unknown-error', 'Failed to parse import data')

        try:
            reply = add_book.load(edition, save=not preview)
            # TODO: If any records have been created, return a 201, otherwise 200
            return json.dumps(reply)
        except add_book.RequiredFields as e:
            return self.error('missing-required-field', str(e))
        except ClientException as e:
            return self.error('bad-request', **json.loads(e.json))
        except TypeError as e:
            return self.error('type-error', repr(e))
        except Exception as e:
            return self.error('unhandled-exception', repr(e))


def raise_non_book_marc(marc_record, **kwargs):
    details = 'Item rejected'
    # Is the item a serial instead of a monograph?
    marc_leaders = marc_record.leader()
    if marc_leaders[7] == 's':
        raise BookImportError('item-is-serial', details, **kwargs)

    # insider note: follows Archive.org's approach of
    # Item::isMARCXMLforMonograph() which excludes non-books
    # MARC leader$6,7 reference: https://www.loc.gov/marc/bibliographic/bdleader.html
    ACCEPTED_TYPES = 'am'  # a: Language material, m: Computer file
    if not (marc_leaders[6] in ACCEPTED_TYPES and marc_leaders[7] == 'm'):
        raise BookImportError('item-not-book', details, **kwargs)


class ia_importapi(importapi):
    """/api/import/ia import endpoint for Archive.org items, requiring an ocaid identifier rather than direct data upload.
    Request Format:

        POST /api/import/ia
        Content-Type: application/json
        Authorization: Basic base64-of-username:password

        {
            "identifier": "<ocaid>",
            "require_marc": "true",
            "bulk_marc": "false"
        }
    """

    @classmethod
    def ia_import(
        cls,
        identifier: str,
        require_marc: bool = True,
        force_import: bool = False,
        preview: bool = False,
    ) -> str:
        import_record, from_marc_record = cls.get_ia_import_record(
            identifier,
            require_marc=require_marc,
            force_import=force_import,
            preview=preview,
        )
        result = add_book.load(
            import_record,
            from_marc_record=from_marc_record,
            save=not preview,
        )
        return json.dumps(result)

    @classmethod
    def get_ia_import_record(
        cls,
        identifier: str,
        require_marc: bool = True,
        force_import: bool = False,
        preview: bool = False,
    ) -> tuple[dict, bool]:
        """
        Performs logic to fetch archive.org item + metadata,
        produces a data dict, then loads into Open Library

        :param str identifier: archive.org ocaid
        :param bool require_marc: require archive.org item have MARC record?
        :param bool force_import: force import of this record
        :returns: the data of the imported book or raises  BookImportError
        """
        from_marc_record = False

        # Check 1 - Is this a valid Archive.org item?
        metadata = ia.get_metadata(identifier)
        if not metadata:
            raise BookImportError('invalid-ia-identifier', f'{identifier} not found')

        # Check 2 - Can the item be loaded into Open Library?
        status = ia.get_item_status(identifier, metadata)
        if status != 'ok' and not force_import:
            raise BookImportError(status, f'Prohibited Item {identifier}')

        # Check 3 - Does this item have a MARC record?
        marc_record = get_marc_record_from_ia(
            identifier=identifier, ia_metadata=metadata
        )
        if require_marc and not marc_record:
            raise BookImportError('no-marc-record')
        if marc_record:
            from_marc_record = True

            if not force_import:
                raise_non_book_marc(marc_record)
            try:
                import_record = read_edition(marc_record)
            except MarcException as e:
                logger.error(f'failed to read from MARC record {identifier}: {e}')
                raise BookImportError('invalid-marc-record')
        else:
            try:
                import_record = cls.get_ia_record(metadata)
            except KeyError:
                raise BookImportError('invalid-ia-metadata')
            except ValidationError as e:
                raise BookImportError('not-differentiable', str(e))

        # Add IA specific fields: ocaid, source_records, and cover
        cls.populate_edition_data(import_record, identifier)

        return import_record, from_marc_record

    def POST(self):
        web.header('Content-Type', 'application/json')

        if not can_write():
            raise web.HTTPError('403 Forbidden')

        i = web.input()

        preview = i.get('preview') == 'true'
        require_marc = i.get('require_marc') != 'false'
        force_import = i.get('force_import') == 'true'
        bulk_marc = i.get('bulk_marc') == 'true'

        if 'identifier' not in i:
            return self.error('bad-input', 'identifier not provided')
        identifier = i.identifier

        # First check whether this is a non-book, bulk-marc item
        if bulk_marc:
            # Get binary MARC by identifier = ocaid/filename:offset:length
            re_bulk_identifier = re.compile(r"([^/]*)/([^:]*):(\d*):(\d*)")
            try:
                ocaid, filename, offset, length = re_bulk_identifier.match(
                    identifier
                ).groups()
                data, next_offset, next_length = get_from_archive_bulk(identifier)
                next_data = {
                    'next_record_offset': next_offset,
                    'next_record_length': next_length,
                }
                rec = MarcBinary(data)
                edition = read_edition(rec)
            except MarcException as e:
                details = f'{identifier}: {e}'
                logger.error(f'failed to read from bulk MARC record {details}')
                return self.error('invalid-marc-record', details, **next_data)

            actual_length = int(rec.leader()[:MARC_LENGTH_POS])
            edition['source_records'] = 'marc:%s/%s:%s:%d' % (
                ocaid,
                filename,
                offset,
                actual_length,
            )

            local_id = i.get('local_id')
            if local_id:
                local_id_type = web.ctx.site.get('/local_ids/' + local_id)
                prefix = local_id_type.urn_prefix
                force_import = True
                id_field, id_subfield = local_id_type.id_location.split('$')

                def get_subfield(field, id_subfield):
                    if isinstance(field[1], str):
                        return field[1]
                    subfields = field[1].get_subfield_values(id_subfield)
                    return subfields[0] if subfields else None

                ids = [
                    get_subfield(f, id_subfield)
                    for f in rec.read_fields([id_field])
                    if f and get_subfield(f, id_subfield)
                ]
                edition['local_id'] = [f'urn:{prefix}:{id_}' for id_ in ids]

            # Don't add the book if the MARC record is a non-monograph item,
            # unless it is a scanning partner record and/or force_import is set.
            if not force_import:
                try:
                    raise_non_book_marc(rec, **next_data)

                except BookImportError as e:
                    return self.error(e.error_code, e.error, **e.kwargs)
            result = add_book.load(edition, save=not preview)

            # Add next_data to the response as location of next record:
            result.update(next_data)
            return json.dumps(result)

        try:
            return self.ia_import(
                identifier,
                require_marc=require_marc,
                force_import=force_import,
                preview=preview,
            )
        except BookImportError as e:
            return self.error(e.error_code, e.error, **e.kwargs)

    @staticmethod
    def get_ia_record(metadata: dict) -> dict:
        """
        Generate Edition record from Archive.org metadata, in lieu of a MARC record

        :param dict metadata: metadata retrieved from metadata API
        :return: Edition record
        """
        authors = [{'name': name} for name in metadata.get('creator', '').split(';')]
        description = metadata.get('description')
        unparsed_isbns = metadata.get('isbn')
        language = metadata.get('language')
        lccn = metadata.get('lccn')
        subject = metadata.get('subject')
        oclc = metadata.get('oclc-id')
        imagecount = metadata.get('imagecount')
        unparsed_publishers = metadata.get('publisher')
        d = {
            'title': metadata.get('title', ''),
            'authors': authors,
            'publish_date': metadata.get('date'),
        }
        if description:
            d['description'] = description
        if unparsed_isbns:
            isbn_10, isbn_13 = get_isbn_10s_and_13s(unparsed_isbns)
            if isbn_10:
                d['isbn_10'] = isbn_10
            if isbn_13:
                d['isbn_13'] = isbn_13
        if language:
            if len(language) == 3:
                d['languages'] = [language]

            # Try converting the name of a language to its three character code.
            # E.g. English -> eng.
            else:
                try:
                    if lang_code := get_abbrev_from_full_lang_name(language):
                        d['languages'] = [lang_code]
                except LanguageMultipleMatchError as e:
                    logger.warning(
                        "Multiple language matches for %s. No edition language set for %s.",
                        e.language_name,
                        metadata.get("identifier"),
                    )
                except LanguageNoMatchError as e:
                    logger.warning(
                        "No language matches for %s. No edition language set for %s.",
                        e.language_name,
                        metadata.get("identifier"),
                    )

        if lccn:
            d['lccn'] = [lccn]
        if subject:
            d['subjects'] = subject
        if oclc:
            d['oclc'] = oclc
        # Ensure no negative page number counts.
        if imagecount:
            if int(imagecount) - 4 >= 1:
                d['number_of_pages'] = int(imagecount) - 4
            else:
                d['number_of_pages'] = int(imagecount)

        if unparsed_publishers:
            publish_places, publishers = get_location_and_publisher(unparsed_publishers)
            if publish_places:
                d['publish_places'] = publish_places
            if publishers:
                d['publishers'] = publishers

        d['source_records'] = ['ia:' + metadata['identifier']]
        import_validator.import_validator().validate(d)
        return d

    @staticmethod
    def populate_edition_data(edition: dict, identifier: str) -> dict:
        """
        Adds archive.org specific fields to a generic Edition record, based on identifier.

        :param dict edition: Edition record
        :param str identifier: ocaid
        :return: Edition record
        """
        edition['ocaid'] = identifier
        edition['source_records'] = 'ia:' + identifier
        edition['cover'] = ia.get_cover_url(identifier)
        return edition

    @staticmethod
    def find_edition(identifier: str) -> str | None:
        """
        Checks if the given identifier has already been imported into OL.

        :param str identifier: ocaid
        :return: OL item key of matching item: '/books/OL..M' or None if no item matches
        """
        # match ocaid
        q = {"type": "/type/edition", "ocaid": identifier}
        keys = web.ctx.site.things(q)
        if keys:
            return keys[0]

        # Match source_records
        # When there are multiple scans for the same edition, only source_records is updated.
        q = {"type": "/type/edition", "source_records": "ia:" + identifier}
        keys = web.ctx.site.things(q)
        if keys:
            return keys[0]

        return None

    @staticmethod
    def status_matched(key):
        reply = {'success': True, 'edition': {'key': key, 'status': 'matched'}}
        return json.dumps(reply)


class ils_search:
    """Search and Import API to use in Koha.

    When a new catalog record is added to Koha, it makes a request with all
    the metadata to find if OL has a matching record. OL returns the OLID of
    the matching record if exists, if not it creates a new record and returns
    the new OLID.

    Request Format:

        POST /api/ils_search
        Content-Type: application/json
        Authorization: Basic base64-of-username:password

        {
            'title': '',
            'authors': ['...','...',...]
            'publisher': '...',
            'publish_year': '...',
            'isbn': [...],
            'lccn': [...],
        }

    Response Format:

        {
            'status': 'found | notfound | created',
            'olid': 'OL12345M',
            'key': '/books/OL12345M',
            'cover': {
                'small': 'https://covers.openlibrary.org/b/12345-S.jpg',
                'medium': 'https://covers.openlibrary.org/b/12345-M.jpg',
                'large': 'https://covers.openlibrary.org/b/12345-L.jpg',
            },
            ...
        }

    When authorization header is not provided and match is not found,
    status='notfound' is returned instead of creating a new record.
    """

    def POST(self):
        try:
            rawdata = json.loads(web.data())
        except ValueError:
            raise self.error("Unparsable JSON input \n %s" % web.data())

        # step 1: prepare the data
        data = self.prepare_input_data(rawdata)

        # step 2: search
        matches = self.search(data)

        # step 3: Check auth
        try:
            auth_header = http_basic_auth()
            self.login(auth_header)
        except accounts.ClientException:
            raise self.auth_failed("Invalid credentials")

        # step 4: create if logged in
        keys = []
        if auth_header:
            keys = self.create(matches)

        # step 4: format the result
        d = self.format_result(matches, auth_header, keys)
        return json.dumps(d)

    def error(self, reason):
        d = json.dumps({"status": "error", "reason": reason})
        return web.HTTPError("400 Bad Request", {"Content-Type": "application/json"}, d)

    def auth_failed(self, reason):
        d = json.dumps({"status": "error", "reason": reason})
        return web.HTTPError(
            "401 Authorization Required",
            {
                "WWW-Authenticate": 'Basic realm="http://openlibrary.org"',
                "Content-Type": "application/json",
            },
            d,
        )

    def login(self, auth_str):
        if not auth_str:
            return
        auth_str = auth_str.replace("Basic ", "")
        try:
            auth_str = base64.decodebytes(bytes(auth_str, 'utf-8'))
            auth_str = auth_str.decode('utf-8')
        except AttributeError:
            auth_str = base64.decodestring(auth_str)
        username, password = auth_str.split(':')
        accounts.login(username, password)

    def prepare_input_data(self, rawdata):
        data = dict(rawdata)
        identifiers = rawdata.get('identifiers', {})
        # TODO: Massage single strings here into lists. e.g. {"google" : "123"} into {"google" : ["123"]}.
        for i in ["oclc_numbers", "lccn", "ocaid", "isbn"]:
            if i in data:
                val = data.pop(i)
                if not isinstance(val, list):
                    val = [val]
                identifiers[i] = val
        data['identifiers'] = identifiers

        if "authors" in data:
            authors = data.pop("authors")
            data['authors'] = [{"name": i} for i in authors]

        return {"doc": data}

    def search(self, params):
        matches = records.search(params)
        return matches

    def create(self, items):
        return records.create(items)

    def format_result(self, matches, authenticated, keys):
        doc = matches.pop("doc", {})
        if doc and doc['key']:
            doc = web.ctx.site.get(doc['key']).dict()
            # Sanitise for only information that we want to return.
            for i in [
                "created",
                "last_modified",
                "latest_revision",
                "type",
                "revision",
            ]:
                doc.pop(i)
            # Main status information
            d = {
                'status': 'found',
                'key': doc['key'],
                'olid': doc['key'].split("/")[-1],
            }
            # Cover information
            covers = doc.get('covers') or []
            if covers and covers[0] > 0:
                d['cover'] = {
                    "small": "https://covers.openlibrary.org/b/id/%s-S.jpg" % covers[0],
                    "medium": "https://covers.openlibrary.org/b/id/%s-M.jpg"
                    % covers[0],
                    "large": "https://covers.openlibrary.org/b/id/%s-L.jpg" % covers[0],
                }

            # Pull out identifiers to top level
            identifiers = doc.pop("identifiers", {})
            for i in identifiers:
                d[i] = identifiers[i]
            d.update(doc)

        elif authenticated:
            d = {'status': 'created', 'works': [], 'authors': [], 'editions': []}
            for i in keys:
                if i.startswith('/books'):
                    d['editions'].append(i)
                if i.startswith('/works'):
                    d['works'].append(i)
                if i.startswith('/authors'):
                    d['authors'].append(i)
        else:
            d = {'status': 'notfound'}
        return d


def http_basic_auth():
    auth = web.ctx.env.get('HTTP_AUTHORIZATION')
    return auth and web.lstrips(auth, "")


class ils_cover_upload:
    """Cover Upload API for Koha.

    Request Format: Following input fields with enctype multipart/form-data

        * olid: Key of the edition. e.g. OL12345M
        * file: image file
        * url: URL to image
        * redirect_url: URL to redirect after upload

        Other headers:
           Authorization: Basic base64-of-username:password

    One of file or url can be provided. If the former, the image is
    directly used. If the latter, the image at the URL is fetched and
    used.

    On Success:
          If redirect URL specified,
                redirect to redirect_url?status=ok
          else
                return
                {
                  "status" : "ok"
                }

    On Failure:
          If redirect URL specified,
                redirect to redirect_url?status=error&reason=bad+olid
          else
                return
                {
                  "status" : "error",
                  "reason" : "bad olid"
                }
    """

    def error(self, i, reason):
        if i.redirect_url:
            url = self.build_url(i.redirect_url, status="error", reason=reason)
            return web.seeother(url)
        else:
            d = json.dumps({"status": "error", "reason": reason})
            return web.HTTPError(
                "400 Bad Request", {"Content-Type": "application/json"}, d
            )

    def success(self, i):
        if i.redirect_url:
            url = self.build_url(i.redirect_url, status="ok")
            return web.seeother(url)
        else:
            d = json.dumps({"status": "ok"})
            return web.ok(d, {"Content-type": "application/json"})

    def auth_failed(self, reason):
        d = json.dumps({"status": "error", "reason": reason})
        return web.HTTPError(
            "401 Authorization Required",
            {
                "WWW-Authenticate": 'Basic realm="http://openlibrary.org"',
                "Content-Type": "application/json",
            },
            d,
        )

    def build_url(self, url, **params):
        if '?' in url:
            return url + "&" + urllib.parse.urlencode(params)
        else:
            return url + "?" + urllib.parse.urlencode(params)

    def login(self, auth_str):
        if not auth_str:
            raise self.auth_failed("No credentials provided")
        auth_str = auth_str.replace("Basic ", "")
        try:
            auth_str = base64.decodebytes(bytes(auth_str, 'utf-8'))
            auth_str = auth_str.decode('utf-8')
        except AttributeError:
            auth_str = base64.decodestring(auth_str)
        username, password = auth_str.split(':')
        accounts.login(username, password)

    def POST(self):
        i = web.input(olid=None, file={}, redirect_url=None, url="")

        if not i.olid:
            self.error(i, "olid missing")

        key = '/books/' + i.olid
        book = web.ctx.site.get(key)
        if not book:
            raise self.error(i, "bad olid")

        try:
            auth_header = http_basic_auth()
            self.login(auth_header)
        except accounts.ClientException:
            raise self.auth_failed("Invalid credentials")

        from openlibrary.plugins.upstream import covers  # noqa: PLC0415

        add_cover = covers.add_cover()

        data = add_cover.upload(key, i)

        if coverid := data.get('id'):
            add_cover.save(book, coverid)
            raise self.success(i)
        else:
            raise self.error(i, "upload failed")


add_hook("import", importapi)
add_hook("ils_search", ils_search)
add_hook("ils_cover_upload", ils_cover_upload)
add_hook("import/ia", ia_importapi)
