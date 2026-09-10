"""Password hashing. Uses bcrypt via passlib."""

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# A real (but meaningless) bcrypt hash to verify against when no such user
# exists, so a nonexistent username still costs one bcrypt round-trip --
# without this, "user not found" returns measurably faster than "wrong
# password", letting an attacker enumerate valid usernames by timing alone.
DUMMY_PASSWORD_HASH = _pwd_context.hash("not-a-real-password-used-only-to-equalize-timing")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(plain_password, password_hash)
