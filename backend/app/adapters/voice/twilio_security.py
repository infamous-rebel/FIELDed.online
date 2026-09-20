"""Twilio-specific request signature verification.

Implements Twilio's official request validation algorithm:

1. Take the full request URL (including query string)
2. Append all POST parameters sorted by name (key=value pairs)
3. HMAC-SHA256 the resulting string with the Auth Token
4. Base64-encode the result
5. Compare against the ``X-Twilio-Signature`` header

This module is a provider-specific seam alongside the generic HMAC
verification in ``webhook_service.verify_webhook_signature``.  Other
providers may use the generic mechanism; Twilio uses this one.

Fail-closed:  missing token, missing signature, or mismatch all
return False.  Constant-time comparison prevents timing attacks.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


def verify_twilio_signature(
    url: str,
    params: dict[str, str] | list[tuple[str, str]],
    auth_token: str,
    signature: str,
) -> bool:
    """Verify a Twilio request signature.

    Args:
        url: The full request URL (scheme + host + path + query).
            For FIELDed this is reconstructed from ``PUBLIC_BASE_URL``
            + the request path, since Twilio signs the public URL.
        params: POST parameters as a dict or list of (key, value)
            tuples.  Form-encoded body parameters from Twilio.
        auth_token: The Twilio Auth Token (shared secret).
        signature: The value of the ``X-Twilio-Signature`` header.

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not auth_token or not signature:
        return False

    # Build the string to sign: URL + sorted key=value pairs
    data = url
    if params:
        if isinstance(params, list):
            sorted_params = sorted(params, key=lambda x: x[0])
        else:
            sorted_params = sorted(params.items())
        data += urlencode(sorted_params)

    # HMAC-SHA256 + Base64
    expected = base64.b64encode(
        hmac.new(
            auth_token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return hmac.compare_digest(expected, signature)
