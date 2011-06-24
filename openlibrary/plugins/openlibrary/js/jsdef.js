/**
 * JavaScript companion for jsdef templetor extension.
 *
 * For more details, see:
 * http://github.com/anandology/notebook/tree/master/2010/03/jsdef/
 */

/**
 * Python range function.
 *
 *      > range(2,5)
 *      2,3,4
 *      > range(5)
 *      0,1,2,3,4
 *      > range(0, 10, 2)
 *      0,2,4,6,8
 */
function range(begin, end, step) {
    step = step || 1;
    if (end == undefined) {
        end = begin;
        begin = 0;
    }

    var r = [];
    for (var i=begin; i<end; i += step) {
        r[r.length] = i;
    }
    return r;
}

/**
 * Adds Python's str.join method to Javascript Strings.
 *
 *      > " - ".join(["a", "b", "c"])
 *      a - b - c
 */
String.prototype.join = function(items) {
    return items.join(this);
}

/**
 * Python's len function.
 */
function len(array) {
    return array.length;
}

function enumerate(a) {
    var b = new Array(a.length);
    for (var i in a) {
        b[i] = [i, a[i]];
    }
    return b;
}

function ForLoop(parent, seq) {
    this.parent = parent;
    this.seq = seq;
    
    this.length = seq.length;
    this.index0 = -1;
}

ForLoop.prototype.next = function() {
    var i = this.index0+1;
    
    this.index0 = i;
    this.index = i+1;
    
    this.first = (i == 0);
    this.last = (i == this.length-1);
    
    this.odd = (this.index % 2 == 1);
    this.even = (this.index % 2 == 0);
    this.parity = ['even', 'odd'][this.index % 2];
    
    this.revindex0 = this.length - i;
    this.revindex = this.length - i + 1;
}

function foreach(seq, parent_loop, callback) {
    var loop = new ForLoop(parent_loop, seq);
    
    for (var i=0; i<seq.length; i++) {
        loop.next();
        
        var args = [loop];
        
        // case of "for a, b in ..."
        if (callback.length > 2) {
            for (var j in seq[i]) {
                args.push(seq[i][j]);
            }
        }
        else {
            args[1] = seq[i];
        }
        callback.apply(this, args);
    }
}

function websafe(value) {
    if (value == null || value == undefined) {
        return "";
    }
    else {
        return htmlquote(value.toString());
    }
}

function htmlquote(text) {
    text = text.replace("&", "&amp;"); // Must be done first!
    text = text.replace("<", "&lt;");
    text = text.replace(">", "&gt;");
    text = text.replace("'", "&#39;");
    text = text.replace('"', "&quot;");
    return text;
}