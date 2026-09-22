"""TOTP (RFC 6238) helpers for M25 MFA -- thin wrapper over `pyotp` so the
rest of the service never touches the library directly. Standard 30-second,
6-digit codes, compatible with Google Authenticator/Authy/1Password etc."""

from __future__ import annotations

import pyotp

_ISSUER = "IBVAP"


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(*, secret: str, username: str) -> str:
    """`otpauth://` URI an authenticator app scans (as a QR code) or a user
    enters manually -- encodes the secret, account name, and issuer."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=_ISSUER)


def verify_code(*, secret: str, code: str) -> bool:
    # valid_window=1 tolerates the code from one 30s step before/after now,
    # the standard allowance for clock drift between server and phone.
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)
