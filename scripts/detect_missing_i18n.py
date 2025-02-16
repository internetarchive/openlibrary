#!/usr/bin/env python
"""Utility script to list html files which might be missing i18n strings."""
import glob
import re
import sys
from enum import Enum
from pathlib import Path

import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH

from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

# This is a list of files that are intentionally excluded from the i18n process
EXCLUDE_LIST = {
    # This is being left untranslated because it is rarely used
    "openlibrary/templates/admin/sync.html",
    # These are excluded because they require more info to fix
    "openlibrary/templates/books/edit.html",
    "openlibrary/templates/history/sources.html",
    # This can't be fixed because it's not in the i18n directories
    "openlibrary/admin/templates/admin/index.html",
    # These can't be fixed since they're rendered as static html
    "static/offline.html",
    "static/status-500.html",
    # Uses jsdef and the current stance is no i18n in JS.
    "openlibrary/templates/jsdef/LazyAuthorPreview.html",
}

default_directories = ('openlibrary/templates/', 'openlibrary/macros/')


class Errtype(str, Enum):
    WARN = "\033[93mWARN\033[0m"
    ERR = "\033[91mERRO\033[0m"
    SKIP = "\033[94mSKIP\033[0m"


skip_directive = r"# detect-missing-i18n-skip-line"
regex_skip_inline = r"\$" + skip_directive
regex_skip_previous_line = r"^\s*\$?" + skip_directive

# Assumptions:
# - Not concerned about HTML elements whose untranslated contents follow a newline, i.e. <p>\nsome untranslated text\n<p>.
# - Don't want to flag false positives where > characters are not part of tags, so this regex looks for a complete opening tag.
# TODO: replace the huge punctuation array with \p{L} - only supported in pip regex and not re
punctuation = r"[\(\)\{\}\[\]\/\\:;\-_\s+=*^%#\.•·\?♥|≡0-9,!xX✓×@\"'†★]"  # noqa: RUF001
htmlents = r"&[a-z0-9]+;"
variables = r"\$:?[^\s]+|\$[^\s\(]+[\(][^\)]+[\)]|\$[^\s\[]+[\[][^\]]+[\]]|\$[\{][^\}]+[\}]|%\(?[a-z_]+\)?|\{\{[^\}]+\}\}"
urls_domains = r"https?:\/\/[^\s]+|[a-z\-]+\.[A-Za-z]{2}[a-z]?"

opening_tag_open = r"<(?!code|link|!--)[a-z][^>]*?"
opening_tag_end = r"[^\/\-\s]>"
opening_tag_syntax = opening_tag_open + opening_tag_end
ignore_after_opening_tag = (
    r"(?![<\r\n]|$|\\\$\$|\$:?_?\(|\$:?ungettext\(|(?:"
    + punctuation
    + r"|"
    + htmlents
    + r"|"
    + variables
    + r"|"
    + urls_domains
    + r")+(?:[\r\n<]|$))"
)
warn_after_opening_tag = r"\$\(['\"]"

i18n_element_missing_regex = opening_tag_syntax + ignore_after_opening_tag
i18n_element_warn_regex = opening_tag_syntax + r"\$\(['\"]"

attr_syntax = r"(title|placeholder|alt)="
ignore_double_quote = (
    r"\"(?!\$:?_?\(|\$:?ungettext\(|\\\$\$|(?:"
    + punctuation
    + r"|"
    + variables
    + r"|"
    + urls_domains
    + r")*\")"
)
ignore_single_quote = (
    r"\'(?!\$:?_?\(|\$:?ungettext\(|\\\$\$|(?:"
    + punctuation
    + r"|"
    + variables
    + r"|"
    + urls_domains
    + r")*\')"
)

i18n_attr_missing_regex = (
    opening_tag_open
    + attr_syntax
    + r"(?:"
    + ignore_double_quote
    + r"|"
    + ignore_single_quote
    + r")[^>]*?>"
)
i18n_attr_warn_regex = opening_tag_open + attr_syntax + r"\"\$\(\'"


