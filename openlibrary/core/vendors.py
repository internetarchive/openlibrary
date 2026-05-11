from __future__ import annotations

import logging
import re
import time
from types import MappingProxyType
from typing import Any, Literal, TypedDict

import httpx
import requests
from dateutil import parser as isoparser
from paapi5_python_sdk.api.default_api import DefaultApi
from paapi5_python_sdk.api_client import Configuration
from paapi5_python_sdk.get_items_request import GetItemsRequest
from paapi5_python_sdk.get_items_resource import GetItemsResource
from paapi5_python_sdk.partner_type import PartnerType
from paapi5_python_sdk.rest import ApiException, RESTClientObject
from paapi5_python_sdk.search_items_request import SearchItemsRequest

from openlibrary import accounts
from openlibrary.catalog.add_book import load
from openlibrary.core import cache
from openlibrary.core import helpers as h
from openlibrary.utils import dateutil, uniq
from openlibrary.utils.isbn import (
    isbn_10_to_isbn_13,
    isbn_13_to_isbn_10,
    normalize_isbn,
)

logger = logging.getLogger("openlibrary.vendors")
session = requests.Session()
async_session = httpx.AsyncClient()

BETTERWORLDBOOKS_API_URL = "https://products.bwbcontent.com/service.aspx?IncludeAmazon=True&ItemId="
affiliate_server_url = None
BWB_AFFILIATE_LINK = "http://www.anrdoezrs.net/links/{}/type/dlg/http://www.betterworldbooks.com/-id-%s".format(h.affiliate_id("betterworldbooks"))
AMAZON_FULL_DATE_RE = re.compile(r"\d{4}-\d\d-\d\d")
ISBD_UNIT_PUNCT = " : "  # ISBD cataloging title-unit separator punctuation


def setup(config):
    global affiliate_server_url
    affiliate_server_url = config.get("affiliate_server")


def get_lexile(isbn):
    try:
        url = "https://atlas-fab.lexile.com/free/books/" + str(isbn)
        headers = {"accept": "application/json; version=1.0"}
        lexile = session.get(url, headers=headers)
        lexile.raise_for_status()  # this will raise an error for us if the http status returned is not 200 OK
        data = lexile.json()
        return data, data.get("error_msg")
    except Exception as e:  # noqa: BLE001
        if e.response.status_code not in [200, 404]:
            raise Exception(f"Got bad response back from server: {e}")
        return {}, e


