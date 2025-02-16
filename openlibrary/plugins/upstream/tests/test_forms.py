from .. import forms, spamcheck


class TestRegister:
    def test_validate(self, monkeypatch):
        monkeypatch.setattr(forms, 'find_account', lambda **kw: None)
        monkeypatch.setattr(forms, 'find_ia_account', lambda **kw: None)
        monkeypatch.setattr(spamcheck, "get_spam_domains", list)

        f = forms.Register()
        d = {
            'username': 'foo',
            'email': 'foo@example.com',
            'password': 'foo123',
            'password2': 'foo123',
        }
        assert f.validates(d)
