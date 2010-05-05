"""Templetor extension to support javascript templates.

During AJAX development, there will be need to generate HTML and update
some part of the DOM. It it clumsy to do that in javascript. Even though
there are some javascript template engines, it often ends up in duplication
because of writing a Python template and a Javascript template for doing
the same thing.

This extension adds a new block `jsdef` to Templetor, which provides a
a template function just like `def` and also generates an equivalent
javascript function.


USAGE:

    import jsdef
    render = web.tempalte.render("templates/", extensions=[jsdef.extension])


Sample Template:

    $def with (page)
    
    <h1>$page.title</h1>
    
    $jsdef render_books(books):
        <ul>
            $for book in books:
                <li><a href="$book.key">$book.title</a></li>
        </ul>
        
    <div id="books">
        $:render_books(page.books)
    </div>
    
    <script type="text/javascript">
        function udpate_books(books) {
            document.getElementById("books").innerHTML = render_books(books);
        }
    </script>

For more details, see:
http://github.com/anandology/notebook/tree/master/2010/03/jsdef/
"""

__author__ = "Anand Chitipothu <anandology@gmail.com>"
__version__ = "0.2"

"""change notes:

0.1: first release
0.2: python to javascript conversion for "and", "or" and "not" keywords
"""

import simplejson

import web
from web.template import Template, Parser, LineNode, SuiteNode, DefNode, PythonTokenizer, INDENT

def extension(parser):
    r"""jsdef extension. Adds support for `jsdef` block to template parser.
    
        >>> t = Template("$jsdef hello(name):\n    Hello $name!", extensions=[extension])
        >>> print t() #doctest:+NORMALIZE_WHITESPACE
        <script type="text/javascript">
        function hello(name){
            var self = [], loop;
            self.push("Hello "); self.push(websafe(name)); self.push("!\n");
            return self.join("");
        }
        </script>        
    """
    parser.statement_nodes['jsdef'] = JSDefNode
    return parser

class JSDefNode(DefNode):
    """Node to represent jsdef block.
    """
    def __init__(self, *a, **kw):
        DefNode.__init__(self, *a, **kw)
        self.suite.sections.append(JSNode(self))
        self.stmt = self.stmt.replace("jsdef", "def")
    
INDENT = "    "

class JSNode:
    def __init__(self, node):
        self.node = node
        self._count = 0
        
    def emit(self, indent, text_indent=""):
        # Code generation logic is changed in version 0.34
        if web.__version__ < "0.34":
            return indent[4:] + 'yield "", %s\n' % repr(self.jsemit(self.node, ""))
        else:
            return indent[4:] + 'self.extend(%s)\n' % repr(self.jsemit(self.node, ""))
    
    def jsemit(self, node, indent):
        r"""Emit Javascript for given node.
        
            >>> jsemit = JSNode(None).jsemit
            >>> jsemit(web.template.StatementNode("break"), "")
            'break;\n'
            >>> jsemit(web.template.AssignmentNode("x = 1"), "")
            'var x = 1;\n'
        """   
        name = "jsemit_" + node.__class__.__name__
        f= getattr(self, name, None)
        if f:
            return f(node, indent)
        else:
            return ""
            
    def jsemit_SuiteNode(self, node, indent):
        return u"".join(self.jsemit(s, indent) for s in node.sections)
            
    def jsemit_LineNode(self, node, indent):
        text = ["self.push(%s);" % self.jsemit(n, "") for n in node.nodes]
        return indent + " ".join(text) + "\n"
        
    def jsemit_TextNode(self, node, indent):
        return simplejson.dumps(node.value)
    
    def jsemit_ExpressionNode(self, node, indent):
        if node.escape:
            return "websafe(%s)" % py2js(node.value)
        else:
            return py2js(node.value)

    def jsemit_AssignmentNode(self, node, indent):
        return indent + "var " + py2js(node.code) + ";\n"
        
    def jsemit_StatementNode(self, node, indent):
        return indent + py2js(node.stmt) + ";\n"
                
    def jsemit_BlockNode(self, node, indent):
        text = ""
        
        for n in ["if", "elif", "else", "for"]:
            if node.stmt.startswith(n):
                name = n
                break
        else:
            return ""
            
        expr = node.stmt[len(name):].strip(": ")        
        expr = expr and "(" + expr + ")"
        
        text += indent + "%s %s {\n" % (name, py2js(expr))
        text += self.jsemit(node.suite, indent + INDENT)
        text += indent + "}\n"
        return text
        
    jsemit_IfNode = jsemit_BlockNode
    jsemit_ElseNode = jsemit_BlockNode
    
    def jsemit_ForNode(self, node, indent):
        tok = PythonTokenizer(node.stmt)
        tok.consume_till('in')
        a = node.stmt[:tok.index].strip() # for i in
        a = a[len("for"):-len("in")].strip() # strip `for` and `in`
        
        b = node.stmt[tok.index:-1].strip() # rest of for stmt excluding :
        b = web.re_compile("loop.setup\((.*)\)").match(b).group(1)

        text = ""
        text += indent + "foreach(%s, loop, function(loop, %s) {\n" % (py2js(b), a)
        text += self.jsemit(node.suite, indent + INDENT)
        text += indent + "});\n"
        return text
        
    def jsemit_JSDefNode(self, node, indent):
        text = ""
        text += '<script type="text/javascript"><!--\n'
        
        text += node.stmt.replace("def ", "function ").strip(": ") + "{\n"
        text += '    var self = [], loop;\n'
        text += self.jsemit(node.suite, indent + INDENT)
        text += '    return self.join("");\n' 
        text += "}\n"
        
        text += "//--></script>\n"
        return text
        
def tokenize(code):
    """Tokenize python code.
    
        >>> list(tokenize("x + y"))
        ['x', ' ', '+', ' ', 'y']
    """
    end = 0
    tok = PythonTokenizer(code)
    try:
        while True:
            x = tok.next()
            begin = x.begin[1]
            if begin > end:
                yield ' ' * (begin - end)
            if x.value:
                yield x.value
            end = x.end[1]
    except StopIteration:
        pass
            
def py2js(expr):
    """Converts a python expression to javascript.
    
        >>> py2js("x + y")
        'x + y'
        >>> py2js("x and y")
        'x && y'
        >>> py2js("x or not y")
        'x || ! y'
    """
    d = {"and": "&&", "or": "||", "not": "!"}
    def f(tokens):
       for t in tokens:
           yield d.get(t, t) 
         
    return "".join(f(tokenize(expr)))
    
def _testrun(code):
    parser = extension(web.template.Parser())
    root = parser.parse(code)
    node = root.suite.sections[0]
    jnode = JSNode(node)
    return jnode.jsemit(node, "")    
    
def _test():
    r"""
        >>> t = _testrun
        >>> t("$x")
        'self.push(websafe(x));\n'
        >>> t("$:x")
        'self.push(x);\n'
        >>> t("$ x = 1")
        'var x = 1;\n'
        >>> t("$ x = a and b")
        'var x = a && b;\n'
        >>> t("$if a or not b: $a")
        u'if (a || ! b) {\n    self.push(websafe(a));\n}\n'
        >>> t("$for i in a and a.data or []: $i")
        u'foreach(a && a.data || [], loop, function(loop, i) {\n    self.push(websafe(i));\n});\n'
    """
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()