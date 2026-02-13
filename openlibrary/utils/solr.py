"""Python library for accessing Solr"""

import logging
import re
from collections.abc import Callable, Iterable
from typing import Literal, TypeVar
from urllib.parse import urlencode, urlsplit

import httpx
import web

from openlibrary.utils.async_utils import async_bridge

logger = logging.getLogger("openlibrary.logger")


T = TypeVar('T')

DEFAULT_SOLR_TIMEOUT_SECONDS = 10
DEFAULT_PASS_TIME_ALLOWED = True


SolrRequestLabel = Literal[
    'UNLABELLED',
    'BOOK_SEARCH',
    'BOOK_SEARCH_API',
    'BOOK_SEARCH_FACETS',
    'BOOK_CAROUSEL',
    'AUTHOR_BOOKS_PAGE',
    # /get endpoint
    'GET_WORK_SOLR_DATA',
    # Subject, publisher pages
    'SUBJECT_ENGINE_PAGE',
    'SUBJECT_ENGINE_API',
    # Used for the internal request made by solr to choose the best edition
    # during a normal book search
    'EDITION_MATCH',
    'LIST_SEARCH',
    'LIST_SEARCH_API',
    'LIST_CAROUSEL',
    'SUBJECT_SEARCH',
    'SUBJECT_SEARCH_API',
    'AUTHOR_SEARCH',
    'AUTHOR_SEARCH_API',
]


