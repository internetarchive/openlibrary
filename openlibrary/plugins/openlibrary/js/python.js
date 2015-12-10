function commify(n) {
    var text = n.toString();
    var re = /(\d+)(\d{3})/;

    while (re.test(text)) {
        text = text.replace(re, "$1,$2");
    }

    return text;
}