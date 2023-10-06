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
LIVE_USER1 = olsession.config['accounts']['live1']
LIVE_USER2 = olsession.config['accounts']['live2']
LIVE_USER3 = olsession.config['accounts']['live3']

OL_EDITION = 'OL11071177M'
IA_EDITION = 'clowns00melb'


class Borrow_Test(unittest.TestCase):
    @staticmethod
    def close_bookreader_switch_back_to_ol():
        time.sleep(2)
        olsession.driver.switch_to_window(olsession.driver.window_handles[1])
        olsession.driver.close()
        olsession.driver.switch_to_window(olsession.driver.window_handles[0])

    # borrow from IA, shows on IA & OL
    # borrow from OL, shows on IA & OL
    # waitlist on OL, borrow attempt from OL
    # waitlist on IA, borrow attempt from OL

    def ia_get_book_cta(self, ocaid, check_cta=None, make_assert=False, click=False):
        ia_ctas = {
            'borrow': {
                'xpath': '//*[@id="IABookReaderMessageWrapper"]/div/div[2]/button[1]',
                'copy': 'Borrow This Book',
                'mode': 'stream',
            },
            'waitlist': {
                'xpath': '//*[@id="IABookReaderMessageWrapper"]/div/div[2]/button[1]',
                'copy': 'Place a hold',
                'mode': 'stream',
            },
            'return': {
                'xpath': '//*[@id="BRtoolbarbuttons"]/span[2]/span[1]/a[1]',
                'copy': 'Return Book',
                'mode': 'stream',
            },
        }

        mode = ia_ctas[check_cta]['mode'] if check_cta else 'stream'
        olsession.driver.get(f'https://archive.org/{mode}/{ocaid}')

        if check_cta:
            time.sleep(1)
            xpath = ia_ctas[check_cta]['xpath']

            if make_assert:
                olsession.wait_for_clickable(
                    xpath, by=olsession.selenium_selector.XPATH
                )
            try:
                time.sleep(3)
                ia_cta_btn = olsession.driver.find_element_by_xpath(xpath)
            except:
                if make_assert:
                    raise
                return False

            conditions = ia_cta_btn and ia_cta_btn.text == ia_ctas[check_cta]['copy']

            if make_assert:
                assert conditions, 'Unable to find %s button on page.' % check_cta
            if not conditions:
                return False

            if click:
                time.sleep(5)
                ia_cta_btn.click()
                time.sleep(3)
            return ia_cta_btn
        return True

    def ol_get_book_cta(self, olid, check_cta=None, make_assert=False, click=False):
        olsession.goto('/books/%s' % olid)
        time.sleep(1)

        if check_cta:
            try:
                ol_cta_btn = olsession.driver.find_element_by_id('%s_ebook' % check_cta)
            except:
                if make_assert:
                    raise
                return False

            if make_assert:
                assert (
                    ol_cta_btn
                ), f'{check_cta} button not found on OL edition page: {olid}'
            elif not ol_cta_btn:
                return False
            if click:
                ol_cta_btn.click()
                time.sleep(1)
                try:
                    alert = olsession.driver.switch_to.alert
                    alert.accept()
                except:
                    pass
                time.sleep(3)
                olsession.goto('/books/%s' % olid)
            return ol_cta_btn
        return True

    def ol_verify_userid(self, olid, itemname):
        cta = self.ol_get_book_cta(
            olid, check_cta="read", make_assert=True, click=False
        )
        userid = cta.get_attribute('data-userid')
        assert (
            cta.get_attribute('data-userid') == itemname
        ), f'data-userid should be {itemname}, was {userid}'

    def test_ia_borrow_ol_read_ol_return(self):
        olsession.ia_login(test=self, **LIVE_USER1)
        olsession.login(test=self, **LIVE_USER1)
        self.ol_get_book_cta(
            OL_EDITION, check_cta="return", make_assert=False, click=True
        )
        self.ia_get_book_cta(
            ocaid=IA_EDITION, check_cta="return", make_assert=False, click=True
        )
        self.ia_get_book_cta(
            ocaid=IA_EDITION, check_cta="borrow", make_assert=True, click=True
        )
        self.ol_verify_userid(OL_EDITION, LIVE_USER1['itemname'])
        self.ol_get_book_cta(
            OL_EDITION, check_cta="return", make_assert=True, click=True
        )
        olsession.logout(test=self)
        olsession.ia_logout(test=self)

    def test_ol_borrow_ia_read_ol_return(self):
        olsession.ia_login(test=self, **LIVE_USER1)
        olsession.login(test=self, **LIVE_USER1)
        self.ol_get_book_cta(
            OL_EDITION, check_cta="return", make_assert=False, click=True
        )
        self.ol_get_book_cta(
            OL_EDITION, check_cta="borrow", make_assert=True, click=True
        )
        self.close_bookreader_switch_back_to_ol()
        self.ia_get_book_cta(
            IA_EDITION, check_cta="return", make_assert=True, click=False
        )
        self.ol_verify_userid(OL_EDITION, LIVE_USER1['itemname'])
        self.ol_get_book_cta(
            OL_EDITION, check_cta="return", make_assert=False, click=True
        )
        olsession.logout(test=self)
        olsession.ia_logout(test=self)

    def test_waitinglist(self):
        olsession.ia_login(test=self, **LIVE_USER2)
        olsession.login(test=self, **LIVE_USER2)
        self.ol_get_book_cta(
            OL_EDITION, check_cta="unwaitlist", make_assert=False, click=True
        )
        olsession.logout(test=self)
        olsession.login(test=self, **LIVE_USER1)
        self.ol_get_book_cta(
            OL_EDITION, check_cta="return", make_assert=False, click=True
        )
        self.ol_get_book_cta(
            OL_EDITION, check_cta="borrow", make_assert=True, click=True
        )
        self.close_bookreader_switch_back_to_ol()
        olsession.logout(test=self)
        olsession.login(test=self, **LIVE_USER2)
        self.ol_get_book_cta(
            OL_EDITION, check_cta="waitlist", make_assert=True, click=True
        )

        # go to /account/loans page and assert
        olsession.goto('/account/loans')
        link = olsession.driver.find_element_by_xpath(
            '//a[@href="/books/%s"]' % OL_EDITION
        )
        assert link, 'Book not found in waiting list on loans page'

        olsession.logout(test=self)
        olsession.login(test=self, **LIVE_USER1)
        self.ol_get_book_cta(
            OL_EDITION, check_cta="return", make_assert=True, click=True
        )
        olsession.logout(test=self)
        olsession.login(test=self, **LIVE_USER2)
        self.ol_get_book_cta(
            OL_EDITION, check_cta="borrow", make_assert=True, click=True
        )
        self.close_bookreader_switch_back_to_ol()
        self.ol_verify_userid(OL_EDITION, LIVE_USER2['itemname'])
        self.ia_get_book_cta(
            IA_EDITION, check_cta="return", make_assert=True, click=True
        )
        self.ol_get_book_cta(
            OL_EDITION, check_cta="return", make_assert=False, click=True
        )
        olsession.logout(test=self)
        olsession.ia_logout(test=self)