class Solr:
    def __init__(self, base_url):
        """
        :param base_url: The base url of the solr server/collection. E.g. http://localhost:8983/solr/openlibrary
        """
        self.base_url = base_url
        self.host = urlsplit(self.base_url)[1]
        self.async_session = httpx.AsyncClient()

    @staticmethod
    def escape(query):
        r"""Escape special characters in the query string

        >>> Solr.escape("a[b]c")
        'a\\[b\\]c'
        """
        chars = r'+-!(){}[]^"~*?:\\'
        pattern = re.compile("([%s])" % re.escape(chars))
        return pattern.sub(r'\\\1', query)

    async def get_async(
        self,
        key: str,
        fields: list[str] | None = None,
        doc_wrapper: Callable[[dict], T] = web.storage,
        request_label: SolrRequestLabel = 'UNLABELLED',
    ) -> T | None:
        """Get a specific item from solr"""
        logger.debug(f"solr /get: {key}, {fields}")
        resp = (
            await self.async_session.get(
                f"{self.base_url}/get",
                # It's unclear how field=None is getting in here; a better fix would be at the source.
                params={
                    'id': key,
                    **(
                        {'fl': ','.join([field for field in fields if field])}
                        if fields
                        else {}
                    ),
                    'ol.label': request_label,
                },
                timeout=DEFAULT_SOLR_TIMEOUT_SECONDS,
            )
        ).json()

        # Solr returns {doc: null} if the record isn't there
        return doc_wrapper(resp['doc']) if resp['doc'] else None

    async def get_many_async(
        self,
        keys: Iterable[str],
        fields: Iterable[str] | None = None,
        doc_wrapper: Callable[[dict], T] = web.storage,
    ) -> list[T]:
        ids = list(keys)
        if not ids:
            return []
        logger.debug(f"solr /get: {ids}, {fields}")
        resp = (
            await self.async_session.post(
                f"{self.base_url}/get",
                data={
                    'ids': ','.join(ids),
                    **({'fl': ','.join(fields)} if fields else {}),
                },
                timeout=DEFAULT_SOLR_TIMEOUT_SECONDS,
            )
        ).json()
        return [doc_wrapper(doc) for doc in resp['response']['docs']]

    async def update_in_place_async(
        self,
        request,
        commit: bool = False,
        _timeout: int | None = DEFAULT_SOLR_TIMEOUT_SECONDS,
    ):
        resp = (
            await self.async_session.post(
                f'{self.base_url}/update?update.partial.requireInPlace=true&commit={commit}',
                json=request,
                timeout=_timeout,
            )
        ).json()
        return resp

    async def select_async(
        self,
        query,
        fields=None,
        facets=None,
        rows=None,
        start=None,
        doc_wrapper=None,
        facet_wrapper=None,
        _timeout=DEFAULT_SOLR_TIMEOUT_SECONDS,
        _pass_time_allowed=DEFAULT_PASS_TIME_ALLOWED,
        **kw,
    ):
        """Asynchronously execute a solr query.

        query can be a string or a dictionary. If query is a dictionary, query
        is constructed by concatenating all the key-value pairs with AND condition.
        """
        params = {'wt': 'json'}

        for k, v in kw.items():
            # convert keys like facet_field to facet.field
            params[k.replace('_', '.')] = v

        params['q'] = self._prepare_select(query)

        if rows is not None:
            params['rows'] = rows
        params['start'] = start or 0

        if fields:
            params['fl'] = ",".join(fields)

        if facets:
            params['facet'] = "true"
            params['facet.field'] = []

            for f in facets:
                if isinstance(f, dict):
                    name = f.pop("name")
                    for k, v in f.items():
                        params[f"f.{name}.facet.{k}"] = v
                else:
                    name = f
                params['facet.field'].append(name)

        json_data = (
            await self.raw_request(
                'select',
                urlencode(params, doseq=True),
                _timeout=_timeout,
                _pass_time_allowed=_pass_time_allowed,
            )
        ).json()

        return self._parse_solr_result(
            json_data, doc_wrapper=doc_wrapper, facet_wrapper=facet_wrapper
        )

    # Non-async versions for backwards compatibility
    get = async_bridge.wrap(get_async)
    get_many = async_bridge.wrap(get_many_async)
    update_in_place = async_bridge.wrap(update_in_place_async)
    select = async_bridge.wrap(select_async)

    async def raw_request(
        self,
        path_or_url: str,
        payload: str,
        _timeout: int | None = DEFAULT_SOLR_TIMEOUT_SECONDS,
        _pass_time_allowed: bool = True,
    ) -> httpx.Response:
        """
        :param _pass_time_allowed: If False, solr will continue processing the query
            server-side even if the client has timed out. This is useful for when
            you want a long-running query to complete and populate Solr's caches,
            which will result in subsequent requests for that same query to possibly
            not time out.
        """
        if path_or_url.startswith("http"):
            # TODO: Should this only take a path, not a full url? Would need to
            # update worksearch.code.execute_solr_query accordingly.
            url = path_or_url
        else:
            url = f'{self.base_url}/{path_or_url.lstrip("/")}'

        if _timeout is not None and _pass_time_allowed:
            if '?' in url:
                url += f'&timeAllowed={_timeout * 1000}'
            else:
                url += f'?timeAllowed={_timeout * 1000}'

        # switch to POST request when the payload is too big.
        # XXX: would it be a good idea to switch to POST always?
        if len(payload) < 500:
            sep = '&' if '?' in url else '?'
            url = url + sep + payload
            logger.debug("solr request: %s", url)
            return await self.async_session.get(url, timeout=_timeout)
        else:
            logger.debug("solr request: %s ...", url)
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            }
            return await self.async_session.post(
                url, data=payload, headers=headers, timeout=_timeout
            )

    def _parse_solr_result(self, result, doc_wrapper, facet_wrapper):
        response = result['response']

        doc_wrapper = doc_wrapper or web.storage
        facet_wrapper = facet_wrapper or (
            lambda name, value, count: web.storage(locals())
        )

        d = web.storage()
        d.num_found = response['numFound']
        d.docs = [doc_wrapper(doc) for doc in response['docs']]

        if 'facet_counts' in result:
            d.facets = {}
            for k, v in result['facet_counts']['facet_fields'].items():
                d.facets[k] = [
                    facet_wrapper(k, value, count) for value, count in web.group(v, 2)
                ]

        if 'highlighting' in result:
            d.highlighting = result['highlighting']

        if 'spellcheck' in result:
            d.spellcheck = result['spellcheck']

        return d

    def _prepare_select(self, query):
        def escape(v):
            # TODO: improve this
            return v.replace('"', r'\"').replace("(", "\\(").replace(")", "\\)")

        def escape_value(v):
            if isinstance(v, tuple):  # hack for supporting range
                return f"[{escape(v[0])} TO {escape(v[1])}]"
            elif isinstance(v, list):  # one of
                return "(%s)" % " OR ".join(escape_value(x) for x in v)
            else:
                return '"%s"' % escape(v)

        if isinstance(query, dict):
            op = query.pop("_op", "AND")
            if op.upper() != "OR":
                op = "AND"
            op = " " + op + " "

            q = op.join(f'{k}:{escape_value(v)}' for k, v in query.items())
        else:
            q = query
        return q


if __name__ == '__main__':
    import doctest

    doctest.testmod()