class AmazonAPI:
    """
    Amazon Product Advertising API 5.0 wrapper for Python
    See https://webservices.amazon.com/paapi5/documentation/
    """

    RESOURCES = MappingProxyType(
        {
            "all": [  # Hack: pulls all resource consts from GetItemsResource
                getattr(GetItemsResource, v) for v in vars(GetItemsResource) if v.isupper()
            ],
            "import": [
                GetItemsResource.IMAGES_PRIMARY_LARGE,
                GetItemsResource.ITEMINFO_BYLINEINFO,
                GetItemsResource.ITEMINFO_CONTENTINFO,
                GetItemsResource.ITEMINFO_MANUFACTUREINFO,
                GetItemsResource.ITEMINFO_PRODUCTINFO,
                GetItemsResource.ITEMINFO_TITLE,
                GetItemsResource.ITEMINFO_CLASSIFICATIONS,
                GetItemsResource.OFFERS_LISTINGS_PRICE,
            ],
            "prices": [GetItemsResource.OFFERS_LISTINGS_PRICE],
        }
    )

    def __init__(
        self,
        key: str,
        secret: str,
        tag: str,
        host: str = "webservices.amazon.com",
        region: str = "us-east-1",
        throttling: float = 0.9,
        proxy_url: str = "",
    ) -> None:
        """
        Creates an instance containing your API credentials. Additionally,
        instantiating this class requires a `proxy_url` parameter as of January
        10th, 2025 because `ol-home0` has no direct internet access.

        :param str key: affiliate key
        :param str secret: affiliate secret
        :param str tag: affiliate string
        :param str host: which server to query
        :param str region: which regional host to query
        :param float throttling: Reduce this value to wait longer between API calls.
        """
        self.tag = tag
        self.throttling = throttling
        self.last_query_time = time.time()

        self.api = DefaultApi(access_key=key, secret_key=secret, host=host, region=region)

        # Replace the api object with one that supports the HTTP proxy. See #10310.
        if proxy_url:
            configuration = Configuration()
            configuration.proxy = proxy_url
            rest_client = RESTClientObject(configuration=configuration)
            self.api.api_client.rest_client = rest_client

    def search(self, keywords):
        """Adding method to test amz searches from the CLI, unused otherwise"""
        return self.api.search_items(
            SearchItemsRequest(
                partner_tag=self.tag,
                partner_type=PartnerType.ASSOCIATES,
                keywords=keywords,
            )
        )

    def get_product(self, asin: str, serialize: bool = False, **kwargs):
        if products := self.get_products([asin], **kwargs):
            return next(self.serialize(p) if serialize else p for p in products)

    def get_products(
        self,
        asins: list | str,
        serialize: bool = False,
        marketplace: str = "www.amazon.com",
        resources: Any | None = None,
        **kwargs,
    ) -> list | None:
        """
        :param str asins: One or more ItemIds like ASIN that uniquely identify an item
        or product URL. (Max 10) Separated by comma or as a list.
        """
        # Wait before doing the request
        wait_time = 1 / self.throttling - (time.time() - self.last_query_time)
        if wait_time > 0:
            time.sleep(wait_time)
        self.last_query_time = time.time()

        item_ids = asins if isinstance(asins, list) else [asins]
        _resources = self.RESOURCES[resources or "import"]
        try:
            request = GetItemsRequest(
                partner_tag=self.tag,
                partner_type=PartnerType.ASSOCIATES,
                marketplace=marketplace,
                item_ids=item_ids,
                resources=_resources,
                **kwargs,
            )
        except ApiException:
            logger.error(f"Amazon fetch failed for: {', '.join(item_ids)}", exc_info=True)
            return None
        response = self.api.get_items(request)
        products = [p for p in response.items_result.items if p] if response.items_result else []
        return products if not serialize else [self.serialize(p) for p in products]

    @staticmethod
    def serialize(product: Any) -> dict:
        """Takes a full Amazon product Advertising API returned AmazonProduct
        with multiple ResponseGroups, and extracts the data we are
        interested in.

        :param AmazonAPI product:
        :return: Amazon metadata for one product

        {
          'price': '$54.06',
          'price_amt': 5406,
          'physical_format': 'hardcover',
          'authors': [{'name': 'Guterson, David'}],
          'publish_date': 'Jan 21, 2020',
          #'dimensions': {
          #  'width': [1.7, 'Inches'],
          #  'length': [8.5, 'Inches'],
          #  'weight': [5.4, 'Pounds'],
          #  'height': [10.875, 'Inches']
          # },
          'publishers': ['Victory Belt Publishing'],
          'source_records': ['amazon:1628603976'],
          'title': 'Boundless: Upgrade Your Brain, Optimize Your Body & Defy Aging',
          'url': 'https://www.amazon.com/dp/1628603976/?tag=internetarchi-20',
          'number_of_pages': 640,
          'cover': 'https://m.media-amazon.com/images/I/51IT9MV3KqL._AC_.jpg',
          'languages': ['English']
          'edition_num': '1'
        }

        """
        if not product:
            return {}  # no match?

        item_info = getattr(product, "item_info")
        images = getattr(product, "images")
        edition_info = item_info and getattr(item_info, "content_info")
        attribution = item_info and getattr(item_info, "by_line_info")
        price = getattr(product, "offers") and product.offers.listings and product.offers.listings[0].price
        brand = attribution and getattr(attribution, "brand") and getattr(attribution.brand, "display_value")
        manufacturer = (
            item_info
            and getattr(item_info, "by_line_info")
            and getattr(item_info.by_line_info, "manufacturer")
            and item_info.by_line_info.manufacturer.display_value
        )
        product_group = (
            item_info
            and getattr(
                item_info,
                "classifications",
            )
            and getattr(item_info.classifications, "product_group")
            and item_info.classifications.product_group.display_value
        )
        languages = []
        if edition_info and getattr(edition_info, "languages"):
            # E.g.
            # 'languages': {
            #     'display_values': [
            #         {'display_value': 'French', 'type': 'Published'},
            #         {'display_value': 'French', 'type': 'Original Language'},
            #         {'display_value': 'French', 'type': 'Unknown'},
            #     ],
            #     'label': 'Language',
            #     'locale': 'en_US',
            # },
            # Note: We don't need to convert from e.g. "French" to "fre"; the
            # import endpoint does that.
            languages = uniq(lang.display_value for lang in getattr(edition_info.languages, "display_values", []) if lang.type != "Original Language")
        try:
            publish_date = edition_info and edition_info.publication_date and isoparser.parse(edition_info.publication_date.display_value).strftime("%b %d, %Y")
        except Exception:
            logger.exception(f"serialize({product})")
            publish_date = None

        asin_is_isbn10 = not product.asin.startswith("B")
        isbn_13 = isbn_10_to_isbn_13(product.asin) if asin_is_isbn10 else None

        book = {
            "url": "https://www.amazon.com/dp/{}/?tag={}".format(product.asin, h.affiliate_id("amazon")),
            "source_records": [f"amazon:{product.asin}"],
            "isbn_10": [product.asin] if asin_is_isbn10 else [],
            "isbn_13": [isbn_13] if isbn_13 else [],
            "price": price and price.display_amount,
            "price_amt": price and price.amount and int(100 * price.amount),
            "title": (item_info and item_info.title and getattr(item_info.title, "display_value")),
            "cover": (
                images.primary.large.url
                if images and images.primary and images.primary.large and images.primary.large.url and "/01RmK+J4pJL." not in images.primary.large.url
                else None
            ),
            "authors": attribution and [{"name": contrib.name} for contrib in attribution.contributors or [] if contrib.role == "Author"],
            "contributors": attribution
            and [{"name": contrib.name, "role": "Translator"} for contrib in attribution.contributors or [] if contrib.role == "Translator"],
            "publishers": list({p for p in (brand, manufacturer) if p}),
            **(
                {"number_of_pages": edition_info.pages_count.display_value}
                if (
                    edition_info
                    and edition_info.pages_count
                    # Note this intentionally excludes 0
                    and edition_info.pages_count.display_value
                )
                else {}
            ),
            "edition_num": (edition_info and edition_info.edition and edition_info.edition.display_value),
            "publish_date": publish_date,
            "product_group": product_group,
            "physical_format": (item_info and item_info.classifications and getattr(item_info.classifications.binding, "display_value", "").lower()),
            **({"languages": languages} if languages else {}),
        }

        if is_dvd(book):
            return {}
        return book


