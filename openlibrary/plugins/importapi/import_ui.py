import json
from dataclasses import dataclass
from typing import cast, override

import requests
import web

from infogami.plugins.api.code import jsonapi
from infogami.utils import delegate
from infogami.utils.flash import add_flash_message
from infogami.utils.template import render_template
from openlibrary.catalog import add_book
from openlibrary.catalog.marc.marc_binary import MarcBinary
from openlibrary.catalog.marc.parse import read_edition
from openlibrary.core.vendors import get_amazon_metadata


class import_preview(delegate.page):
    path = "/import/preview"
    """Preview page for import API."""

    def GET(self):
        user = web.ctx.site.get_user()

        if user is None:
            raise web.unauthorized()
        has_access = user and (
            (user.is_admin() or user.is_librarian()) or user.is_super_librarian()
        )
        if not has_access:
            raise web.forbidden()

        req = ImportPreviewRequest.from_input(
            web.input(provider='amazon', identifier='')
        )
        # GET requests should not save the import
        req.save = False
        return render_template("import_preview.html", metadata_provider_factory, req)

    def POST(self):
        user = web.ctx.site.get_user()

        if user is None:
            raise web.unauthorized()
        has_access = user and (
            (user.is_admin() or user.is_librarian()) or user.is_super_librarian()
        )
        if not has_access:
            raise web.forbidden()

        try:
            req = ImportPreviewRequest.from_input(web.input())
        except ValueError as e:
            add_flash_message("error", str(e))
            return render_template("import_preview.html", metadata_provider_factory)

        result = req.metadata_provider.do_import(req.identifier, req.save)

        if req.save:
            add_flash_message("success", "Import successful")
            return web.seeother(result['edition']['key'])
        else:
            return render_template(
                "import_preview.html",
                metadata_provider_factory,
                req=req,
                result=result,
            )


class import_preview_json(delegate.page):
    path = "/import/preview"
    encoding = "json"

    @jsonapi
    def GET(self):
        user = web.ctx.site.get_user()

        if user is None:
            raise web.unauthorized()
        has_access = user and (
            (user.is_admin() or user.is_librarian()) or user.is_super_librarian()
        )
        if not has_access:
            raise web.forbidden()

        try:
            req = ImportPreviewRequest.from_input(web.input())
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        # GET requests should not save the import
        req.save = False

        return json.dumps(req.metadata_provider.do_import(req.identifier, req.save))

    @jsonapi
    def POST(self):
        user = web.ctx.site.get_user()

        if user is None:
            raise web.unauthorized()
        has_access = user and (
            (user.is_admin() or user.is_librarian()) or user.is_super_librarian()
        )
        if not has_access:
            raise web.forbidden()

        try:
            req = ImportPreviewRequest.from_input(web.input())
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        return json.dumps(req.metadata_provider.do_import(req.identifier, req.save))


@dataclass
class ImportPreviewRequest:
    metadata_provider: 'AbstractMetadataProvider'
    identifier: str
    save: bool

    @staticmethod
    def from_input(i: dict) -> 'ImportPreviewRequest':
        source = cast(str | None, i.get('source'))
        provider = cast(str | None, i.get('provider'))

        if not source and not provider:
            raise ValueError("No provider specified")

        identifier: str | None = None
        if source:
            if ':' not in source:
                raise ValueError("Invalid source provided")

            provider_prefix, identifier = source.split(':', 1)
        elif provider:
            provider_prefix = provider
            identifier = cast(str | None, i.get('identifier'))

        metadata_provider = metadata_provider_factory.get_metadata_provider(
            provider_prefix
        )

        if not metadata_provider:
            raise ValueError("Invalid source provided")

        return ImportPreviewRequest(
            metadata_provider=metadata_provider,
            identifier=identifier or '',
            save=i.get('save', 'false') == 'true',
        )


class AbstractMetadataProvider:
    full_name: str
    id_name: str

    def do_import(self, identifier: str, save: bool):
        """Import metadata from the source."""
        raise NotImplementedError(
            f"do_import method not implemented for {self.__class__.__name__}"
        )


class AmazonMetadataProvider(AbstractMetadataProvider):
    full_name = "Amazon"
    id_name = 'amazon'

    @override
    def do_import(self, identifier: str, save: bool):
        id_type = "isbn" if identifier[0].isdigit() else "asin"
        import_record = get_amazon_metadata(
            id_=identifier, id_type=id_type, high_priority=True, stage_import=False
        )
        assert import_record, "No metadata found for the given identifier"
        return add_book.load(
            import_record,
            account_key='account/ImportBot',
            save=save,
        )


class IaMetadataProvider(AbstractMetadataProvider):
    full_name = "Internet Archive"
    id_name = 'ia'

    @override
    def do_import(self, identifier: str, save: bool):
        # This appears to be causing a circular dependency... only in tests?
        from openlibrary.plugins.importapi.code import ia_importapi  # noqa: PLC0415

        import_record, from_marc_record = ia_importapi.get_ia_import_record(
            identifier,
            require_marc=False,
            force_import=True,
            preview=not save,
        )
        assert import_record, "No metadata found for the given identifier"
        return add_book.load(
            import_record,
            account_key='account/ImportBot',
            from_marc_record=from_marc_record,
            save=save,
        )


class RawMarcMetadataProvider(AbstractMetadataProvider):
    full_name = "Raw MARC"
    id_name = 'marc'

    @override
    def do_import(self, identifier: str, save: bool):
        # The "ID" is a url, with a byte offset for the start of the MARC record.
        # Example: "https://archive.org/download/harvard_bibliographic_metadata/20220215_007.bib.mrc:35217689"
        url, offset = identifier.rsplit(':', 1)

        headers = {'Range': f'bytes={offset}-'}
        response = requests.get(url, headers=headers, stream=True)
        if response.status_code != 206:
            raise ValueError(
                f"Failed to fetch MARC record from {url}: {response.status_code}"
            )

        # The first 5 bytes are the length of the MARC record.
        marc_data = response.raw.read(5)
        if len(marc_data) < 5:
            raise ValueError("Invalid MARC record data: less than 5 bytes received")
        length = int(marc_data[:5])
        marc_data += response.raw.read(length - 5)
        marc_record = MarcBinary(marc_data)
        import_record = read_edition(marc_record)

        if 'source_records' not in import_record:
            import_record['source_records'] = [f'marc:{url}:{offset}:{length}']

        return add_book.load(
            import_record,
            account_key='account/ImportBot',
            from_marc_record=True,
            save=save,
        )


class MetadataProviderFactory:
    def __init__(self):
        providers = [
            AmazonMetadataProvider(),
            IaMetadataProvider(),
            RawMarcMetadataProvider(),
        ]
        self.metadata_providers = {provider.id_name: provider for provider in providers}

    def get_metadata_provider(
        self, provider_name: str
    ) -> AbstractMetadataProvider | None:
        if provider_name not in self.metadata_providers:
            return None
        return self.metadata_providers[provider_name]


metadata_provider_factory = MetadataProviderFactory()


def setup():
    pass


setup()
