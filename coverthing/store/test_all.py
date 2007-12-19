import unittest

import test_disk
import test_store
import test_warc

def test():
    modules = [test_disk, test_warc, test_store]
    suites = [m.suite() for m in modules]
    
    suite = unittest.TestSuite(suites)
    runner = unittest.TextTestRunner()
    runner.run(suite)

if __name__ == "__main__":
    test()
