import time
from openlibrary.core.task import oltask
import logging

logger1 = logging.getLogger("Bunyan 1")
logger1.setLevel(logging.DEBUG)
h = logging.StreamHandler()
h.setLevel(logging.DEBUG)
f = logging.Formatter("%(levelname)s : %(filename)s : %(name)s : %(message)s")
h.setFormatter(f)
logger1.addHandler(h)


@oltask
def baz(a, b):
    time.sleep(10)
    logger1.debug("Hello")
    logger1.warn("Hello")
    logger1.critical("Dead")
    logger1.info("""All source code published here is available under the terms of the GNU Affero General Public License, version 3. Please see http://gplv3.fsf.org/ for more information.""")
    return a + b



for i in range(50):
    print "Hello", baz.delay(2, 2)




