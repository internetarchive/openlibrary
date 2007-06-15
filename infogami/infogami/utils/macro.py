"""
Macro extension to markdown.

Macros take argument string as input and returns result as markdown text.
"""
import markdown

_macros = {}

def macro(f):
    """Decorator to register a markdown macro.
    Macro is a function that takes argument string and returns result as markdown string.
    """
    _macros[f.__name__] = f
    return f
    
def call_macro(name, args):
    if name in _macros:
        result = _macros[name](args)            
        # support for iterators
        if result and hasattr(result, 'next'):
            result = "\n".join(result)
        return result
    else:
        return "Unknown macro: **%s**(*%s*)" % (name, args)

class MacroPattern(markdown.BasePattern):
    """Inline pattern to replace macros."""
    def __init__(self, stash):
        pattern = r'{{(.*)\((.*)\)}}'
        markdown.BasePattern.__init__(self, pattern)
        self.stash = stash

    def handleMatch(self, m, doc):
        name, args = m.group(2), m.group(3)
        text = call_macro(name, args)
        md = markdown.Markdown(source=text, safe_mode=False)

        # markdown uses place-holders to replace html blocks. 
        # markdown.HtmlStash stores the html blocks to be replaced
        placeholder = self.stash.store(str(md))
        return doc.createTextNode(placeholder)

def macromarkdown(md):
    """Adds macro extenstions to the specified markdown instance."""
    md.inlinePatterns.append(MacroPattern(md.htmlStash))
    return md

@macro
def HelloWorld(args):
    """Hello world macro."""
    return "**Hello**, *world*"

@macro
def ListOfMacros(args):
    """Lists all available macros."""
    out = "\n"
    for k in sorted(_macros.keys()):
        out += '* **%s** - %s\n' % (k, _macros[k].__doc__)
    return out
    
if __name__ == "__main__":
    def get_markdown(text):
        md = markdown.Markdown(source=text, safe_mode=False)
        md = macromarkdown(md)
        return md
    
    print get_markdown("This is HelloWorld Macro. {{HelloWorld()}}\n\n" + 
            "And this is the list of available macros. {{ListOfMacros()}}")