def is_dvd(book) -> bool:
    """
    If product_group or physical_format is a dvd, it will return True.
    """
    product_group = book["product_group"]
    physical_format = book["physical_format"]

    try:
        product_group = product_group.lower()
    except AttributeError:
        product_group = None

    try:
        physical_format = physical_format.lower()
    except AttributeError:
        physical_format = None

    return "dvd" in [product_group, physical_format]


class AmazonCreatorsAPI:
    """
    Amazon Creators API wrapper — replacement for AmazonAPI (PA-API 5.0).

    Uses the `python-amazon-paapi` library (amazon_creatorsapi module).
    Auth: OAuth 2.0 credential_id + credential_secret instead of AWS key+secret.
    Exposes the same public interface as AmazonAPI so it is a drop-in replacement
    in affiliate_server.py.

    See: https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction
    Migration: https://affiliate-program.amazon.com/creatorsapi/docs/en-us/migrating-to-creatorsapi-from-paapi
    """

    # Browse-node filtering constants — compiled once at class definition time.
    _GENERIC_NODES: frozenset[str] = frozenset({"Books", "Subjects", "Departments"})
    _UUID_RE: re.Pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-", re.IGNORECASE)
    _INTERNAL_TERMS: re.Pattern = re.compile(
        r"ASIN|^Test node|^Sponsored|^Textbook Rental|^Special Offer"
        r"|Challenge Faves|Goodreads",
        re.IGNORECASE,
    )

    def __init__(
        self,
        credential_id: str,
        credential_secret: str,
        tag: str,
        version: str = "3.1",
        country: str = "US",
        throttling: float = 0.9,
        proxy_url: str = "",
        proxy_creds: str = "",
    ) -> None:
        """
        :param str credential_id: Creators API key / credential ID (OAuth 2.0)
        :param str credential_secret: Creators API secret / credential secret (OAuth 2.0)
        :param str tag: affiliate tag / Application Id from the Creators API credentials portal
        :param str version: Creators API version string from the credentials portal (e.g. '3.1')
        :param str country: two-letter country code (default 'US')
        :param float throttling: Reduce this value to wait longer between API calls.
            Minimum inter-call gap is ``1 / throttling`` seconds (same semantics as
            AmazonAPI).  The library's internal throttle is disabled so this class
            is the sole source of rate-limiting.
        :param str proxy_url: HTTP proxy URL for environments without direct internet access
        """
        self.tag = tag
        self.throttling = throttling
        self.last_query_time = time.time()

        # Lazy import: python-amazon-paapi may not be installed in all environments
        # (e.g. test runners that don't have the package). Importing here means the
        # rest of vendors.py loads fine; only AmazonCreatorsAPI instantiation fails.
        from amazon_creatorsapi import AmazonCreatorsApi, Country

        # Pass throttling=0 to the library so it never sleeps internally.
        # We own the throttle loop in get_products (1/throttling semantics),
        # matching AmazonAPI behaviour. Letting the library also sleep would
        # double the wait time at every call.
        self.api = AmazonCreatorsApi(
            credential_id=credential_id,
            credential_secret=credential_secret,
            version=version,
            tag=tag,
            country=getattr(Country, country),
            throttling=0,
        )

        # Inject proxy into underlying SDK rest client, mirroring the PA-API approach.
        # Required for ol-home0 which has no direct internet access. See #10310.
        if proxy_url:
            try:
                from creatorsapi_python_sdk.configuration import (
                    Configuration as CreatorsConfig,
                )
                from creatorsapi_python_sdk.rest import (
                    RESTClientObject as CreatorsRESTClient,
                )
                from urllib3 import make_headers

                configuration = CreatorsConfig()
                configuration.proxy = proxy_url
                configuration.proxy_headers = make_headers(proxy_basic_auth=proxy_creds)
                rest_client = CreatorsRESTClient(configuration=configuration)
                # _api_client is the ApiClient instance stored directly on
                # AmazonCreatorsApi; replace its rest_client to route all
                # outbound HTTP through the proxy.
                self.api._api_client.rest_client = rest_client
            except (ImportError, AttributeError):
                logger.warning(
                    "AmazonCreatorsAPI: could not inject proxy — falling back to environment-level proxy (HTTPS_PROXY)",
                    exc_info=True,
                )

    def get_product(self, asin: str, serialize: bool = False, **kwargs):
        if products := self.get_products([asin], **kwargs):
            return next(self.serialize(p) if serialize else p for p in products)

    def get_products(
        self,
        asins: list | str,
        serialize: bool = False,
        **kwargs,
    ) -> list | None:
        """
        :param asins: One or more ASINs. Max 10 per call.
        :param serialize: If True, run each product through serialize() before returning.

        Additional keyword args (e.g. `marketplace`, `resources`) are accepted and silently
        ignored for drop-in compatibility with AmazonAPI.get_products callers.
        """
        wait_time = 1 / self.throttling - (time.time() - self.last_query_time)
        if wait_time > 0:
            time.sleep(wait_time)
        self.last_query_time = time.time()

        item_ids = asins if isinstance(asins, list) else [asins]
        try:
            products = self.api.get_items(item_ids) or []
        except Exception as e:
            logger.error(
                f"AmazonCreatorsAPI fetch failed for: {', '.join(item_ids)}: {e}",
                exc_info=True,
            )
            return None

        return products if not serialize else [self.serialize(p) for p in products]

    @staticmethod
    def serialize(product: Any) -> dict:
        """
        Maps a Creators API Item object to the same dict shape as AmazonAPI.serialize(),
        plus new fields only available via the Creators API.

        New fields (not present in the legacy PA-API output):
          isbn_13         — sourced directly from external_ids.eans (more reliable than
                            computing from ISBN-10)
          categories      — Amazon browse node names, usable as OL subjects
          availability    — 'IN_STOCK', 'AVAILABLE_DATE', etc.
          price_savings_pct — discount percentage off list price
          list_price      — original list price string, e.g. '$17.00'
          image_variants  — alternate cover image URLs (back cover, spine, etc.)
        """
        if not product:
            return {}

        item_info = getattr(product, "item_info", None)
        images = getattr(product, "images", None)
        edition_info = item_info and getattr(item_info, "content_info", None)
        attribution = item_info and getattr(item_info, "by_line_info", None)

        # Creators API: offers_v2 replaces offers
        offers_v2 = getattr(product, "offers_v2", None)
        listings = getattr(offers_v2, "listings", None) if offers_v2 else None
        listing = listings[0] if listings else None
        price = listing and listing.price

        brand = attribution and getattr(attribution, "brand", None) and getattr(attribution.brand, "display_value", None)
        manufacturer = (
            item_info
            and getattr(item_info, "by_line_info", None)
            and getattr(item_info.by_line_info, "manufacturer", None)
            and item_info.by_line_info.manufacturer.display_value
        )
        product_group = (
            item_info
            and getattr(item_info, "classifications", None)
            and getattr(item_info.classifications, "product_group", None)
            and item_info.classifications.product_group.display_value
        )

        languages = []
        if edition_info and getattr(edition_info, "languages", None):
            languages = uniq(lang.display_value for lang in getattr(edition_info.languages, "display_values", []) if lang.type != "Original Language")

        try:
            publish_date = edition_info and edition_info.publication_date and isoparser.parse(edition_info.publication_date.display_value).strftime("%b %d, %Y")
        except Exception:
            logger.exception(
                "AmazonCreatorsAPI.serialize: failed to parse publish_date for asin=%s",
                product.asin,
            )
            publish_date = None

        asin_is_isbn10 = not product.asin.startswith("B")

        # Prefer ISBN-13 from external_ids.eans (authoritative); fall back to
        # computing it from the ISBN-10 as we did with PA-API.
        external_ids = item_info and getattr(item_info, "external_ids", None)
        eans = external_ids and getattr(external_ids, "eans", None) and getattr(external_ids.eans, "display_values", None)
        if eans:
            isbn_13_list = [e for e in eans if len(e) == 13]
        elif asin_is_isbn10:
            derived = isbn_10_to_isbn_13(product.asin)
            isbn_13_list = [derived] if derived else []
        else:
            isbn_13_list = []

        # Browse node categories: unique context_free_name from all nodes +
        # their immediate ancestors, excluding generic roots and Amazon-internal
        # nodes (UUIDs, test nodes, internal campaign labels).
        browse_node_info = getattr(product, "browse_node_info", None)
        browse_nodes = (browse_node_info and getattr(browse_node_info, "browse_nodes", None)) or []
        categories = uniq(
            name
            for node in browse_nodes
            for name in (
                [getattr(node, "context_free_name", None)] + ([getattr(node.ancestor, "context_free_name", None)] if getattr(node, "ancestor", None) else [])
            )
            if name
            and name not in AmazonCreatorsAPI._GENERIC_NODES
            and not AmazonCreatorsAPI._UUID_RE.match(name)
            and not AmazonCreatorsAPI._INTERNAL_TERMS.search(name)
        )

        # Availability from the buy-box listing
        availability = listing and getattr(listing, "availability", None) and getattr(listing.availability, "type", None)

        # Savings: percentage off and original list price
        savings = price and getattr(price, "savings", None)
        price_savings_pct = savings and getattr(savings, "percentage", None)
        saving_basis = price and getattr(price, "saving_basis", None)
        saving_basis_money = saving_basis and getattr(saving_basis, "money", None)
        list_price = saving_basis_money and getattr(saving_basis_money, "display_amount", None)

        # Variant images (alternate covers: back, spine, etc.)
        variants = (images and getattr(images, "variants", None)) or []
        image_variants = [v.large.url for v in variants if getattr(v, "large", None) and getattr(v.large, "url", None)]

        book = {
            "url": "https://www.amazon.com/dp/{}/?tag={}".format(product.asin, h.affiliate_id("amazon")),
            "source_records": [f"amazon:{product.asin}"],
            "isbn_10": [product.asin] if asin_is_isbn10 else [],
            "isbn_13": isbn_13_list,
            # Creators API: price is OfferPriceV2 → price.money.display_amount
            "price": price and price.money and price.money.display_amount,
            "price_amt": (price and price.money and price.money.amount and int(100 * price.money.amount)),
            "title": (item_info and item_info.title and getattr(item_info.title, "display_value", None)),
            "cover": (
                images.primary.large.url
                if images and images.primary and images.primary.large and images.primary.large.url and "/01RmK+J4pJL." not in images.primary.large.url
                else None
            ),
            "authors": attribution and [{"name": contrib.name} for contrib in (getattr(attribution, "contributors", None) or []) if contrib.role == "Author"],
            "contributors": attribution
            and [{"name": contrib.name, "role": "Translator"} for contrib in (getattr(attribution, "contributors", None) or []) if contrib.role == "Translator"],
            "publishers": list({p for p in (brand, manufacturer) if p}),
            **(
                {"number_of_pages": edition_info.pages_count.display_value}
                if (edition_info and edition_info.pages_count and edition_info.pages_count.display_value)
                else {}
            ),
            "edition_num": (edition_info and edition_info.edition and edition_info.edition.display_value),
            "publish_date": publish_date,
            "product_group": product_group,
            "physical_format": (item_info and item_info.classifications and getattr(item_info.classifications.binding, "display_value", "").lower()),
            **({"languages": languages} if languages else {}),
            # --- Creators API additions ---
            **({"categories": categories} if categories else {}),
            **({"availability": availability} if availability else {}),
            **({"price_savings_pct": price_savings_pct} if price_savings_pct else {}),
            **({"list_price": list_price} if list_price else {}),
            **({"image_variants": image_variants} if image_variants else {}),
        }

        if is_dvd(book):
            return {}
        return book


