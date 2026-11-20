// Simple Javascript Templating
//
// Inspired by http://ejohn.org/blog/javascript-micro-templating/

export default function Template(tmpl_text) {
    const s = [];
    const js = ['var _p=[];', 'with(env) {'];
    let i, t;

    function addCode(text) {
        js.push(text);
    }
    function addExpr(text) {
        js.push(`_p.push(htmlquote(${text}));`);
    }
    function addText(text) {
        js.push(`_p.push(__s[${s.length}]);`);
        s.push(text);
    }

    const tokens = tmpl_text.split('<%');

    addText(tokens[0]);
    for (i = 1; i < tokens.length; i++) {
        t = tokens[i].split('%>');

        if (t[0][0] === '=') {
            addExpr(t[0].substr(1));
        } else {
            addCode(t[0]);
        }
        addText(t[1]);
    }
    js.push('}', "return _p.join('');");

    const f = new Function(['__s', 'env'], js.join('\n'));
    const g = function (env) {
        return f(s, env);
    };
    g.toString = function () {
        return tmpl_text;
    };
    g.toCode = function () {
        return f.toString();
    };
    return g;
}
