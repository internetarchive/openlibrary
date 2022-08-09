image_engine = "pil"
image_sizes = dict(S=(116, 58), M=(180, 360), L=(500, 500))

default_image = None
data_root = None

ol_url = "http://openlibrary.org/"

# ids of the blocked covers
# this is used to block covers when someone requests
# an image to be blocked.
blocked_covers: list[str] = []


def get(name, default=None):
    return globals().get(name, default)