def get_amazon_metadata(
    id_: str,
    id_type: Literal["asin", "isbn"] = "isbn",
    resources: Any = None,
    high_priority: bool = False,
    stage_import: bool = True,
) -> dict | None:
    """Main interface to Amazon LookupItem API. Will cache results.

    :param str id_: The item id: isbn (10/13), or Amazon ASIN.
    :param str id_type: 'isbn' or 'asin'.
    :param bool high_priority: Priority in the import queue. High priority
           goes to the front of the queue.
    param bool stage_import: stage the id_ for import if not in the cache.
    :return: A single book item's metadata, or None.
    """
    return cached_get_amazon_metadata(
        id_,
        id_type=id_type,
        resources=resources,
        high_priority=high_priority,
        stage_import=stage_import,
    )


def search_amazon(title: str = "", author: str = "") -> dict:  # type: ignore[empty-body]
    """Uses the Amazon Product Advertising API ItemSearch operation to search for
    books by author and/or title.
    https://docs.aws.amazon.com/AWSECommerceService/latest/DG/ItemSearch.html
    XXX! Broken while migrating from paapi 4.0 to 5.0
    :return: dict of "results", a list of one or more found books, with metadata.
    """
    pass


def _get_amazon_metadata(
    id_: str,
    id_type: Literal["asin", "isbn"] = "isbn",
    resources: Any = None,
    high_priority: bool = False,
    stage_import: bool = True,
    timeout: float = 4.0,
) -> dict | None:
    """Uses the Amazon Product Advertising API ItemLookup operation to locate a
    specific book by identifier; either 'isbn' or 'asin'.
    https://webservices.amazon.com/paapi5/documentation/get-items.html

    :param str id_: The item id: isbn (10/13), or Amazon ASIN.
    :param str id_type: 'isbn' or 'asin'.
    :param Any resources: Used for AWSE Commerce Service lookup
           See https://webservices.amazon.com/paapi5/documentation/get-items.html
    :param bool high_priority: Priority in the import queue. High priority
           goes to the front of the queue.
    param bool stage_import: stage the id_ for import if not in the cache.
    :return: A single book item's metadata, or None.
    """
    if not affiliate_server_url:
        return None

    if id_type == "isbn":
        isbn = normalize_isbn(id_)
        if isbn is None:
            return None
        id_ = isbn
        if len(id_) == 13 and id_.startswith("978"):
            isbn = isbn_13_to_isbn_10(id_)
            if isbn is None:
                return None
            id_ = isbn

    try:
        priority = "true" if high_priority else "false"
        stage = "true" if stage_import else "false"
        r = session.get(
            f"http://{affiliate_server_url}/isbn/{id_}?high_priority={priority}&stage_import={stage}",
            timeout=timeout,
        )
        r.raise_for_status()
        if data := r.json().get("hit"):
            return data
        else:
            return None
    except requests.exceptions.ConnectionError:
        logger.exception("Affiliate Server unreachable")
    except requests.exceptions.HTTPError:
        logger.exception(f"Affiliate Server: id {id_} not found")
    return None


