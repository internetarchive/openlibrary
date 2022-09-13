from typing import Callable
from luqum.parser import parser
from luqum.tree import Item, SearchField, BaseOperation, Group, Word
import re


class EmptyTreeError(Exception):
    pass


def luqum_remove_child(child: Item, parents: list[Item]):
    parent = parents[-1] if parents else None
    if parent is None:
        raise EmptyTreeError()
    elif isinstance(parent, BaseOperation) or isinstance(parent, Group):
        new_children = tuple(c for c in parent.children if c != child)
        if not new_children:
            luqum_remove_child(parent, parents[:-1])
        else:
            parent.children = new_children
    else:
        raise ValueError("Not supported for generic class Item")


def luqum_traverse(item: Item, parents: list[Item] = None):
    parents = parents or []
    yield item, parents
    new_parents = [*parents, item]
    for child in item.children:
        yield from luqum_traverse(child, new_parents)


def luqum_find_and_replace(query: str, field_pattern: str, replacement: str) -> str:
    """
    >>> luqum_find_and_replace('hello AND has_fulltext:true', 'has_fulltext:true', 'ebook_access:[borrowable TO *]')
    hello AND ebook_access:[borrowable TO *]
    >>> luqum_find_and_replace('hello AND has_fulltext: true', 'has_fulltext:true', 'ebook_access:[borrowable TO *]')
    hello AND ebook_access:[borrowable TO *]
    >>> luqum_find_and_replace('hello AND (has_fulltext:true)', 'has_fulltext:true', 'ebook_access:[borrowable TO *]')
    return hello AND (ebook_access:[borrowable TO *])
    """
    tree = parser.parse(query)
    field_tree = parser.parse(field_pattern)
    assert isinstance(field_tree, SearchField)
    for item, parents in luqum_traverse(tree):
        if item == field_tree:
            replacement_tree = parser.parse(replacement)
            replacement_tree.head = item.head
            replacement_tree.tail = item.tail
            print(item, parents)
            parents[-1].children = tuple(
                child if child is item else replacement_tree
                for child in parents[-1].children
            )
    return str(tree)


def escape_unknown_fields(query: str, is_valid_field: Callable[[str], bool]) -> str:
    """
    >>> escape_unknown_fields('title:foo', lambda field: False)
    'title\\:foo'
    >>> escape_unknown_fields('title:foo bar   blah:bar baz:boo', lambda field: False)
    'title\\:foo bar   blah\\:bar baz\\:boo'
    >>> escape_unknown_fields('title:foo bar', {'title'}.__contains__)
    'title:foo bar'
    >>> escape_unknown_fields('title:foo bar baz:boo', {'title'}.__contains__)
    'title:foo bar baz\\:boo'
    >>> escape_unknown_fields('hi', {'title'}.__contains__)
    'hi'
    """
    # Treat as just normal text with the colon escaped
    tree = parser.parse(query)
    escaped_query = query
    offset = 0
    for sf, _ in luqum_traverse(tree):
        if isinstance(sf, SearchField) and not is_valid_field(sf.name):
            field = sf.name + r'\:'
            if hasattr(sf, 'head'):
                field = sf.head + field
            escaped_query = (
                escaped_query[: sf.pos + offset]
                + field
                + escaped_query[sf.pos + len(field) - 1 + offset :]
            )
            offset += 1
    return escaped_query


def fully_escape_query(query: str) -> str:
    """
    >>> fully_escape_query('title:foo')
    'title\\:foo'
    >>> fully_escape_query('title:foo bar')
    'title\\:foo bar'
    >>> fully_escape_query('title:foo (bar baz:boo)')
    'title\\:foo \\(bar baz\\:boo\\)'
    >>> fully_escape_query('x:[A TO Z}')
    'x\\:\\[A TO Z\\}'
    """
    escaped = query
    # Escape special characters
    escaped = re.sub(r'[\[\]\(\)\{\}:]', lambda _1: f'\\{_1.group(0)}', escaped)
    # Remove boolean operators by making them lowercase
    escaped = re.sub(r'AND|OR|NOT', lambda _1: _1.lower(), escaped)
    return escaped


def luqum_parser(query: str) -> Item:
    tree = parser.parse(query)

    for node, parents in luqum_traverse(tree):
        # if the first child is a search field and words, we bundle
        # the words into the search field value
        # eg. (title:foo) (bar) (baz) -> title:(foo bar baz)
        if isinstance(node, BaseOperation) and isinstance(
            node.children[0], SearchField
        ):
            sf = node.children[0]
            others = node.children[1:]
            if isinstance(sf.expr, Word) and all(isinstance(n, Word) for n in others):
                # Replace BaseOperation with SearchField
                node.children = others
                sf.expr = Group(type(node)(sf.expr, *others))
                parent = parents[-1] if parents else None
                if not parent:
                    tree = sf
                else:
                    parent.children = tuple(
                        sf if child is node else child for child in parent.children
                    )

    return tree
