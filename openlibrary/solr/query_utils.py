import re
from collections.abc import Callable
from typing import Literal

from luqum.parser import parser
from luqum.tree import BaseOperation, Group, Item, SearchField, Unary, Word


class EmptyTreeError(Exception):
    pass


def luqum_remove_child(child: Item, parents: list[Item]):
    """
    Removes a child from a luqum parse tree. If the tree
    ends up being empty, errors.

    :param child: Node to remove
    :param parents: Path of parent nodes leading from the root of the tree
    """
    parent = parents[-1] if parents else None
    if parent is None:
        # We cannot remove the element if it is the root of the tree
        raise EmptyTreeError
    elif isinstance(parent, (BaseOperation, Group, Unary)):
        new_children = tuple(c for c in parent.children if c != child)
        if not new_children:
            # If we have deleted all the children, we need to delete the parent
            # as well. And potentially recurse up the tree.
            luqum_remove_child(parent, parents[:-1])
        else:
            parent.children = new_children
    else:
        raise NotImplementedError(
            f"Not implemented for Item subclass: {parent.__class__.__name__}"
        )


def luqum_replace_child(parent: Item, old_child: Item, new_child: Item):
    """
    Replaces a child in a luqum parse tree.
    """
    if isinstance(parent, (BaseOperation, Group, Unary)):
        new_children = tuple(
            new_child if c == old_child else c for c in parent.children
        )
        parent.children = new_children
    else:
        raise ValueError("Not supported for generic class Item")


def luqum_traverse(item: Item, _parents: list[Item] | None = None):
    """
    Traverses every node in the parse tree in depth-first order.

    Does not make any guarantees about what will happen if you
    modify the tree while traversing it 😅 But we do it anyways.

    :param item: Node to traverse
    :param _parents: Internal parameter for tracking parents
    """
    parents = _parents or []
    yield item, parents
    new_parents = [*parents, item]
    for child in item.children:
        yield from luqum_traverse(child, new_parents)


def escape_unknown_fields(
    query: str,
    is_valid_field: Callable[[str], bool],
    lower=True,
) -> str:
    """
    Escapes the colon of any search field that is not deemed valid by the
    predicate function `is_valid_field`.

    :param query: Query to escape
    :param is_valid_field: Predicate function that determines if a field is valid
    :param lower: If true, the field will be lowercased before being checked

    >>> escape_unknown_fields('title:foo', lambda field: False)
    'title\\\\:foo'
    >>> escape_unknown_fields('title:foo bar   blah:bar baz:boo', lambda field: False)
    'title\\\\:foo bar   blah\\\\:bar baz\\\\:boo'
    >>> escape_unknown_fields('title:foo bar', {'title'}.__contains__)
    'title:foo bar'
    >>> escape_unknown_fields('title:foo bar baz:boo', {'title'}.__contains__)
    'title:foo bar baz\\\\:boo'
    >>> escape_unknown_fields('title:foo bar baz:boo', {'TITLE'}.__contains__, lower=False)
    'title\\\\:foo bar baz\\\\:boo'
    >>> escape_unknown_fields('hi', {'title'}.__contains__)
    'hi'
    >>> escape_unknown_fields('(title:foo) OR (blah:bah)', {'title'}.__contains__)
    '(title:foo) OR (blah\\\\:bah)'
    """
    tree = parser.parse(query)
    # Note we use the string of the tree, because it strips spaces
    # like: "title : foo" -> "title:foo"
    escaped_query = str(tree)
    offset = 0
    for sf, _ in luqum_traverse(tree):
        if isinstance(sf, SearchField) and not is_valid_field(
            sf.name.lower() if lower else sf.name
        ):
            field = sf.name + r'\:'
            if hasattr(sf, 'head'):
                # head and tail are used for whitespace between fields;
                # copy it along to the write space to avoid things smashing
                # together
                field = sf.head + field

            # We will be moving left to right, so we need to adjust the offset
            # to account for the characters we have already replaced
            escaped_query = (
                escaped_query[: sf.pos + offset]
                + field
                + escaped_query[sf.pos + len(field) - 1 + offset :]
            )
            offset += 1
    return escaped_query


def fully_escape_query(query: str) -> str:
    """
    Try to convert a query to basically a plain lucene string.

    >>> fully_escape_query('title:foo')
    'title\\\\:foo'
    >>> fully_escape_query('title:foo bar')
    'title\\\\:foo bar'
    >>> fully_escape_query('title:foo (bar baz:boo)')
    'title\\\\:foo \\\\(bar baz\\\\:boo\\\\)'
    >>> fully_escape_query('x:[A TO Z}')
    'x\\\\:\\\\[A TO Z\\\\}'
    >>> fully_escape_query('foo AND bar')
    'foo and bar'
    >>> fully_escape_query("foo's bar")
    "foo\\\\'s bar"
    """
    escaped = query
    # Escape special characters
    escaped = re.sub(r'[\[\]\(\)\{\}:"\-+?~^/\\,\']', r'\\\g<0>', escaped)
    # Remove boolean operators by making them lowercase
    escaped = re.sub(r'AND|OR|NOT', lambda _1: _1.group(0).lower(), escaped)
    return escaped


