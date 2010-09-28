
image_engine = "pil"
image_sizes = dict(S=(116, 58), M=(180, 360), L=(500, 500))

default_image = None
data_root = None

ol_url = "http://openlibrary.org/"

def get(name, default=None):
    return globals().get(name, default)