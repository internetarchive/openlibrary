#!/usr/bin/env python
"""Utility script to list html files which might be missing i18n strings."""
import _init_path  # noqa: F401  Imported for its side effect of setting PYTHONPATH
import re
import sys
from pathlib import Path
from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI

valid_directories = ['openlibrary/templates/', 'openlibrary/macros/']

# Assumptions:
# - Not concerned about HTML elements whose untranslated contents follow a newline, i.e. <p>\nsome untranslated text\n<p>.
# - Don't want to flag false positives where > characters are not part of tags, so this regex looks for a complete opening tag.
# TODO: replace the huge punctuation array with \p{L} - only supported in pip regex and not re
punct = r"\(\)\{\}\[\]\/\\:;\-_\s+=*^%#\.•·\?♥|≡0-9,!x✓×"
allowed_after_opening_tag = (
    r"(?!<|$|\$[^\(]|\\\$\$|'\s?\+\s?_\(|%|\{\{|(?:["
    + punct
    + r"]|&[a-z0-9]+;)+(?:[\r\n<]|$|\$:?_))"
)
i18n_element_missing_regex = (
    r"<(?!code|link|[/\s])[^>]+?[^\/\-]>" + allowed_after_opening_tag
)
i18n_element_warn_regex = r"^<(?!code|link|[/\s])[^>]+>\$\("
i18n_substring_regex = r"^<(?:a|b|abbr|bdi|bdo|br|cite|del|dfn|em|i|ins|kbd|mark|meter|q|rp|rt|s|samp|small|span|strong|sub|sup|time|u|var|wbr)\W"
i18n_attr_missing_regex = (
    r"<[^/\s][^>]*?(title|placeholder|alt)=(?:\"(?!\"|$|\$[^\(]|%|["
    + punct
    + r"]+\")|'(?!'|$|\$[^\(]|%|["
    + punct
    + r"]+'))[^>]*?>"
)
i18n_attr_warn_regex = r"<[^/\s][^>]*?(title|placeholder|alt)=['\"]\$\([^>]*?>"


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

    errcount: int = 0
    warnings: int = 0

    for file in valid_files:

        contents = file.read_text()
        lines = contents.splitlines()

        for line_index, line in enumerate(lines):
            line_number = line_index + 1
            # Check first if the line contains any instances at all of the offending regexes.
            if not re.search(i18n_attr_missing_regex, line) and not re.search(
                i18n_element_missing_regex, line
            ):
                continue
            # Find the exact index within the line where the regex is matched.
            for char_index in range(len(line)):
                position = char_index + 1
                search_chunk = line[char_index:]

                untranslated = False
                errtype = "ERRO"

                if re.match(i18n_element_missing_regex, search_chunk):
                    # Ignore if it's an element that can be part of a translated string
                    if not (
                        re.match(i18n_substring_regex, search_chunk)
                        and "$:" in line[:char_index]
                    ):
                        untranslated = True
                        if re.match(i18n_element_warn_regex, search_chunk):
                            errtype = "WARN"
                            warnings += 1
                        else:
                            errcount += 1

                elif re.match(i18n_attr_missing_regex, search_chunk):
                    untranslated = True
                    if re.match(i18n_attr_warn_regex, search_chunk):
                        errtype = "WARN"
                        warnings += 1
                    else:
                        errcount += 1

                if untranslated:
                    print(f"{errtype} {file}:{line_number}:{position}  {search_chunk}")

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