def stage_bookworm_metadata(identifier: str | None) -> dict | None:
    """
    `stage` metadata, if found. into `import_item` via BookWorm.

    :param str identifier: ISBN 10, ISBN 13, or B*ASIN. Spaces, hyphens, etc. are fine.
    """
    if not identifier:
        return None
    try:
        r = session.get(f"http://{affiliate_server_url}/isbn/{identifier}?high_priority=true&stage_import=true")
        r.raise_for_status()
        if data := r.json().get("hit"):
            return data
        else:
            return None
    except requests.exceptions.ConnectionError:
        logger.exception("Affiliate Server unreachable")
    except requests.exceptions.HTTPError:
        logger.exception(f"Affiliate Server: id {identifier} not found")
    return None


def split_amazon_title(full_title: str) -> tuple[str, str | None]:
    """
    Splits an Amazon title into (title, subtitle | None) and strips parenthetical
    tags.
    """

    # strip parenthetical blocks wherever they occur
    # can handle 1 level of nesting
    re_parens_strip = re.compile(r"\(([^\)\(]*|[^\(]*\([^\)]*\)[^\)]*)\)")
    full_title = re.sub(re_parens_strip, "", full_title)

    titles = full_title.split(":")
    subtitle = titles.pop().strip() if len(titles) > 1 else None
    title = ISBD_UNIT_PUNCT.join([unit.strip() for unit in titles])
    return (title, subtitle)


