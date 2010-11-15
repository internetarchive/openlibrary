"""Open Library Flavored Markdown, inspired by [Github Flavored Markdown][GFM].

GFM: http://github.github.com/github-flavored-markdown/

Differences from traditional Markdown:
* new lines in paragraph are treated as line breaks
* URLs are autolinked
* generated HTML is sanitized

The custom changes done here to markdown are also reptead in WMD editor, 
the javascript markdown editor used in OL.
"""

import helpers as h
import re
from infogami.utils.markdown import markdown

# regexp to match urls and emails. 
# Adopted from github-flavored-markdown (BSD-style open source license)
# http://github.com/github/github-flavored-markdown/blob/gh-pages/scripts/showdown.js#L158
AUTOLINK_RE = r'''(^|\s)(https?\:\/\/[^"\s<>]*[^.,;'">\:\s\<\>\)\]\!]|[a-z0-9_\-+=.]+@[a-z0-9\-]+(?:\.[a-z0-9-]+)+)'''

LINK_REFERENCE_RE = re.compile(r' *\[[^\[\] ]*\] *:')

class LineBreaksPreprocessor(markdown.Preprocessor):
    def run(self, lines) :
        for i in range(len(lines)-1):
            # append <br/> to all lines expect blank lines and the line before blankline.
            if (lines[i].strip() and lines[i+1].strip()
                and not markdown.RE.regExp['tabbed'].match(lines[i])
                and not LINK_REFERENCE_RE.match(lines[i])):
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
        p = self.preprocessors
        p[p.index(markdown.LINE_BREAKS_PREPROCESSOR)] = LINE_BREAKS_PREPROCESSOR
        p.append(AUTOLINK_PREPROCESSOR)
        
    def convert(self):
        html = markdown.Markdown.convert(self)
        return h.sanitize(html)
