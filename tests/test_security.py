from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hashing():
    """Verify that bcrypt password hashing and verification work as expected."""
    raw_password = "SecurePassword123!"
    hashed = hash_password(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_tokens():
    """Verify access and refresh token creation and payload decoding."""
    payload = {"sub": "user_id_123", "role": "OWNER"}

    access_token = create_access_token(payload)
    decoded_access = decode_token(access_token)
    assert decoded_access["sub"] == "user_id_123"
    assert decoded_access["role"] == "OWNER"
    assert decoded_access["type"] == "access"
    assert "exp" in decoded_access

    refresh_token = create_refresh_token(payload)
    decoded_refresh = decode_token(refresh_token)
    assert decoded_refresh["sub"] == "user_id_123"
    assert decoded_refresh["type"] == "refresh"
