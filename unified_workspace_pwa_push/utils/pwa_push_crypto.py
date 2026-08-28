# =============================================================================
# unified_workspace_pwa_push - Web Push-kryptering och VAPID-signering
# =============================================================================
# Implementerar Web Push-protokollet (RFC 8291 + RFC 8188) med endast
# cryptography-biblioteket. Ingen extern dependency som pywebpush behovs.
#
# - VAPID: ECDSA P-256 signerade JWT-tokens (ES256 / JWS).
# - Payload: aes128gcm med ECDH P-256 nyckelutbyte.
# =============================================================================

import base64
import json
import os
import struct
import time
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    Prehashed,
    encode_dss_signature,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature


# -----------------------------------------------------------------------------
# Base64url-hjalpare
# -----------------------------------------------------------------------------

def b64url_encode(data):
    """Base64url-encode bytes utan padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(data):
    """Base64url-decode string/bytes, tolererar saknad padding."""
    if isinstance(data, str):
        data = data.encode("ascii")
    pad = 4 - (len(data) % 4)
    if pad != 4:
        data += b"=" * pad
    return base64.urlsafe_b64decode(data)


# -----------------------------------------------------------------------------
# VAPID-nycklar
# -----------------------------------------------------------------------------

def generate_vapid_keys():
    """Generera ett nytt VAPID P-256 nyckelpar.

    Returnerar (private_base64url, public_base64url).
    """
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()

    private_value = private_key.private_numbers().private_value
    private_bytes = private_value.to_bytes(32, "big")
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )

    return b64url_encode(private_bytes), b64url_encode(public_bytes)


def load_vapid_private_key(private_b64url):
    """Ladda en VAPID privat nyckel från base64url."""
    raw = b64url_decode(private_b64url)
    private_value = int.from_bytes(raw, "big")
    return ec.derive_private_key(
        private_value,
        ec.SECP256R1(),
        default_backend(),
    )


def load_vapid_public_key(public_b64url):
    """Ladda en VAPID publik nyckel från base64url."""
    raw = b64url_decode(public_b64url)
    return ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), raw
    )


# -----------------------------------------------------------------------------
# VAPID JWT (ES256 / JWS)
# -----------------------------------------------------------------------------

def _der_to_jws_signature(der_sig):
    """Konvertera DER ECDSA-signatur till raw r || s (64 bytes)."""
    from cryptography.hazmat.primitives.asymmetric.utils import (
        decode_dss_signature,
    )
    r, s = decode_dss_signature(der_sig)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def sign_vapid_jwt(endpoint, private_key, subscriber_email, ttl=86400):
    """Signera en VAPID JWT för en push-endpoint.

    :param endpoint: push service URL (t.ex. https://fcm.googleapis.com/...)
    :param private_key: cryptography ECDSA private key object
    :param subscriber_email: mailto:-adress som sub-claim
    :param ttl: JWT-livstid i sekunder
    :return: JWT-token som string
    """
    origin = urlparse(endpoint).scheme + "://" + urlparse(endpoint).netloc
    now = int(time.time())

    header = {"typ": "JWT", "alg": "ES256"}
    payload = {
        "aud": origin,
        "exp": now + ttl,
        "sub": subscriber_email if subscriber_email.startswith("mailto:") else f"mailto:{subscriber_email}",
    }

    signing_input = (
        b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        + "."
        + b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    )

    signature = private_key.sign(
        signing_input.encode("ascii"),
        ec.ECDSA(hashes.SHA256()),
    )
    jws_sig = _der_to_jws_signature(signature)

    return signing_input + "." + b64url_encode(jws_sig)


# -----------------------------------------------------------------------------
# HKDF (RFC 5869)
# -----------------------------------------------------------------------------

def _hkdf_extract(salt, ikm):
    """HKDF-Extract med SHA-256."""
    from cryptography.hazmat.primitives.hmac import HMAC
    h = HMAC(salt, hashes.SHA256(), backend=default_backend())
    h.update(ikm)
    return h.finalize()


def _hkdf_expand(prk, info, length):
    """HKDF-Expand med SHA-256."""
    from cryptography.hazmat.primitives.hmac import HMAC
    output = b""
    t = b""
    counter = 1
    while len(output) < length:
        h = HMAC(prk, hashes.SHA256(), backend=default_backend())
        h.update(t + info + bytes([counter]))
        t = h.finalize()
        output += t
        counter += 1
    return output[:length]


# -----------------------------------------------------------------------------
# aes128gcm payload-kryptering (RFC 8188 + RFC 8291)
# -----------------------------------------------------------------------------

def _derive_key_and_nonce(shared_secret, auth_secret, client_public_key,
                          server_public_key, salt):
    """Härleder CEK och nonce för aes128gcm."""
    # PRK = HKDF-Extract(salt=auth_secret, IKM=shared_secret)
    prk = _hkdf_extract(auth_secret, shared_secret)

    def info(label):
        return (
            label.encode("ascii")
            + b"\x00"
            + b"P-256"
            + b"\x00"
            + client_public_key
            + b"\x00"
            + server_public_key
        )

    cek = _hkdf_expand(prk, info("Content-Encoding: aes128gcm"), 16)
    nonce = _hkdf_expand(prk, info("Content-Encoding: nonce"), 12)
    return cek, nonce


def encrypt_payload(plaintext, client_p256dh_b64url, client_auth_b64url,
                    record_size=4096):
    """Kryptera en push-payload med aes128gcm.

    :param plaintext: bytes payload
    :param client_p256dh_b64url: base64url client public key
    :param client_auth_b64url: base64url auth secret
    :param record_size: max post size (default 4096)
    :return: bytes redo att POST-as till push endpoint
    """
    client_public_key = b64url_decode(client_p256dh_b64url)
    auth_secret = b64url_decode(client_auth_b64url)

    # Ephemeral ECDH-nyckelpar
    ephemeral_private = ec.generate_private_key(ec.SECP256R1(), default_backend())
    ephemeral_public = ephemeral_private.public_key()
    ephemeral_public_bytes = ephemeral_public.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )

    # Ladda klientens publika nyckel
    client_pub = load_vapid_public_key(client_p256dh_b64url)

    # Delad hemlighet
    shared_secret = ephemeral_private.exchange(ec.ECDH(), client_pub)

    # Salt
    salt = os.urandom(16)

    cek, nonce = _derive_key_and_nonce(
        shared_secret, auth_secret, client_public_key, ephemeral_public_bytes, salt
    )

    # Plaintext enligt RFC 8188: padding || delimiter(0x02) || content
    # Inga padding-bytes, bara delimiter.
    encoded_plaintext = b"\x02" + plaintext

    aesgcm = AESGCM(cek)
    ciphertext = aesgcm.encrypt(nonce, encoded_plaintext, None)

    # Layout: salt(16) || record_size(4) || keyid_len(1) || keyid(65) || ciphertext+tag
    rs = struct.pack(">I", record_size)
    keyid_len = struct.pack("B", len(ephemeral_public_bytes))

    return salt + rs + keyid_len + ephemeral_public_bytes + ciphertext


# -----------------------------------------------------------------------------
# Hjälp för att skicka en push-notis
# -----------------------------------------------------------------------------

def build_push_headers(endpoint, private_key_b64url, public_key_b64url,
                       subscriber_email, ttl=86400):
    """Bygg HTTP-headers för en Web Push-förfrågan.

    :return: dict med headers
    """
    private_key = load_vapid_private_key(private_key_b64url)
    jwt_token = sign_vapid_jwt(endpoint, private_key, subscriber_email, ttl)

    return {
        "Authorization": f"vapid t={jwt_token}, k={public_key_b64url}",
        "TTL": str(ttl),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
    }
