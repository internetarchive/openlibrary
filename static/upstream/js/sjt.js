// Simple Javascript Templating 
// Anand Chitipothu - http://anandology.com/ - MIT Licensed
//
// Inspired by http://ejohn.org/blog/javascript-micro-templating/
function Template(tmpl_text) {
    var s = [];
    var js = ["var p=[];", "with(env) {"]

    function addCode(text) {
        js.push(text);
    }
    function addExpr(text) {
        js.push("p.push(" + text + ");");
    }
    function addText(text) {
        js.push("p.push(__s[" + s.length + "]);"); 
        s.push(text);
    }

    var tokens = tmpl_text.split("<%");

    addText(tokens[0]);
    for (var i=1; i < tokens.length; i++) {
        var t = tokens[i].split('%>')
        
        if (t[0][0] == "=")
            addExpr(t[0].substr(1));
        else
            addCode(t[0]);

        addText(t[1]);
    }
    js.push("}", "return p.join('');");

    var f = Function(["__s", "env"], js.join("\n"));
    var g = function(env) {
        return f(s, env);
    }
    g.toString = function() { return tmpl_text; }
    g.toCode = function() { return f.toString(); }
    return g;
}

