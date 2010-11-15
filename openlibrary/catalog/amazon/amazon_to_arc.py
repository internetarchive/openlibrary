import socket

#url = "http://www.amazon.com/dp/1847195881"
#asin = "1847195881"

def get(sock, host, url):
    send = 'GET %s HTTP/1.1\r\nHost: %s\r\nAccept-Encoding: identity\r\n\r\n' % (url, host)
    sock.sendall(send)

    fp = sock.makefile('rb', 0)

    line = fp.readline()
    print 'status:', `line`

    state = 'header'
    for line in fp:
        if line == '\r\n':
            break
        print 'header', `line`

    while True:
        chunk_size = int(fp.readline(),16)
        print chunk_size
        if chunk_size == 0:
            break
        print len(fp.read(chunk_size))
        print `fp.read(2)`
    line = fp.readline()
    print `line`
    fp.close()

host = 'openlibrary.org'
host = 'www.amazon.com'
sock = socket.create_connection((host, 80))

url = 'http://openlibrary.org/type/work'
url = "http://www.amazon.com/dp/1847195881"
get(sock, host, url)

url = 'http://openlibrary.org/type/edition'
url = "http://www.amazon.com/dp/0393062287"
get(sock, host, url)
