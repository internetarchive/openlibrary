from .. import forms
from .. import spamcheck

class TestRegister:
    def test_leaks(slef):
        f = forms.Register()
        assert f.displayname.value is None 
        f.displayname.value = 'Foo'

        f = forms.Register()
        assert f.displayname.value is None

    def test_validate(self, monkeypatch):
        monkeypatch.setattr(forms, 'find_account', lambda **kw: None)
        monkeypatch.setattr(spamcheck, "get_spam_domains", lambda: [])

        f = forms.Register()
        d = {
            'displayname': 'Foo',
            'username': 'foo',
            'email': 'foo@example.com',
            'email2': 'foo@example.com',
            'password': 'foo123'
        } 
        assert f.validates(d)
