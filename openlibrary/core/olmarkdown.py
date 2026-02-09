"""Open Library Flavored Markdown, inspired by [Github Flavored Markdown][GFM].

GFM: http://github.github.com/github-flavored-markdown/

Differences from traditional Markdown:
* new lines in paragraph are treated as line breaks
* URLs are autolinked
* generated HTML is sanitized

The custom changes done here to markdown are also reptead in WMD editor,
the javascript markdown editor used in OL.
"""

import re

from infogami.utils.markdown import markdown
from openlibrary.core import helpers as h

# regexp to match urls and emails.
# Adopted from github-flavored-markdown (BSD-style open source license)
# http://github.com/github/github-flavored-markdown/blob/gh-pages/scripts/showdown.js#L158
AUTOLINK_RE = r'''(^|\s)(https?\:\/\/[^"\s<>]*[^.,;'">\:\s\<\>\)\]\!]|[a-z0-9_\-+=.]+@[a-z0-9\-]+(?:\.[a-z0-9-]+)+)'''

LINK_REFERENCE_RE = re.compile(r' *\[[^\[\] ]*\] *:')


class LineBreaksPreprocessor(markdown.Preprocessor):
    def run(self, lines):
        for i in range(len(lines) - 1):
            # append <br/> to all lines expect blank lines and the line before blankline.
            if (
                lines[i].strip()
                and lines[i + 1].strip()
                and not markdown.RE.regExp['tabbed'].match(lines[i])
                and not LINK_REFERENCE_RE.match(lines[i])
            ):
                lines[i] += "<br />"
        return lines


LINE_BREAKS_PREPROCESSOR = LineBreaksPreprocessor()


class AutolinkPreprocessor(markdown.Preprocessor):
    rx = re.compile(AUTOLINK_RE)

    def run(self, lines):
        for i in range(len(lines)):
            if not markdown.RE.regExp['tabbed'].match(lines[i]):
                lines[i] = self.rx.sub(r'\1<\2>', lines[i])
        return lines


AUTOLINK_PREPROCESSOR = AutolinkPreprocessor()


class AsteriskSafePreprocessor(markdown.Preprocessor):
    """
    Preprocessor to fix problematic asterisk patterns that create unclosed HTML tags.

    This addresses GitHub issue #4986 where patterns like **** or ** at the start
    of lines would create unclosed <em> or <strong> tags that leak out of the
    description container and break page formatting.

    Rules:
    - **** (4+ asterisks) at line start → # (heading)
    - ** (2 asterisks) followed by space at line start → * (bullet point)
    - Preserves valid markdown patterns like **bold** and *italic*
    """

    def run(self, lines):
        for i in range(len(lines)):
            line = lines[i]

            # Skip code blocks (lines starting with 4 spaces or a tab)
            # Check BEFORE stripping to preserve code block detection
            if line.startswith(("    ", "\t")):
                continue

            stripped = line.lstrip()

            # Fix: **** (4+ asterisks) at start → # heading
            if stripped.startswith("****"):
                # Count leading asterisks
                asterisk_count = 0
                for char in stripped:
                    if char == '*':
                        asterisk_count += 1
                    else:
                        break

                # Only replace if it's 4 or more asterisks
                if asterisk_count >= 4:
                    # Get the rest of the line after asterisks
                    rest_of_line = stripped[asterisk_count:]
                    # Check if it's followed by space or is at end of line
                    if not rest_of_line or rest_of_line[0].isspace():
                        # Replace with heading marker, preserving leading whitespace
                        leading_whitespace = line[: len(line) - len(stripped)]
                        lines[i] = leading_whitespace + "#" + rest_of_line

            # Fix: ** followed by space at line start → * bullet point
            # But only if it's not a valid **bold** pattern (i.e., not closed on same line)
            elif stripped.startswith("** ") and "**" not in stripped[3:]:
                # This is likely intended as a bullet point, not bold
                rest_of_line = stripped[2:]
                leading_whitespace = line[: len(line) - len(stripped)]
                lines[i] = leading_whitespace + "*" + rest_of_line

        return lines


ASTERISK_SAFE_PREPROCESSOR = AsteriskSafePreprocessor()


class OLMarkdown(markdown.Markdown):
    """Open Library flavored Markdown, inspired by [Github Flavored Markdown][GFM].

    GFM: http://github.github.com/github-flavored-markdown/

    Differences from traditional Markdown:
    * new lines in paragraph are treated as line breaks
    * URLs are autolinked
    * generated HTML is sanitized
    """

    def __init__(self, *a, **kw):
        markdown.Markdown.__init__(self, *a, **kw)
        self._patch()

    def _patch(self):
        patterns = self.inlinePatterns
        autolink = markdown.AutolinkPattern(
            markdown.AUTOLINK_RE.replace('http', 'https?')
        )
        patterns[patterns.index(markdown.AUTOLINK_PATTERN)] = autolink
        p = self.preprocessors
        p[p.index(markdown.LINE_BREAKS_PREPROCESSOR)] = LINE_BREAKS_PREPROCESSOR
        p.append(AUTOLINK_PREPROCESSOR)
        # Add asterisk safety preprocessor early in the pipeline
        # Insert at position 0 so it runs first, before other preprocessors
        p.insert(0, ASTERISK_SAFE_PREPROCESSOR)

    def convert(self):
        html = markdown.Markdown.convert(self)
        return h.sanitize(html)
