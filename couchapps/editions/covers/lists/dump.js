function (head, req) {
    while(row = getRow()) {
        send([row.key[0], row.key[1], row.value['key'], row.value['cover']].join("\t") + "\n");
    }
}