def clean_amazon_metadata_for_load(metadata: dict) -> dict:
    """This is a bootstrapping helper method which enables us to take the
    results of get_amazon_metadata() and create an OL book catalog record.

    :param dict metadata: Metadata representing an Amazon product.
    :return: A dict representing a book suitable for importing into OL.
    """

    conforming_fields = [
        "title",
        "authors",
        "contributors",
        "publish_date",
        "source_records",
        "number_of_pages",
        "languages",
        "publishers",
        "cover",
        "isbn_10",
        "isbn_13",
        "physical_format",
    ]
    conforming_metadata = {}
    for k in conforming_fields:
        # if valid key and value not None
        if metadata.get(k) is not None:
            conforming_metadata[k] = metadata[k]
    if source_records := metadata.get("source_records"):
        asin = source_records[0].replace("amazon:", "")
        if asin[0].isalpha():
            # Only store asin if it provides more information than ISBN
            conforming_metadata["identifiers"] = {"amazon": [asin]}
    title, subtitle = split_amazon_title(metadata["title"])
    conforming_metadata["title"] = title
    if subtitle:
        conforming_metadata["full_title"] = f"{title}{ISBD_UNIT_PUNCT}{subtitle}"
        conforming_metadata["subtitle"] = subtitle
    # Record original title if some content has been removed (i.e. parentheses)
    if metadata["title"] != conforming_metadata.get("full_title", title):
        conforming_metadata["notes"] = "Source title: %s" % metadata["title"]

    return conforming_metadata