def terminal_underline(text: str) -> str:
    return f"\033[4m{text}\033[0m"


def print_analysis(
    errtype: str,
    filename: Path,
    details: str,
    spacing_base: int,
    line_number: int = 0,
    line_position: int = 0,
):
    linestr = (
        f":{line_number}:{line_position}"
        if line_number > 0 and line_position > 0
        else ""
    )
    filestring = f'{filename}{linestr}'
    print(
        '\t'.join(
            [errtype, terminal_underline(filestring).ljust(spacing_base + 12), details]
        )
    )


def main(files: list[Path], skip_excluded: bool = True):
    """
    :param files: The html files to check for missing i18n. Leave empty to run over all html files.
    :param skip_excluded: If --no-skip-excluded is supplied as an arg, files in the EXCLUDE_LIST slice will be processed
    """

    if not files:
        files = [
            Path(file_path)
            for ddir in default_directories
            for file_path in glob.glob(f'{ddir}**/*.html', recursive=True)
        ]

    # Figure out how much padding to put between the filename and the error output
    longest_filename_length = max(len(str(f)) for f in files)
    spacing_base = longest_filename_length + len(':XXX:XXX')

    errcount: int = 0
    warnings: int = 0

    for file in files:
        contents = file.read_text()
        lines = contents.splitlines()

        if skip_excluded and str(file) in EXCLUDE_LIST:
            print_analysis(Errtype.SKIP, file, "", spacing_base)
            continue

        for line_number, line in enumerate(lines, start=1):

            includes_error_element = re.search(i18n_element_missing_regex, line)
            includes_warn_element = re.search(i18n_element_warn_regex, line)
            includes_error_attribute = re.search(i18n_attr_missing_regex, line)
            includes_warn_attribute = re.search(i18n_attr_warn_regex, line)

            char_index = -1
            # Element with untranslated elements
            if includes_error_element:
                char_index = includes_error_element.start()
                errtype = Errtype.ERR
            # Element with bypassed elements
            elif includes_warn_element:
                char_index = includes_warn_element.start()
                errtype = Errtype.WARN
            # Element with untranslated attributes
            elif includes_error_attribute:
                char_index = includes_error_attribute.start()
                errtype = Errtype.ERR
            # Element with bypassed attributes
            elif includes_warn_attribute:
                char_index = includes_warn_attribute.start()
                errtype = Errtype.WARN

            # Don't proceed if the line doesn't match any of the four cases.
            else:
                continue

            preceding_text = line[:char_index]
            regex_match = line[char_index:]

            # Don't proceed if the line is likely commented out or part of a $: function.
            if (
                "<!--" in preceding_text
                or "$:" in preceding_text
                or "$ " in preceding_text
            ):
                continue

            # Don't proceed if skip directive is included inline.
            if re.search(regex_skip_inline, regex_match):
                continue

            # Don't proceed if the previous line is a skip directive.
            if re.match(regex_skip_previous_line, lines[line_number - 2]):
                continue

            print_position = char_index + 1
            print_analysis(
                errtype,
                file,
                regex_match,
                spacing_base,
                line_number,
                print_position,
            )

            if errtype == Errtype.WARN:
                warnings += 1
            elif errtype == Errtype.ERR:
                errcount += 1

    print(
        f"{len(files)} file{'s' if len(files) != 1 else ''} scanned. {errcount} error{'s' if errcount != 1 else ''} found."
    )
    if errcount > 0 or warnings > 0:
        print(
            "Learn how to fix these errors by reading our i18n documentation: https://github.com/internetarchive/openlibrary/wiki/Internationalization#internationalization-i18n-developers-guide"
        )

    if errcount > 0:
        sys.exit(1)


if __name__ == "__main__":
    FnToCLI(main).run()
