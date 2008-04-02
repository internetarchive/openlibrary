
image_engine = "pil"

image_sizes = dict(thumbnail=(75, 75), small=(110, 110), medium=(160, 160), large=(500, 500))

cache_dir = "cache"
cache_size = 30000

redirect_amazon_images = True

from store.disk import WARCDisk

disk = WARCDisk(root="covers", prefix="covers")
