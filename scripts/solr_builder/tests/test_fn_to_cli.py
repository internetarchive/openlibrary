from argparse import BooleanOptionalAction
import typing
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI


class TestFnToCLI:
    def test_full_flow(self):
        def fn(works: list[str], solr_url: str | None = None):
            """
            Do some magic!
            :param works: These are works
            :param solr_url: This is solr url
            """

        cli = FnToCLI(fn)
        assert cli.parser.description.strip() == 'Do some magic!'
        assert '--solr-url' in cli.parser.format_usage()

    def test_parse_docs(self):
        docs = """
        :param a: A
        :param b: B
        :param c: C
        """
        assert FnToCLI.parse_docs(docs) == {'a': 'A', 'b': 'B', 'c': 'C'}

        docs = """
        Some function description

        :param a: A asdfas
        """
        assert FnToCLI.parse_docs(docs) == {'a': 'A asdfas'}

    def test_type_to_argparse(self):
        assert FnToCLI.type_to_argparse(int) == {'type': int}
        assert FnToCLI.type_to_argparse(typing.Optional[int]) == {  # noqa: UP007
            'type': int
        }
        assert FnToCLI.type_to_argparse(bool) == {
            'type': bool,
            'action': BooleanOptionalAction,
        }
        assert FnToCLI.type_to_argparse(typing.Literal['a', 'b']) == {
            'choices': ('a', 'b'),
        }

    def test_is_optional(self):
        assert FnToCLI.is_optional(typing.Optional[int])  # noqa: UP007
        assert not FnToCLI.is_optional(int)
