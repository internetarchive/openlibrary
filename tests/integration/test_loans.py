#-*- coding: utf-8 -*-

"""
testing loans and waitlist
"""

import time
import unittest
from . import OLSession


olsession = OLSession()


# =========
# Accounts
# =========
LIVE_USER1 = config['accounts']['live1']
LIVE_USER2 = config['accounts']['live2']
INTERNAL_TEST_API_URL = olsession.config.internal_tests_api_key

EDITION = 'OL12149938M'

class Borrow_Test(unittest.TestCase):

    def test_borrow_return(self):
        olsession.login(**LIVE_USER1)
        olsession.goto('/books/%s' % EDITION)
        olsession.driver.find_element_by_class_name('borrow-btn').click()
        time.sleep(5)
        olsession.goto('/books/%s' % EDITION)
        btn = olsession.driver.find_element_by_class_name('borrow-btn')
        itemname = btn.get_attribute('data-userid')
        self.assertTrue(LIVE_USER1['itemname'] == itemname)

    def test_waitlist(self):
        pass
