import logging
import re
import sys
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from types import MappingProxyType
from typing import Any, cast

import luqum.tree
import web

import infogami
from openlibrary.plugins.upstream.utils import convert_iso_to_marc
from openlibrary.plugins.worksearch.schemes import SearchScheme
from openlibrary.solr.query_utils import (
    EmptyTreeError,
    fully_escape_query,
    luqum_parser,
    luqum_remove_child,
    luqum_remove_field,
    luqum_replace_child,
    luqum_replace_field,
    luqum_traverse,
)
from openlibrary.utils.ddc import (
    normalize_ddc,
    normalize_ddc_prefix,
    normalize_ddc_range,
)
from openlibrary.utils.isbn import normalize_isbn
from openlibrary.utils.lcc import (
    normalize_lcc_prefix,
    normalize_lcc_range,
    short_lcc_to_sortable_lcc,
)

logger = logging.getLogger("openlibrary.worksearch")
re_author_key = re.compile(r'(OL\d+A)')


class WorkSearchScheme(SearchScheme):
    universe = frozenset(['type:work'])
    all_fields = frozenset(
        {
            "key",
            "redirects",
            "title",
            "subtitle",
            "alternative_title",
            "alternative_subtitle",
            "cover_i",
            "ebook_access",
            "ebook_provider",
            "edition_count",
            "edition_key",
            "format",
            "by_statement",
            "publish_date",
            "lccn",
            "lexile",
            "ia",
            "oclc",
            "isbn",
            "contributor",
            "publish_place",
            "publisher",
            "first_sentence",
            "author_key",
            "author_name",
            "author_alternative_name",
            "subject",
            "person",
            "place",
            "time",
            "has_fulltext",
            "title_suggest",
            "publish_year",
            "language",
            "number_of_pages_median",
            "ia_count",
            "publisher_facet",
            "author_facet",
            "first_publish_year",
            "ratings_count",
            "readinglog_count",
            "want_to_read_count",
            "currently_reading_count",
            "already_read_count",
            # Subjects
            "subject_key",
            "person_key",
            "place_key",
            "time_key",
            # Classifications
            "lcc",
            "ddc",
            "lcc_sort",
            "ddc_sort",
            "osp_count",
            # Trending
            "trending_score_hourly_sum",
            "trending_z_score",
        }
    )
    non_solr_fields = frozenset(
        {
            'description',
            'providers',
        }
    )
    facet_fields = frozenset(
        {
            "has_fulltext",
            "author_facet",
            "language",
            "first_publish_year",
            "publisher_facet",
            "subject_facet",
            "person_facet",
            "place_facet",
            "time_facet",
            "public_scan_b",
        }
    )
    field_name_map = MappingProxyType(
        {
            'author': 'author_name',
            'authors': 'author_name',
            'by': 'author_name',
            'number_of_pages': 'number_of_pages_median',
            'publishers': 'publisher',
            'subtitle': 'alternative_subtitle',
            'title': 'alternative_title',
            'work_subtitle': 'subtitle',
            'work_title': 'title',
            'trending': 'trending_z_score',
            # "Private" fields
            # This is private because we'll change it to a multi-valued field instead of a
            # plain string at the next opportunity, which will make it much more usable.
            '_ia_collection': 'ia_collection_s',
        }
    )
    sorts = MappingProxyType(
        {
            'editions': 'edition_count desc',
            'old': 'def(first_publish_year, 9999) asc',
            'new': 'first_publish_year desc',
            'trending_score_hourly_sum': 'def(trending_score_hourly_sum, 0) desc',
            'trending_score_hourly_sum asc': 'def(trending_score_hourly_sum, 0) asc',
            'trending_score_hourly_sum desc': 'def(trending_score_hourly_sum, 0) desc',
            'trending': 'def(trending_z_score, 0) desc',
            'trending asc': 'def(trending_z_score, 0) asc',
            'trending desc': 'def(trending_z_score, 0) desc',
            'rating': 'ratings_sortable desc',
            'rating asc': 'ratings_sortable asc',
            'rating desc': 'ratings_sortable desc',
            'readinglog': 'readinglog_count desc',
            'want_to_read': 'want_to_read_count desc',
            'currently_reading': 'currently_reading_count desc',
            'already_read': 'already_read_count desc',
            'title': 'title_sort asc',
            'scans': 'ia_count desc',
            # Classifications
            'lcc_sort': 'lcc_sort asc',
            'lcc_sort asc': 'lcc_sort asc',
            'lcc_sort desc': 'lcc_sort desc',
            'ddc_sort': 'ddc_sort asc',
            'ddc_sort asc': 'ddc_sort asc',
            'ddc_sort desc': 'ddc_sort desc',
            # Ebook access
            'ebook_access': 'ebook_access desc',
            'ebook_access asc': 'ebook_access asc',
            'ebook_access desc': 'ebook_access desc',
            # Open Syllabus Project
            'osp_count': 'osp_count desc',
            'osp_count asc': 'osp_count asc',
            'osp_count desc': 'osp_count desc',
            # Key
            'key': 'key asc',
            'key asc': 'key asc',
            'key desc': 'key desc',
            # Random
            'random': 'random_1 asc',
            'random asc': 'random_1 asc',
            'random desc': 'random_1 desc',
            'random.hourly': lambda: f'random_{datetime.now():%Y%m%dT%H} asc',
            'random.daily': lambda: f'random_{datetime.now():%Y%m%d} asc',
        }
    )
    default_fetched_fields = frozenset(
        {
            'key',
            'author_name',
            'author_key',
            'title',
            'subtitle',
            'edition_count',
            'ebook_access',
            'ia',
            'has_fulltext',
            'first_publish_year',
            'cover_i',
            'cover_edition_key',
            'public_scan_b',
            'lending_edition_s',
            'lending_identifier_s',
            'language',
            'ia_collection_s',
            # FIXME: These should be fetched from book_providers, but can't cause circular
            # dep
            'id_project_gutenberg',
            'id_project_runeberg',
            'id_librivox',
            'id_standard_ebooks',
            'id_openstax',
            'id_cita_press',
            'id_wikisource',
        }
    )
    facet_rewrites = MappingProxyType(
        {
            ('public_scan', 'true'): 'ebook_access:public',
            ('public_scan', 'false'): '-ebook_access:public',
            ('print_disabled', 'true'): 'ebook_access:printdisabled',
            ('print_disabled', 'false'): '-ebook_access:printdisabled',
            (
                'has_fulltext',
                'true',
            ): lambda: f'ebook_access:[{get_fulltext_min()} TO *]',
            (
                'has_fulltext',
                'false',
            ): lambda: f'ebook_access:[* TO {get_fulltext_min()}]',
        }
    )

    def is_search_field(self, field: str):
        # New variable introduced to prevent rewriting the input.
        if field.startswith(('work.', 'edition.')):
            return self.is_search_field(field.partition(".")[2])
        return super().is_search_field(field) or field.startswith('id_')

    def transform_user_query(
        self, user_query: str, q_tree: luqum.tree.Item
    ) -> luqum.tree.Item:
        has_search_fields = False
        for node, parents in luqum_traverse(q_tree):
            if isinstance(node, luqum.tree.SearchField):
                has_search_fields = True
                if node.name.lower() in self.field_name_map:
                    node.name = self.field_name_map[node.name.lower()]
                if node.name == 'isbn':
                    isbn_transform(node)
                if node.name in ('lcc', 'lcc_sort'):
                    lcc_transform(node)
                if node.name in ('dcc', 'dcc_sort'):
                    ddc_transform(node)
                if node.name == 'ia_collection_s':
                    ia_collection_s_transform(node)

        if not has_search_fields:
            # If there are no search fields, maybe we want just an isbn?
            isbn = normalize_isbn(user_query)
            if isbn and len(isbn) in (10, 13):
                q_tree = luqum_parser(f'isbn:({isbn})')

        return q_tree

    def build_q_from_params(self, params: dict[str, Any]) -> str:
        q_list = []
        if 'author' in params:
            v = params['author'].strip()
            m = re_author_key.search(v)
            if m:
                q_list.append(f"author_key:({m.group(1)})")
            else:
                v = fully_escape_query(v)
                q_list.append(f"(author_name:({v}) OR author_alternative_name:({v}))")

        check_params = {
            'title',
            'publisher',
            'oclc',
            'lccn',
            'contributor',
            'subject',
            'place',
            'person',
            'time',
            'author_key',
        }
        # support web.input fields being either a list or string
        # when default values used
        q_list += [
            f'{k}:({fully_escape_query(val)})'
            for k in (check_params & set(params))
            for val in (params[k] if isinstance(params[k], list) else [params[k]])
        ]

        if params.get('isbn'):
            q_list.append(
                'isbn:(%s)' % (normalize_isbn(params['isbn']) or params['isbn'])
            )

        return ' AND '.join(q_list)

    def q_to_solr_params(  # noqa: PLR0915
        self,
        q: str,
        solr_fields: set[str],
        cur_solr_params: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        new_params: list[tuple[str, str]] = []

        # We need to parse the tree so that it gets transformed using the
        # special OL query parsing rules (different from default solr!)
        # See luqum_parser for details.
        work_q_tree = luqum_parser(q)

        # Removes the work prefix from fields; used as the callable argument for 'luqum_replace_field'
        def remove_work_prefix(field: str) -> str:
            return field.partition('.')[2] if field.startswith('work.') else field

        # Removes the indicator prefix from queries with the 'work field' before appending them to parameters.
        final_work_query = deepcopy(work_q_tree)
        luqum_replace_field(final_work_query, remove_work_prefix)
        try:
            luqum_remove_field(final_work_query, lambda f: f.startswith('edition.'))
        except EmptyTreeError:
            # If the whole tree is removed, we should just search for everything
            final_work_query = luqum_parser('*:*')

        new_params.append(('userWorkQuery', str(final_work_query)))

        # This full work query uses solr-specific syntax to add extra parameters
        # to the way the search is processed. We are using the edismax parser.
        # See https://solr.apache.org/guide/8_11/the-extended-dismax-query-parser.html
        # This is somewhat synonymous to setting defType=edismax in the
        # query, but much more flexible. We wouldn't be able to do our
        # complicated parent/child queries with defType!

        full_work_query = '({{!edismax q.op="AND" qf="{qf}" pf="{pf}" bf="{bf}" v={v}}})'.format(
            # qf: the fields to query un-prefixed parts of the query.
            # e.g. 'harry potter' becomes
            # 'text:(harry potter) OR alternative_title:(harry potter)^20 OR ...'
            qf='text alternative_title^10 author_name^10',
            # pf: phrase fields. This increases the score of documents that
            # match the query terms in close proximity to each other.
            pf='alternative_title^10 author_name^10',
            # bf (boost factor): boost results based on the value of this
            # field. I.e. results with more editions get boosted, upto a
            # max of 100, after which we don't see it as good signal of
            # quality.
            bf='min(100,edition_count) min(100,def(readinglog_count,0))',
            # v: the query to process with the edismax query parser. Note
            # we are using a solr variable here; this reads the url parameter
            # arbitrarily called userWorkQuery.
            v='$userWorkQuery',
        )
        ed_q = None
        full_ed_query = None
        editions_fq = []
        if has_solr_editions_enabled() and 'editions:[subquery]' in solr_fields:
            WORK_FIELD_TO_ED_FIELD: dict[str, str | Callable[[str], str]] = {
                # Internals
                'edition_key': 'key',
                'text': 'text',
                # Display data
                'title': 'title',
                'title_suggest': 'title_suggest',
                'subtitle': 'subtitle',
                'alternative_title': 'alternative_title',
                'alternative_subtitle': 'subtitle',
                'cover_i': 'cover_i',
                # Duplicate author fields
                # Disabled until the next full reindex
                # 'author_name': 'author_name',
                # 'author_key': 'author_key',
                # 'author_alternative_name': 'author_alternative_name',
                # 'author_facet': 'author_facet',
                # Misc useful data
                'format': 'format',
                'language': 'language',
                'publisher': 'publisher',
                'publisher_facet': 'publisher_facet',
                'publish_date': 'publish_date',
                'publish_year': 'publish_year',
                # Identifiers
                'isbn': 'isbn',
                # 'id_*': 'id_*', # Handled manually for now to match any id field
                'ebook_access': 'ebook_access',
                # IA
                'has_fulltext': 'has_fulltext',
                'ia': 'ia',
                'ia_collection': 'ia_collection',
                'ia_box_id': 'ia_box_id',
                'public_scan_b': 'public_scan_b',
            }

            def convert_work_field_to_edition_field(
                field: str,
            ) -> str | Callable[[str], str] | None:
                """
                Convert a SearchField name (eg 'title') to the correct fieldname
                for use in an edition query.

                If no conversion is possible, return None.
                """
                if field in WORK_FIELD_TO_ED_FIELD:
                    return WORK_FIELD_TO_ED_FIELD[field]
                elif field.startswith('id_'):
                    return field
                elif self.is_search_field(field) or field in self.facet_fields:
                    return None
                else:
                    raise ValueError(f'Unknown field: {field}')

            def convert_work_query_to_edition_query(work_query: str) -> str:
                """
                Convert a work query to an edition query. Mainly involves removing
                invalid fields, or renaming fields as necessary.
                """
                q_tree = luqum_parser(work_query)
                for node, parents in luqum_traverse(q_tree):
                    if isinstance(node, luqum.tree.SearchField) and node.name != '*':
                        if node.name.startswith('edition.'):
                            ed_field = node.name.partition('.')[2]
                        else:
                            ed_field = node.name

                        new_name = convert_work_field_to_edition_field(ed_field)
                        if new_name is None:
                            try:
                                luqum_remove_child(node, parents)
                            except EmptyTreeError:
                                # Deleted the whole tree! Nothing left
                                return ''
                        elif isinstance(new_name, str):
                            parent = parents[-1] if parents else None
                            # Prefixing with + makes the field mandatory
                            if isinstance(
                                parent,
                                (
                                    luqum.tree.Not,
                                    luqum.tree.Prohibit,
                                    luqum.tree.OrOperation,
                                ),
                            ):
                                node.name = new_name
                            else:
                                node.name = f'+{new_name}'
                            if new_name == 'key':
                                # need to convert eg 'edition_key:OL123M' to
                                # 'key:(/books/OL123M)'. Or
                                # key:(/books/OL123M OR /books/OL456M)
                                for n, n_parents in luqum_traverse(node.expr):
                                    if isinstance(
                                        n, (luqum.tree.Word, luqum.tree.Phrase)
                                    ):
                                        val = (
                                            n.value
                                            if isinstance(n, luqum.tree.Word)
                                            else n.value[1:-1]
                                        )
                                        val = val.removeprefix('/books/')
                                        n.value = f'"/books/{val}"'
                        elif callable(new_name):
                            # Replace this node with a new one
                            # First process the expr
                            new_expr = convert_work_query_to_edition_query(
                                str(node.expr)
                            )
                            new_node = luqum.tree.Group(
                                luqum_parser(new_name(new_expr))
                            )
                            if parents:
                                luqum_replace_child(parents[-1], node, new_node)
                            else:
                                return convert_work_query_to_edition_query(
                                    str(new_node)
                                )
                        else:
                            # Shouldn't happen
                            raise ValueError(f'Invalid new_name: {new_name}')
                return str(q_tree)

            # Move over all fq parameters that can be applied to editions.
            # These are generally used to handle facets.
            editions_fq = ['type:edition']
            for param_name, param_value in cur_solr_params:
                if param_name != 'fq' or param_value.startswith('type:'):
                    continue
                field_name, field_val = param_value.split(':', 1)
                if ed_field := convert_work_field_to_edition_field(field_name):
                    editions_fq.append(f'{ed_field}:{field_val}')
            for fq in editions_fq:
                new_params.append(('editions.fq', fq))

            user_lang = convert_iso_to_marc(web.ctx.lang or 'en') or 'eng'

            ed_q = convert_work_query_to_edition_query(str(work_q_tree))
            # Note that if there is no edition query (because no fields in
            # the user's work query apply), we use the special value *:* to
            # match everything, but still get boosting.
            new_params.append(('userEdQuery', ed_q or '*:*'))
            # Needs to also set this on the editions subquery; subqueries appear
            # to have their own scope for template parameters, so in order
            # for `userEdQuery` to be available to `editions.q`, we will
            # need to specify it twice.
            new_params.append(('editions.userEdQuery', ed_q or '*:*'))
            new_params.append(('editions.ol.label', 'EDITION_MATCH'))

            full_ed_query = '({{!edismax bq="{bq}" v={v} qf="{qf}"}})'.format(
                # See qf in work_query
                qf='text alternative_title^4 author_name^4',
                # Reading from the url parameter userEdQuery. This lets us avoid
                # having to try to escape the query in order to fit inside this
                # other query.
                v='$userEdQuery',
                # bq (boost query): Boost which edition is promoted to the top
                bq=' '.join(
                    (
                        f'language:{user_lang}^40',
                        'ebook_access:public^10',
                        'ebook_access:borrowable^8',
                        'ebook_access:printdisabled^2',
                        'cover_i:*^2',
                    )
                ),
            )

        if ed_q or len(editions_fq) > 1:
            # The elements in _this_ edition query should cause works not to
            # match _at all_ if matching editions are not found
            new_params.append(
                ('fullEdQuery', cast(str, full_ed_query) if ed_q else '*:*')
            )
            q = (
                f'+{full_work_query} '
                # This is using the special parent query syntax to, on top of
                # the user's `full_work_query`, also only find works which have
                # editions matching the edition query.
                # Also include edition-less works (i.e. edition_count:0)
                '+('
                '_query_:"{!parent which=type:work v=$fullEdQuery filters=$editions.fq}" '
                'OR edition_count:0'
                ')'
            )
            new_params.append(('q', q))
        else:
            new_params.append(('q', full_work_query))

        if full_ed_query:
            edition_fields = {
                f.split('.', 1)[1] for f in solr_fields if f.startswith('editions.')
            }
            if not edition_fields:
                edition_fields = solr_fields - {
                    # Default to same fields as for the work...
                    'editions:[subquery]',
                    # but exclude the author fields since they're primarily work data;
                    # they only exist on editions to improve search matches.
                    'author_name',
                    'author_key',
                    'author_alternative_name',
                    'author_facet',
                }
            # The elements in _this_ edition query will match but not affect
            # whether the work appears in search results
            new_params.append(
                (
                    'editions.q',
                    # Here we use the special terms parser to only filter the
                    # editions for a given, already matching work '_root_' node.
                    f'({{!terms f=_root_ v=$row.key}}) AND {full_ed_query}',
                )
            )
            new_params.append(('editions.rows', '1'))
            new_params.append(('editions.fl', ','.join(edition_fields)))
        return new_params

    def add_non_solr_fields(self, non_solr_fields: set[str], solr_result: dict) -> None:
        from openlibrary.plugins.upstream.models import Edition  # noqa: PLC0415

        # Augment with data from db
        edition_keys = [
            ed_doc['key']
            for doc in solr_result['response']['docs']
            for ed_doc in doc.get('editions', {}).get('docs', [])
        ]
        editions = cast(list[Edition], web.ctx.site.get_many(edition_keys))
        ed_key_to_record = {ed.key: ed for ed in editions if ed.key in edition_keys}

        from openlibrary.book_providers import get_book_provider  # noqa: PLC0415

        for doc in solr_result['response']['docs']:
            for ed_doc in doc.get('editions', {}).get('docs', []):
                # `ed` could be `None` if the record has been deleted and Solr not yet updated.
                if not (ed := ed_key_to_record.get(ed_doc['key'])):
                    continue

                for field in non_solr_fields:
                    val = getattr(ed, field)
                    if field == 'providers':
                        provider = get_book_provider(ed)
                        if not provider:
                            continue
                        ed_doc[field] = [
                            p.__dict__ for p in provider.get_acquisitions(ed)
                        ]
                    elif isinstance(val, infogami.infobase.client.Nothing):
                        continue
                    elif field == 'description':
                        ed_doc[field] = val if isinstance(val, str) else val.value


def lcc_transform(sf: luqum.tree.SearchField):
    # e.g. lcc:[NC1 TO NC1000] to lcc:[NC-0001.00000000 TO NC-1000.00000000]
    # for proper range search
    val = sf.children[0]
    if isinstance(val, luqum.tree.Range):
        normed_range = normalize_lcc_range(val.low.value, val.high.value)
        if normed_range:
            val.low.value, val.high.value = normed_range
    elif isinstance(val, luqum.tree.Word):
        if '*' in val.value and not val.value.startswith('*'):
            # Marshals human repr into solr repr
            # lcc:A720* should become A--0720*
            parts = val.value.split('*', 1)
            lcc_prefix = normalize_lcc_prefix(parts[0])
            val.value = (lcc_prefix or parts[0]) + '*' + parts[1]
        else:
            normed = short_lcc_to_sortable_lcc(val.value.strip('"'))
            if normed:
                val.value = normed
    elif isinstance(val, luqum.tree.Phrase):
        normed = short_lcc_to_sortable_lcc(val.value.strip('"'))
        if normed:
            val.value = f'"{normed}"'
    elif (
        isinstance(val, luqum.tree.Group)
        and isinstance(val.expr, luqum.tree.UnknownOperation)
        and all(isinstance(c, luqum.tree.Word) for c in val.expr.children)
    ):
        # treat it as a string
        normed = short_lcc_to_sortable_lcc(str(val.expr))
        if normed:
            if ' ' in normed:
                sf.expr = luqum.tree.Phrase(f'"{normed}"')
            else:
                sf.expr = luqum.tree.Word(f'{normed}*')
    else:
        logger.warning(f"Unexpected lcc SearchField value type: {type(val)}")


def ddc_transform(sf: luqum.tree.SearchField):
    val = sf.children[0]
    if isinstance(val, luqum.tree.Range):
        normed_range = normalize_ddc_range(val.low.value, val.high.value)
        val.low.value = normed_range[0] or val.low
        val.high.value = normed_range[1] or val.high
    elif isinstance(val, luqum.tree.Word) and val.value.endswith('*'):
        return normalize_ddc_prefix(val.value[:-1]) + '*'
    elif isinstance(val, (luqum.tree.Word, luqum.tree.Phrase)):
        if normed := normalize_ddc(val.value.strip('"')):
            val.value = normed
    else:
        logger.warning(f"Unexpected ddc SearchField value type: {type(val)}")


def isbn_transform(sf: luqum.tree.SearchField):
    field_val = sf.children[0]
    if isinstance(field_val, luqum.tree.Word) and '*' not in field_val.value:
        isbn = normalize_isbn(field_val.value)
        if isbn:
            field_val.value = isbn
    else:
        logger.warning(f"Unexpected isbn SearchField value type: {type(field_val)}")


def ia_collection_s_transform(sf: luqum.tree.SearchField):
    """
    Because this field is not a multi-valued field in solr, but a simple ;-separate
    string, we have to do searches like this for now.
    """
    val = sf.children[0]
    if isinstance(val, luqum.tree.Word):
        if val.value.startswith('*'):
            val.value = '*' + val.value
        if val.value.endswith('*'):
            val.value += '*'
    else:
        logger.warning(
            f"Unexpected ia_collection_s SearchField value type: {type(val)}"
        )


def has_solr_editions_enabled():
    if 'pytest' in sys.modules:
        return True

    def read_query_string():
        return web.input(editions=None).get('editions')

    def read_cookie():
        if "SOLR_EDITIONS" in web.ctx.env.get("HTTP_COOKIE", ""):
            return web.cookies().get('SOLR_EDITIONS')

    if (qs_value := read_query_string()) is not None:
        return qs_value == 'true'

    if (cookie_value := read_cookie()) is not None:
        return cookie_value == 'true'

    return True


def get_fulltext_min():
    is_printdisabled = web.cookies().get('pd', False)
    return 'printdisabled' if is_printdisabled else 'borrowable'
