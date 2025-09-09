"""Python library for accessing Solr"""

import asyncio
import logging
import re
import threading
from collections.abc import Callable, Iterable
from typing import TypeVar
from urllib.parse import urlencode, urlsplit

import httpx
import requests
import web

logger = logging.getLogger("openlibrary.logger")


T = TypeVar('T')


class Solr:
    def __init__(self, base_url):
        """
        :param base_url: The base url of the solr server/collection. E.g. http://localhost:8983/solr/openlibrary
        """
        self.base_url = base_url
        self.host = urlsplit(self.base_url)[1]
        self.session = requests.Session()
        self.httpx_session = httpx.AsyncClient()

        # Start a persistent event loop in a background thread.
        # This avoids creating/destroying a loop on every call to select().
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def close(self):
        """
        Gracefully shuts down the background event loop and the httpx session.
        This method should be called when the Solr instance is no longer needed.
        """
        if self._thread.is_alive():
            # Schedule the closing of the httpx session in the event loop
            asyncio.run_coroutine_threadsafe(
                self.httpx_session.aclose(), self._loop
            ).result()
            # Stop the loop
            self._loop.call_soon_threadsafe(self._loop.stop)
            # Wait for the thread to terminate (optional, but good practice)
            self._thread.join()

    def escape(self, query):
        r"""Escape special characters in the query string

        >>> solr = Solr("")
        >>> solr.escape("a[b]c")
        'a\\[b\\]c'
        """
        chars = r'+-!(){}[]^"~*?:\\'
        pattern = re.compile("([%s])" % re.escape(chars))
        return pattern.sub(r'\\\1', query)

    def get(
        self,
        key: str,
        fields: list[str] | None = None,
        doc_wrapper: Callable[[dict], T] = web.storage,
    ) -> T | None:
        """Get a specific item from solr"""
        logger.info(f"solr /get: {key}, {fields}")
        resp = self.session.get(
            f"{self.base_url}/get",
            # It's unclear how field=None is getting in here; a better fix would be at the source.
            params={
                'id': key,
                **(
                    {'fl': ','.join([field for field in fields if field])}
                    if fields
                    else {}
                ),
            },
        ).json()

        # Solr returns {doc: null} if the record isn't there
        return doc_wrapper(resp['doc']) if resp['doc'] else None

    def get_many(
        self,
        keys: Iterable[str],
        fields: Iterable[str] | None = None,
        doc_wrapper: Callable[[dict], T] = web.storage,
    ) -> list[T]:
        if not keys:
            return []
        logger.info(f"solr /get: {keys}, {fields}")
        resp = self.session.post(
            f"{self.base_url}/get",
            data={
                'ids': ','.join(keys),
                **({'fl': ','.join(fields)} if fields else {}),
            },
        ).json()
        return [doc_wrapper(doc) for doc in resp['response']['docs']]

    def update_in_place(self, request, commit: bool = False):
        resp = requests.post(
            f'{self.base_url}/update?update.partial.requireInPlace=true&commit={commit}',
            json=request,
        ).json()
        return resp

    def select(
        self,
        query,
        fields=None,
        facets=None,
        rows=None,
        start=None,
        doc_wrapper=None,
        facet_wrapper=None,
        _timeout=None,
        **kw,
    ):
        """Execute a solr query.

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

        # MODIFICATION: Instead of asyncio.run(), submit the coroutine to the
        # background event loop and wait for its result.
        coro = self.async_raw_request(
            'select',
            urlencode(params, doseq=True),
            _timeout=_timeout,
        )
        # run_coroutine_threadsafe returns a future. .result() waits for completion.
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        # The result of the coroutine is an httpx.Response object. We need its JSON content.
        response = future.result()
        json_data = response.json()

        return self._parse_solr_result(
            json_data, doc_wrapper=doc_wrapper, facet_wrapper=facet_wrapper
        )

    async def async_raw_request(
        self,
        path_or_url: str,
        payload: str,
        _timeout: int | None = None,
    ) -> httpx.Response:
        if path_or_url.startswith("http"):
            # TODO: Should this only take a path, not a full url? Would need to
            # update worksearch.code.execute_solr_query accordingly.
            url = path_or_url
        else:
            url = f'{self.base_url}/{path_or_url.lstrip("/")}'

        if _timeout is not None:
            timeout = _timeout
        else:
            timeout = 10

        # switch to POST request when the payload is too big.
        # XXX: would it be a good idea to switch to POST always?
        if len(payload) < 500:
            sep = '&' if '?' in url else '?'
            url = url + sep + payload
            logger.info("solr request: %s", url)
            return await self.httpx_session.get(url, timeout=timeout)
        else:
            logger.info("solr request: %s ...", url)
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            }
            return await self.httpx_session.post(
                url, data=payload, headers=headers, timeout=timeout
            )

    def raw_request(
        self,
        path_or_url: str,
        payload: str,
        _timeout: int | None = None,
    ) -> requests.Response:
        if path_or_url.startswith("http"):
            # TODO: Should this only take a path, not a full url? Would need to
            # update worksearch.code.execute_solr_query accordingly.
            url = path_or_url
        else:
            url = f'{self.base_url}/{path_or_url.lstrip("/")}'

        if _timeout is not None:
            timeout = _timeout
        else:
            timeout = 10

        # switch to POST request when the payload is too big.
        # XXX: would it be a good idea to switch to POST always?
        if len(payload) < 500:
            sep = '&' if '?' in url else '?'
            url = url + sep + payload
            logger.info("solr request: %s", url)
            return self.session.get(url, timeout=timeout)
        else:
            logger.info("solr request: %s ...", url)
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            }
            return self.session.post(
                url, data=payload, headers=headers, timeout=timeout
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
