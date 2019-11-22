from openlibrary.accounts import model


def test_verify_hash():
    secret_key = "aqXwLJVOcV"
    hash = model.generate_hash(secret_key, "foo")
    assert model.verify_hash(secret_key, "foo", hash) == True
