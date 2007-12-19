from coverthing import code
from store.disk import WARCDisk
import web
import os

def mkdirs(path):
    if not os.path.exists(path):
        os.makedirs(path)

cache_dir = 'cache'
root = 'covers'

mkdirs(cache_dir)
mkdirs(root)

disk = WARCDisk(root='covers', prefix='covers')

if __name__ == "__main__":
    username = os.environ['USER']
    web.config.db_parameters = dict(dbn='postgres', db='coverthing', user=username, pw='')
    code.run(disk, cache_dir, web.reloader)
	
