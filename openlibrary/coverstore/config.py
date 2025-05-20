image_engine = "pil"
image_sizes = {"S": (116, 58), "M": (180, 360), "L": (500, 500)}

default_image = None
data_root = None

ol_url = "http://openlibrary.org/"

# ids of the blocked covers
# this is used to block covers when someone requests
# an image to be blocked.
blocked_covers: list[str] = []


def get(name, default=None):
    return globals().get(name, default)


def load_from_file(configfile: str) -> None:
    """Load configuration from a file."""
    import yaml

    with open(configfile) as in_file:
        d = yaml.safe_load(in_file)
    for k, v in d.items():
        globals()[k] = v
