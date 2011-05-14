from .. import account

def test_create_list_doc(wildcard):
    key = "account/foo/verify"
    username = "foo"
    email = "foo@example.com"
    
    doc = account.create_link_doc(key, username, email)
    
    assert doc == {
        "_key": key,
        "_rev": None,
        "type": "account-link",
        "username": username,
        "email": email,
        "code": wildcard,
        "created_on": wildcard,
        "expires_on": wildcard
    }
    
def test_verify_hash():
    secret_key = "aqXwLJVOcV"
    hash = account.generate_hash(secret_key, "foo")
    assert account.verify_hash(secret_key, "foo", hash) == True
