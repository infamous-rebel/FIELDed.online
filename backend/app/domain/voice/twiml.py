"""TwiML response generation for Twilio voice interactions.

Small, isolated layer that produces valid TwiML XML for the Twilio
call flow:

    <Response>
        <Say>greeting or agent reply</Say>
        <Gather input="speech" action="..." method="POST" />
    </Response>

Uses raw XML construction — the verb set is small (<Say>, <Gather>,
<Hangup>, <Response>) and does not justify a template engine or the
official Twilio helper library as a dependency.

All URLs are generated from configuration (``PUBLIC_BASE_URL``),
never hardcoded.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any


def _element(tag: str, text: str | None = None, **attribs: Any) -> ET.Element:
    """Create an XML element with optional text and attributes."""
    elem = ET.Element(tag, {k: str(v) for k, v in attribs.items()})
    if text is not None:
        elem.text = str(text)
    return elem


def gather_response(
    *,
    say_text: str,
    gather_action_url: str,
    gather_method: str = "POST",
    speech_timeout: str = "auto",
    language: str | None = None,
    voice: str | None = None,
) -> str:
    """Build a TwiML response with <Say> followed by <Gather>.

    Args:
        say_text: Text to speak to the caller.
        gather_action_url: URL Twilio POSTs the speech transcript to.
        gather_method: HTTP method for the Gather callback.
        speech_timeout: Twilio speech timeout setting.
        language: BCP-47 language tag (e.g. "en-US").
        voice: Twilio voice name (e.g. "alice").

    Returns:
        Valid TwiML XML string.
    """
    response = _element("Response")

    say_attribs: dict[str, str] = {}
    if language:
        say_attribs["language"] = language
    if voice:
        say_attribs["voice"] = voice

    say = _element("Say", say_text, **say_attribs)
    response.append(say)

    gather_attribs: dict[str, str] = {
        "input": "speech",
        "action": gather_action_url,
        "method": gather_method,
        "speechTimeout": speech_timeout,
    }
    if language:
        gather_attribs["language"] = language

    gather = _element("Gather", **gather_attribs)
    response.append(gather)

    return _to_xml(response)


def say_and_hangup_response(
    *,
    say_text: str,
    language: str | None = None,
    voice: str | None = None,
) -> str:
    """Build a TwiML response with <Say> followed by <Hangup>.

    Used when the call should end after the agent's final reply.
    """
    response = _element("Response")

    say_attribs: dict[str, str] = {}
    if language:
        say_attribs["language"] = language
    if voice:
        say_attribs["voice"] = voice

    say = _element("Say", say_text, **say_attribs)
    response.append(say)
    response.append(_element("Hangup"))

    return _to_xml(response)


def hangup_response() -> str:
    """Build a TwiML response with only <Hangup>.

    Used for error cases where no speech is needed.
    """
    response = _element("Response")
    response.append(_element("Hangup"))
    return _to_xml(response)


def retry_gather_response(
    *,
    gather_action_url: str,
    message: str = "I didn't catch that. Could you please repeat it?",
    language: str | None = None,
) -> str:
    """Build a TwiML retry prompt when speech input was empty.

    Does not invoke the LLM — uses a deterministic retry message.
    """
    return gather_response(
        say_text=message,
        gather_action_url=gather_action_url,
        language=language,
    )


def error_response(
    *,
    message: str = "An error occurred. Please try again later.",
    language: str | None = None,
) -> str:
    """Build a TwiML error response with <Say> + <Hangup>.

    Used when the call cannot proceed (invalid state, tenant
    mismatch, etc.).
    """
    return say_and_hangup_response(say_text=message, language=language)


def _to_xml(element: ET.Element) -> str:
    """Serialize an Element to an XML string declaration + body."""
    return ET.tostring(element, encoding="unicode", xml_declaration=False)
