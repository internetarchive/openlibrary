import json
from dataclasses import dataclass
from typing import cast, override

import web

from infogami.plugins.api.code import jsonapi
from infogami.utils import delegate
from infogami.utils.flash import add_flash_message
from infogami.utils.template import render_template
from openlibrary.catalog import add_book
from openlibrary.core.vendors import get_amazon_metadata


class import_preview(delegate.page):
    path = "/import/preview"
    """Preview page for import API."""

    def GET(self):
        req = ImportPreviewRequest.from_input(web.input(provider='ia', identifier=''))
        req.save = False
        return render_template("import_preview.html", metadata_provider_factory, req)

    def POST(self):
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
        try:
            req = ImportPreviewRequest.from_input(web.input())
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        # GET requests should not save the import
        req.save = False

        return json.dumps(req.metadata_provider.do_import(req.identifier, req.save))

    @jsonapi
    def POST(self):
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


class InternetArchiveMetadataProvider(AbstractMetadataProvider):
    full_name = "Internet Archive"
    id_name = 'ia'


class AmazonMetadataProvider(AbstractMetadataProvider):
    full_name = "Amazon"
    id_name = 'amazon'

    @override
    def do_import(self, identifier: str, save: bool):
        id_type = "isbn" if identifier.isdigit() else "asin"
        import_record = get_amazon_metadata(
            id_=identifier, id_type=id_type, high_priority=True, stage_import=True
        )
        assert import_record, "No metadata found for the given identifier"
        return add_book.load(
            import_record,
            account_key='account/ImportBot',
            save=save,
        )


class GoogleBooksMetadataProvider(AbstractMetadataProvider):
    full_name = "Google Books"
    id_name = 'google'


class MetadataProviderFactory:
    def __init__(self):
        providers = [
            InternetArchiveMetadataProvider(),
            AmazonMetadataProvider(),
            GoogleBooksMetadataProvider(),
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