def create_edition_from_amazon_metadata(id_: str, id_type: Literal["asin", "isbn"] = "isbn") -> str | None:
    """Fetches Amazon metadata by id from Amazon Product Advertising API, attempts to
    create OL edition from metadata, and returns the resulting edition key `/key/OL..M`
    if successful or None otherwise.

    :param str id_: The item id: isbn (10/13), or Amazon ASIN.
    :param str id_type: 'isbn' or 'asin'.
    :return: Edition key '/key/OL..M' or None
    """

    md = get_amazon_metadata(id_, id_type=id_type)

    if md and md.get("product_group") == "Book":
        with accounts.RunAs("ImportBot"):
            reply = load(clean_amazon_metadata_for_load(md), account_key="account/ImportBot")
            if reply and reply.get("success"):
                return reply["edition"].get("key")
    return None


def cached_get_amazon_metadata(*args, **kwargs):
    """If the cached data is `None`, it's likely a 503 throttling occurred on
    Amazon's side. Try again to fetch the value instead of using the
    cached value. It may 503 again, in which case the next access of
    this page will trigger another re-cache. If the Amazon API call
    succeeds but the book has no price data, then {"price": None} will
    be cached as to not trigger a re-cache (only the value `None`
    will cause re-cache)
    """

    # fetch/compose a cache controller obj for
    # "upstream.code._get_amazon_metadata"
    memoized_get_amazon_metadata = cache.memcache_memoize(
        _get_amazon_metadata,
        "upstream.code._get_amazon_metadata",
        timeout=dateutil.WEEK_SECS,
    )
    # fetch cached value from this controller
    result = memoized_get_amazon_metadata(*args, **kwargs)
    # if no result, then recache / update this controller's cached value
    return result or memoized_get_amazon_metadata.update(*args, **kwargs)[0]


