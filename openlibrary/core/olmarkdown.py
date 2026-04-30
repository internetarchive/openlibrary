"""Open Library Flavored Markdown, inspired by [Github Flavored Markdown][GFM].

GFM: http://github.github.com/github-flavored-markdown/

Differences from traditional Markdown:
* new lines in paragraph are treated as line breaks
* URLs are autolinked
* generated HTML is sanitized

"""

import re

from infogami.utils.markdown import markdown

from openlibrary.core import helpers as h

# regexp to match urls and emails.
# Adopted from github-flavored-markdown (BSD-style open source license)
# http://github.com/github/github-flavored-markdown/blob/gh-pages/scripts/showdown.js#L158
AUTOLINK_RE = r"""(^|\s)(https?\:\/\/[^"\s<>]*[^.,;'">\:\s\<\>\)\]\!]|[a-z0-9_\-+=.]+@[a-z0-9\-]+(?:\.[a-z0-9-]+)+)"""

LINK_REFERENCE_RE = re.compile(r" *\[[^\[\] ]*\] *:")


class FencedCodePreprocessor(markdown.Preprocessor):
    """Convert GitHub-style fenced code blocks into 4-space indented blocks.

    Python-Markdown 1.6b (the upstream vendored at vendor/infogami) predates
    fenced code blocks, so ```...``` would otherwise render as literal backticks
    with <br /> between the lines. Rewriting to the indented form lets the
    base renderer emit <pre><code>, and keeps the content out of reach of the
    line-break, autolink, header, and HTML-block preprocessors (all of which
    skip indented lines).
    """

    FENCE_RE = re.compile(r"^`{3,}[^`]*$")

    def run(self, lines):
        processed = []
        idx = 0
        line_count = len(lines)
        while idx < line_count:
            if self.FENCE_RE.match(lines[idx]):
                fence_end = idx + 1
                while fence_end < line_count and not self.FENCE_RE.match(lines[fence_end]):
                    fence_end += 1
                if fence_end < line_count:
                    if processed and processed[-1].strip():
                        processed.append("")
                    for code_line in lines[idx + 1 : fence_end]:
                        processed.append("    " + code_line)
                    if fence_end + 1 < line_count and lines[fence_end + 1].strip():
                        processed.append("")
                    idx = fence_end + 1
                    continue
            processed.append(lines[idx])
            idx += 1
        return processed


FENCED_CODE_PREPROCESSOR = FencedCodePreprocessor()


class LineBreaksPreprocessor(markdown.Preprocessor):
    def run(self, lines):
        for i in range(len(lines) - 1):
            # append <br/> to all lines expect blank lines and the line before blankline.
            if (
                lines[i].strip()
                and lines[i + 1].strip()
                and not markdown.RE.regExp["tabbed"].match(lines[i])
                and not LINK_REFERENCE_RE.match(lines[i])
                and not lines[i].lstrip().startswith(">")
            ):
                lines[i] += "<br />"
        return lines


LINE_BREAKS_PREPROCESSOR = LineBreaksPreprocessor()


class AutolinkPreprocessor(markdown.Preprocessor):
    rx = re.compile(AUTOLINK_RE)

    def run(self, lines):
        for i in range(len(lines)):
            if not markdown.RE.regExp["tabbed"].match(lines[i]):
                lines[i] = self.rx.sub(r"\1<\2>", lines[i])
        return lines


AUTOLINK_PREPROCESSOR = AutolinkPreprocessor()


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
        autolink = markdown.AutolinkPattern(markdown.AUTOLINK_RE.replace("http", "https?"))
        patterns[patterns.index(markdown.AUTOLINK_PATTERN)] = autolink
        p = self.preprocessors
        p.insert(0, FENCED_CODE_PREPROCESSOR)
        p[p.index(markdown.LINE_BREAKS_PREPROCESSOR)] = LINE_BREAKS_PREPROCESSOR
        p.append(AUTOLINK_PREPROCESSOR)

    def convert(self):
        html = markdown.Markdown.convert(self)
        return h.sanitize(html)
