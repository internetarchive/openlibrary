# incremental zlib compression, written by solrize, August 2009
import zlib

__doc__ = """
Compressor object for medium-sized, statistically-similar strings.

The idea is that you have a lot of moderate-sized strings (short email
messages or the like) that you would like to compress independently,
for storage in a lookup table where space is at a premium.  They
strings might be a few hundred bytes long on average.  That's not
enough to get much compression by gzipping without context.  gzip
works by starting with no knowledge, then building up knowledge (and
improving its compression ratio) as it goes along.

The trick is to "pre-seed" the gzip compressor with a bunch of text
(say a few kilobytes of messages concatenated) similar to the ones
that you want to compress separately, and pre-seed the gzip
decompressor with the same initial text.  That lets the compressor and
decompressor both start with enough knowledge to get good compression
even for fairly short strings.  This class puts a compressor and
decompressor into the same object, called a Compressor for convenience.

Usage: running the three lines

    compressor = Compressor(initial_seed)
    compressed_record = compressor.compress(some_record)
    restored_record = compressor.decompress(compressed_record)

where initial_seed is a few kilobytes of messages, and some_record is
a single record of maybe a few hundred bytes, for typical text, should
result in compressed_record being 50% or less of the size of
some_record, and restored_record being identical to some_record.
"""


class Compressor:
    def __init__(self, seed):
        c = zlib.compressobj(9)
        d_seed = c.compress(seed.encode())
        d_seed += c.flush(zlib.Z_SYNC_FLUSH)
        self.c_context = c.copy()

        d = zlib.decompressobj()
        d.decompress(d_seed)
        while d.unconsumed_tail:
            d.decompress(d.unconsumed_tail)
        self.d_context = d.copy()

    def compress(self, text):
        if not isinstance(text, str):
            text = text.decode()
        c = self.c_context.copy()
        t = c.compress(text.encode())
        t2 = c.flush(zlib.Z_FINISH)
        return t + t2

    def decompress(self, ctext):
        if not isinstance(ctext, bytes):
            ctext = ctext.encode()
        d = self.d_context.copy()
        t = d.decompress(ctext)
        while d.unconsumed_tail:
            t += d.decompress(d.unconsumed_tail)
        return t.decode()


def test_compressor():
    """
    >>> test_compressor()  # Self-doctest this code.
    """
    c = Compressor(__doc__)
    test_string = "zlib is a pretty good compression algorithm"
    ct = c.compress(test_string)
    # print('initial length=%d, compressed=%d' % (len(test_string), len(ct)))
    # the above string compresses from 43 bytes to 29 bytes using the
    # current doc text as compression seed, not bad for such short input.
    dt = c.decompress(ct)
    assert dt == test_string, (dt, test_string)
    # Test that utf-8 encoded bytes return the utf-8 string
    ct = c.compress(test_string.encode("utf-8"))
    # print('initial length=%d, compressed=%d' % (len(test_string), len(ct)))
    # the above string compresses from 43 bytes to 29 bytes using the
    # current doc text as compression seed, not bad for such short input.
    dt = c.decompress(ct)
    assert dt == test_string, (dt, test_string)


if __name__ == "__main__":
    test_compressor()