class BetterWorldBooksMetadata(TypedDict):
    url: str
    isbn: str
    market_price: list[str] | None
    price: str | None
    price_amt: str | None
    qlt: str | None


class BetterWorldBooksMetadataError(TypedDict):
    error: str
    code: int


async def get_betterworldbooks_metadata(
    isbn: str,
) -> BetterWorldBooksMetadata | BetterWorldBooksMetadataError | None:
    """
    Automatically tries with ISBN 13 if ISBN 10 fails.

    :param str isbn: Unnormalisied ISBN10 or ISBN13
    :return: Metadata for a single BWB book, currently lited on their catalog, or
             an error dict.
    """

    isbn = normalize_isbn(isbn) or isbn
    if isbn is None:
        return None

    try:
        if (result := await _get_betterworldbooks_metadata(isbn)).get("price") is None:
            new_isbn = isbn_10_to_isbn_13(isbn)
            if new_isbn and new_isbn != isbn:
                result = await _get_betterworldbooks_metadata(new_isbn)
        return result
    except Exception:
        logger.exception(f"_get_betterworldbooks_metadata({isbn})")
        return betterworldbooks_fmt(isbn)


async def _get_betterworldbooks_metadata(
    isbn: str,
) -> BetterWorldBooksMetadata | BetterWorldBooksMetadataError:
    """Returns price and other metadata (currently minimal)
    for a book currently available on betterworldbooks.com

    :param str isbn: Normalised ISBN10 or ISBN13
    :return: Metadata for a single BWB book currently listed on their catalog,
            or an error dict.
    """

    url = BETTERWORLDBOOKS_API_URL + isbn
    response = await async_session.get(url, timeout=3)
    if response.status_code != requests.codes.ok:
        return {"error": response.text, "code": response.status_code}
    text = response.text
    new_qty = re.findall("<TotalNew>([0-9]+)</TotalNew>", text)
    new_price = re.findall(r"<LowestNewPrice>\$([0-9.]+)</LowestNewPrice>", text)
    used_price = re.findall(r"<LowestUsedPrice>\$([0-9.]+)</LowestUsedPrice>", text)
    used_qty = re.findall("<TotalUsed>([0-9]+)</TotalUsed>", text)
    market_price = re.findall(r"<LowestMarketPrice>\$([0-9.]+)</LowestMarketPrice>", text)
    price = qlt = None

    if used_qty and used_qty[0] and used_qty[0] != "0":
        price = used_price[0] if used_price else ""
        qlt = "used"

    if new_qty and new_qty[0] and new_qty[0] != "0":
        _price = new_price[0] if new_price else None
        if _price and (not price or float(_price) < float(price)):
            price = _price
            qlt = "new"

    first_market_price = ("$" + market_price[0]) if market_price else None
    return betterworldbooks_fmt(isbn, qlt, price, first_market_price)


def betterworldbooks_fmt(
    isbn: str,
    qlt: str | None = None,
    price: str | None = None,
    market_price: list[str] | None = None,
) -> BetterWorldBooksMetadata:
    """Defines a standard interface for returning bwb price info

    :param str qlt: Quality of the book, e.g. "new", "used"
    :param str price: Price of the book as a decimal str, e.g. "4.28"
    """
    price_fmt = f"${price} ({qlt})" if price and qlt else None
    return {
        "url": BWB_AFFILIATE_LINK % isbn,
        "isbn": isbn,
        "market_price": market_price,
        "price": price_fmt,
        "price_amt": price,
        "qlt": qlt,
    }
