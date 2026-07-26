from app.domain.shared.password import hash_password, verify_password


def test_verify_password_accepts_the_correct_password():
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded) is True


def test_verify_password_rejects_the_wrong_password():
    encoded = hash_password("correct horse battery staple")
    assert verify_password("wrong password", encoded) is False


def test_hash_password_salts_each_call_differently():
    assert hash_password("same password") != hash_password("same password")


def test_verify_password_rejects_malformed_hashes():
    assert verify_password("anything", "not-a-valid-hash") is False
