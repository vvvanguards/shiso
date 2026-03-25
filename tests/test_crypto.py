"""Tests for Fernet encryption/decryption."""

import pytest
from cryptography.fernet import Fernet

from shiso.scraper.services.crypto import decrypt, encrypt


@pytest.fixture()
def temp_key(tmp_path, monkeypatch):
    """Use a temp Fernet key for tests."""
    key = Fernet.generate_key()
    key_path = tmp_path / ".fernet.key"
    key_path.write_bytes(key)

    from shiso.scraper.services import crypto
    monkeypatch.setattr(crypto, "KEY_PATH", key_path)


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self, temp_key):
        original = "my_secret_password_123!@#"
        encrypted = encrypt(original)
        decrypted = decrypt(encrypted)

        assert decrypted == original

    def test_different_ciphertext_each_time(self, temp_key):
        plaintext = "same_password"
        encrypted1 = encrypt(plaintext)
        encrypted2 = encrypt(plaintext)

        assert encrypted1 != encrypted2

        assert decrypt(encrypted1) == plaintext
        assert decrypt(encrypted2) == plaintext

    def test_tampered_ciphertext_raises(self, temp_key):
        import cryptography.fernet

        encrypted = encrypt("password")
        tampered = encrypted[:-4] + "XXXX"

        with pytest.raises(cryptography.fernet.InvalidToken):
            decrypt(tampered)

    def test_empty_string_roundtrips(self, temp_key):
        encrypted = encrypt("")
        decrypted = decrypt(encrypted)
        assert decrypted == ""

    def test_unicode_roundtrips(self, temp_key):
        original = "пароль密码🔐"
        encrypted = encrypt(original)
        decrypted = decrypt(encrypted)
        assert decrypted == original
