#!/usr/bin/env python
"""Utility script to list html files which might be missing i18n strings."""
import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH
import re
import sys
from pathlib import Path
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

valid_directories = ['openlibrary/templates/', 'openlibrary/macros/']
warn_prefix = "\033[93mWARN\033[0m"
err_prefix = "\033[91mERRO\033[0m"

# Assumptions:
# - Not concerned about HTML elements whose untranslated contents follow a newline, i.e. <p>\nsome untranslated text\n<p>.
# - Don't want to flag false positives where > characters are not part of tags, so this regex looks for a complete opening tag.
# TODO: replace the huge punctuation array with \p{L} - only supported in pip regex and not re
punctuation = r"[\(\)\{\}\[\]\/\\:;\-_\s+=*^%#\.•·\?♥|≡0-9,!xX✓×@\"'†★]"
htmlents = r"&[a-z0-9]+;"
variables = r"\$:?[^\s]+|%\(?[a-z_]+\)?|\{\{[^\}]+\}\}"
urls_domains = r"https?:\/\/[^\s]+|[a-z\-]+\.[a-z]{2}[a-z]?"

opening_tag_open = r"<(?!code|link|!--)[a-z][^>]*?"
opening_tag_end = r"[^\/\-]>"
opening_tag_syntax = opening_tag_open + opening_tag_end
ignore_after_opening_tag = (
    r"(?![<\r\n]|$|\\\$\$|\$:?_?\(|(?:"
    + punctuation
    + r"|"
    + htmlents
    + r"|"
    + variables
    + r"|"
    + urls_domains
    + r")+(?:[\r\n<]|$))"
)

substring_elements = [
    "a",
    "b",
    "abbr",
    "bdi",
    "bdo",
    "br",
    "cite",
    "del",
    "dfn",
    "em",
    "i",
    "ins",
    "kbd",
    "mark",
    "meter",
    "q",
    "rp",
    "rt",
    "s",
    "samp",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "time",
    "u",
    "var",
    "wbr",
]
i18n_substring_regex = r"^<(?:" + re.escape("|".join(substring_elements)) + r")\W"

i18n_element_missing_regex = opening_tag_syntax + ignore_after_opening_tag
i18n_element_warn_regex = opening_tag_syntax + r"\$\("

attr_syntax = r"(title|placeholder|alt)="
ignore_double_quote = (
    r"\"(?!\$:?_?\(|\\\$\$|(?:"
    + punctuation
    + r"|"
    + variables
    + r"|"
    + urls_domains
    + r")*\")"
)
ignore_single_quote = (
    r"\'(?!\$:?_?\(|\\\$\$|(?:"
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
i18n_attr_warn_regex = opening_tag_open + attr_syntax + r"['\"]\$\("


def main(files: list[Path]):
    """
    :param files: The html files to check for missing i18n
    """

    # Don't validate i18n unless the file is in one of the valid_directories.
    valid_files = [
        file
        for file in files
        if len([valid for valid in valid_directories if str(file).startswith(valid)])
        > 0
    ]
    if len(valid_files) == 0:
        sys.exit(0)

    # Figure out how much padding to put between the filename and the error output
    longest_filename_length = 0
    longest_line_count = 0
    longest_line = 0
    for f in valid_files:
        if len(str(f)) > longest_filename_length:
            longest_filename_length = len(str(f))
        contents = f.read_text()
        lines = contents.splitlines()
        if len(lines) + 1 > longest_line_count:
            longest_line_count = len(lines) + 1
        for line in lines:
            if len(line) + 1 > longest_line:
                longest_line = len(line) + 1
    spacing_base = longest_filename_length + len(
        f':{longest_line_count}:{longest_line}'
    )

    errcount: int = 0
    warnings: int = 0

    for file in valid_files:

        contents = file.read_text()
        lines = contents.splitlines()

        for line_index, line in enumerate(lines):
            line_number = line_index + 1

            includes_error_element = re.search(i18n_element_missing_regex, line)
            includes_warn_element = re.search(i18n_element_warn_regex, line)
            includes_error_attribute = re.search(i18n_attr_missing_regex, line)
            includes_warn_attribute = re.search(i18n_attr_warn_regex, line)

            # Check first if the line contains any instances at all of the offending regexes.
            if not (
                includes_error_element
                or includes_warn_element
                or includes_error_attribute
                or includes_warn_attribute
            ):
                continue

            # Find the exact index within the line where the regex is matched.
            for char_index in range(len(line)):
                position = char_index + 1
                search_chunk = line[char_index:]

                if "<!--" in line[:char_index]:
                    break

                untranslated = False

                # Element with untranslated elements that isn't encased in a translation function
                if re.match(i18n_element_missing_regex, search_chunk) and not (
                    re.match(i18n_substring_regex, search_chunk)
                    and "$:" in line[:char_index]
                ):
                    errtype = err_prefix
                    errcount += 1
                    untranslated = True

                # Element with bypassed elements that isn't encased in a translation function
                elif re.match(i18n_element_warn_regex, search_chunk) and not (
                    re.match(i18n_substring_regex, search_chunk)
                    and "$:" in line[:char_index]
                ):
                    errtype = warn_prefix
                    warnings += 1
                    untranslated = True

                # Element with untranslated attributes
                elif re.match(i18n_attr_missing_regex, search_chunk):
                    errtype = err_prefix
                    errcount += 1
                    untranslated = True

                # Element with bypassed attributes
                elif re.match(i18n_attr_warn_regex, search_chunk):
                    errtype = warn_prefix
                    warnings += 1
                    untranslated = True

                if untranslated:
                    filestring = f'{file}:{line_number}:{position}'
                    padding = spacing_base - len(filestring) + 4
                    print(
                        f"{errtype} \033[4m{filestring}\033[0m{' ' * padding}{search_chunk}"
                    )

    print(
        f"{len(valid_files)} file{'s' if len(valid_files) != 1 else ''} scanned. {errcount} error{'s' if errcount != 1 else ''} found."
    )
    if errcount > 0 or warnings > 0:
        print(
            "Learn how to fix these errors by reading our i18n documentation: https://github.com/internetarchive/openlibrary/wiki/Internationalization#internationalization-i18n-developers-guide"
        )

    if errcount > 0:
        sys.exit(1)


if __name__ == "__main__":
    FnToCLI(main).run()
