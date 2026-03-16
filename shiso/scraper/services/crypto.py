"""
Fernet encryption for storing credentials at rest.

Key is stored in finance/dashboard/config/.fernet.key (auto-generated on first use).
"""

from pathlib import Path

from cryptography.fernet import Fernet

KEY_PATH = Path(__file__).parent.parent / "config" / ".fernet.key"


def _get_fernet() -> Fernet:
    if not KEY_PATH.exists():
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        KEY_PATH.write_bytes(Fernet.generate_key())
    return Fernet(KEY_PATH.read_bytes().strip())


def encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()
