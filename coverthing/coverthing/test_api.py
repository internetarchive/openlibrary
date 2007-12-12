import unittest
import api

class ClientTest(unittest.TestCase):
    def testUpload(self):
        response = app.request('/hello')
        