def luqum_parser(query: str) -> Item:
    """
    Parses a lucene-like query, with the special binding rules of Open Library.

    In our queries, unlike native solr/lucene, field names are greedy, and
    affect the rest of the query until another field is hit.

    Here are some examples. The first query is the native solr/lucene
    parsing. The second is the parsing we want.

    Query : title:foo bar
    Lucene: (title:foo) bar
    OL    : (title:foo bar)

    Query : title:foo OR bar AND author:blah
    Lucene: (title:foo) OR (bar) AND (author:blah)
    OL    : (title:foo OR bar) AND (author:blah)

    This requires an annoying amount of manipulation of the default
    Luqum parser, unfortunately.

    Also, OL queries allow spaces after fields.
    """
    tree = parser.parse(query)

    def find_next_word(item: Item) -> tuple[Word, BaseOperation | None] | None:
        if isinstance(item, Word):
            return item, None
        elif isinstance(item, BaseOperation) and isinstance(item.children[0], Word):
            return item.children[0], item
        else:
            return None

    for node, parents in luqum_traverse(tree):
        if isinstance(node, BaseOperation):
            # if any of the children are SearchField followed by one or more words,
            # we bundle them together
            last_sf: SearchField = None
            to_rem = []
            for child in node.children:
                if isinstance(child, SearchField) and isinstance(child.expr, Word):
                    last_sf = child
                elif last_sf and (next_word := find_next_word(child)):
                    word, parent_op = next_word
                    # Add it over
                    if not isinstance(last_sf.expr, Group):
                        last_sf.expr = Group(type(node)(last_sf.expr, word))
                        last_sf.expr.tail = word.tail
                        word.tail = ''
                    else:
                        last_sf.expr.expr.children[-1].tail = last_sf.expr.tail
                        last_sf.expr.expr.children += (word,)
                        last_sf.expr.tail = word.tail
                        word.tail = ''
                    if parent_op:
                        # A query like: 'title:foo blah OR author:bar
                        # Lucene parses as: (title:foo) ? (blah OR author:bar)
                        # We want         : (title:foo ? blah) OR (author:bar)
                        node.op = parent_op.op
                        node.children += (*parent_op.children[1:],)
                    to_rem.append(child)
                else:
                    last_sf = None
            if len(to_rem) == len(node.children) - 1:
                # We only have the searchfield left!
                if parents:
                    # Move the head to the next element
                    last_sf.head = node.head
                    parents[-1].children = tuple(
                        child if child is not node else last_sf
                        for child in parents[-1].children
                    )
                else:
                    tree = last_sf
                    break
            else:
                node.children = tuple(
                    child for child in node.children if child not in to_rem
                )

    # Remove spaces before field names
    for node, parents in luqum_traverse(tree):
        if isinstance(node, SearchField):
            node.expr.head = ''

    return tree


def query_dict_to_str(
    escaped: dict | None = None,
    unescaped: dict | None = None,
    op: Literal['AND', 'OR', ''] = '',
    phrase: bool = False,
) -> str:
    """
    Converts a query dict to a search query.

    >>> query_dict_to_str({'title': 'foo'})
    'title:(foo)'
    >>> query_dict_to_str({'title': 'foo bar', 'author': 'bar'})
    'title:(foo bar)  author:(bar)'
    >>> query_dict_to_str({'title': 'foo bar', 'author': 'bar'}, op='OR')
    'title:(foo bar) OR author:(bar)'
    >>> query_dict_to_str({'title': 'foo ? to escape'})
    'title:(foo \\\\? to escape)'
    >>> query_dict_to_str({'title': 'YES AND'})
    'title:(YES and)'
    >>> query_dict_to_str({'publisher_facet': 'Running Press'}, phrase=True)
    'publisher_facet:"Running Press"'
    """
    result = ''
    if escaped:
        result += f' {op} '.join(
            (
                f'{k}:"{fully_escape_query(v)}"'
                if phrase
                else f'{k}:({fully_escape_query(v)})'
            )
            for k, v in escaped.items()
        )
    if unescaped:
        if result:
            result += f' {op} '
        result += f' {op} '.join(f'{k}:{v}' for k, v in unescaped.items())
    return result


def luqum_replace_field(query: Item, replacer: Callable[[str], str]) -> None:
    """
    In-place replaces portions of a field, as indicated by the replacement function.

    :param query: Passed in the form of a luqum tree
    :param replacer: function called on each query.
    """
    for sf, _ in luqum_traverse(query):
        if isinstance(sf, SearchField):
            sf.name = replacer(sf.name)


def luqum_remove_field(query: Item, predicate: Callable[[str], bool]) -> None:
    """
    In-place removes fields from a query, as indicated by the predicate function.

    :param query: Passed in the form of a luqum tree
    :param predicate: function called on each query.
    """
    for sf, parents in luqum_traverse(query):
        if isinstance(sf, SearchField) and predicate(sf.name):
            luqum_remove_child(sf, parents)
