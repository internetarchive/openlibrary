import string
from hashlib import sha1 as mkhash


# choose token length to make collisions unlikely (if there is a
# rare collision once in a while, we tolerate it, it just means
# that users may occasionally see some extra search results.
# don't make it excessively large because the tokens do use index space.
# The probability of a collision is approx.  1 - exp(-k**2 / (2*n)) where
# k = total # of facet tokens (= # of books * avg # of fields)
# n = 26 ** facet_token_length
# so for k = 10**8 and facet_token_length = 12,
# this probability is 1 - exp(-1e16/(2*26**12)) = approx 0.05.
# (That's the prob of EVER getting a collision, not the prob. of
# seeing a collision on any particular query).

facet_token_length = 12

# turn v into a str object, by encoding from unicode or numeric
# if necessary.
def coerce_str(v):
    if isinstance(v, str):
        v = v.encode('utf-8')
    v = str(v)  # in case v is a numeric type
    assert isinstance(v, str), (type(v), v)
    return v


# str, str -> str
def facet_token(field, v):
    token = []
    v = coerce_str(v)
    field = coerce_str(field)

    q = int(mkhash(f'FT,{field},{v}').hexdigest(), 16)
    for i in range(facet_token_length):
        q, r = divmod(q, 26)
        token.append(string.lowercase[r])
    return ''.join(token)
