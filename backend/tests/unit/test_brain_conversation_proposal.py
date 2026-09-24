"""Unit tests for Brain conversation proposal extraction and detection.

Covers the production defect where an explicit proposal request from the
business owner results in no BrainProposal being created because:
1. The AI asks for confirmation instead of emitting a [PROPOSAL] block.
2. The extraction regex only matches [PROPOSAL]...[/PROPOSAL] blocks.

Tests:
- _is_explicit_proposal_request() detection logic
- _extract_proposal_from_response() with all three patterns
- End-to-end proposal creation with directive injection
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.ai.base import AIProvider, AIResponse
from app.domain.business.conversation_service import BrainConversationService
from app.domain.business.models import (
    BrainConversation,
    BrainMessage,
    BrainProposal,
)
from app.domain.common.enums import (
    BrainConversationStatus,
    BrainMessageRole,
    BrainProposalStatus,
    BrainProposalType,
)


# ---------------------------------------------------------------------------
# _is_explicit_proposal_request
# ---------------------------------------------------------------------------


class TestIsExplicitProposalRequest:
    """Test detection of explicit proposal requests in owner messages."""

    def test_create_formal_proposalal(self):
        msg = (
            "Create a formal Qualification Rule proposal now based on "
            "the Business Consulting knowledge you have learned."
        )
        assert BrainConversationService._is_explicit_proposal_request(msg) is True

    def test_propose_a_rule(self):
        assert BrainConversationService._is_explicit_proposal_request("Propose a new pricing rule") is True

    def test_submit_proposal_for_approval(self):
        msg = "Mark it explicitly as PROPOSED — NOT ACTIVE and submit it to me for approval."
        assert BrainConversationService._is_explicit_proposal_request(msg) is True

    def test_generate_a_proposal(self):
        assert BrainConversationService._is_explicit_proposal_request("Generate a proposal for cancellation policy") is True

    def test_draft_a_proposal(self):
        assert BrainConversationService._is_explicit_proposal_request("Draft a proposal for a new service") is True

    def test_make_a_proposal(self):
        assert BrainConversationService._is_explicit_proposal_request("Make a proposal for operating hours") is True

    def test_casual_message_not_detected(self):
        assert BrainConversationService._is_explicit_proposal_request("What services can I improve?") is False

    def test_hello_not_detected(self):
        assert BrainConversationService._is_explicit_proposal_request("Hello") is False

    def test_pricing_question_not_detected(self):
        assert BrainConversationService._is_explicit_proposal_request("Tell me about pricing") is False

    def test_casual_proposal_mention_without_trigger(self):
        """Just saying 'proposal' without a trigger phrase should not match."""
        assert BrainConversationService._is_explicit_proposal_request("What's the status of my proposal?") is False

    def test_empty_message(self):
        assert BrainConversationService._is_explicit_proposal_request("") is False


# ---------------------------------------------------------------------------
# _extract_proposal_from_response
# ---------------------------------------------------------------------------


class TestExtractProposalFromResponse:
    """Test proposal extraction from AI response text."""

    def _make_service(self) -> BrainConversationService:
        """Create a minimal service instance for testing pure methods."""
        mock_session = MagicMock()
        mock_ai = MagicMock(spec=AIProvider)
        service = BrainConversationService(mock_session, mock_ai)
        return service

    def test_pattern1_proposal_with_code_fence(self):
        """[PROPOSAL] ```json {...} ``` [/PROPOSAL]"""
        content = """Here is the proposal:

[PROPOSAL]
```json
{
  "proposal_type": "qualification_rule",
  "summary": "Require project scope before quoting",
  "reasoning": "Need details to price accurately",
  "confidence": 0.85,
  "affected_area": "qualification",
  "rule_type": "required_information",
  "rule_name": "Project Scope Required",
  "rule_data": {"required_fields": ["project_scope", "budget_range"]}
}
```
[/PROPOSAL]

This rule ensures we have enough info."""

        service = self._make_service()
        result = service._extract_proposal_from_response(content)
        assert result is not None
        assert result["proposal_type"] == "qualification_rule"
        assert result["summary"] == "Require project scope before quoting"
        assert result["confidence"] == 0.85

    def test_pattern2_proposal_without_code_fence(self):
        """[PROPOSAL] {...} [/PROPOSAL]"""
        content = """[PROPOSAL]
{"proposal_type": "pricing_rule", "summary": "Base rate increase", "confidence": 0.9}
[/PROPOSAL]"""

        service = self._make_service()
        result = service._extract_proposal_from_response(content)
        assert result is not None
        assert result["proposal_type"] == "pricing_rule"

    def test_pattern3_bare_json_with_proposal_type(self):
        """Fallback: bare ```json block with proposal_type key."""
        content = """I've prepared the proposal:

```json
{
  "proposal_type": "qualification_rule",
  "summary": "Require site address before quote",
  "reasoning": "Location affects pricing",
  "confidence": 0.8,
  "affected_area": "qualification",
  "rule_type": "required_information",
  "rule_name": "Site Address Required",
  "rule_data": {"required_fields": ["site_address"]}
}
```

Shall I proceed?"""

        service = self._make_service()
        result = service._extract_proposal_from_response(content)
        assert result is not None
        assert result["proposal_type"] == "qualification_rule"
        assert result["summary"] == "Require site address before quote"

    def test_no_proposal_returns_none(self):
        content = "I understand your requirements. Let me confirm before proceeding."
        service = self._make_service()
        result = service._extract_proposal_from_response(content)
        assert result is None

    def test_json_without_proposal_type_returns_none(self):
        """JSON block without proposal_type should not be extracted."""
        content = """```json
{"summary": "Some data", "confidence": 0.5}
```"""
        service = self._make_service()
        result = service._extract_proposal_from_response(content)
        assert result is None

    def test_malformed_json_returns_none(self):
        content = """[PROPOSAL]
{invalid json here}
[/PROPOSAL]"""
        service = self._make_service()
        result = service._extract_proposal_from_response(content)
        assert result is None


# ---------------------------------------------------------------------------
# _clean_proposal_from_text
# ---------------------------------------------------------------------------


class TestCleanProposalFromText:
    """Test removal of proposal blocks from display text."""

    def _make_service(self) -> BrainConversationService:
        mock_session = MagicMock()
        mock_ai = MagicMock(spec=AIProvider)
        return BrainConversationService(mock_session, mock_ai)

    def test_cleans_proposal_block_with_fence(self):
        content = "Here is the plan:\n\n[PROPOSAL]\n```json\n{\"proposal_type\": \"x\"}\n```\n[/PROPOSAL]\n\nDone."
        service = self._make_service()
        cleaned = service._clean_proposal_from_text(content)
        assert "[PROPOSAL]" not in cleaned
        assert "Here is the plan:" in cleaned
        assert "Done." in cleaned

    def test_preserves_non_proposal_text(self):
        content = "Just a normal response with no proposal."
        service = self._make_service()
        cleaned = service._clean_proposal_from_text(content)
        assert cleaned == content


# ---------------------------------------------------------------------------
# End-to-end: directive injection triggers proposal
# ---------------------------------------------------------------------------


class TestDirectiveInjection:
    """Test that explicit proposal requests inject the directive override."""

    def _make_service_with_mock_ai(
        self, ai_response_content: str
    ) -> BrainConversationService:
        """Create a service with a mock AI provider that returns fixed content."""
        mock_session = MagicMock()
        mock_ai = MagicMock(spec=AIProvider)
        mock_response = AIResponse(
            content=ai_response_content,
            model="test-model",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
        )
        mock_ai.chat = AsyncMock(return_value=mock_response)
        mock_ai.complete = AsyncMock(return_value=mock_response)
        mock_ai.provider_name = "test"

        # Mock repositories
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = BrainConversationService(mock_session, mock_ai)
        return service

    @pytest.mark.asyncio
    async def test_explicit_request_injects_directive(self):
        """When the owner explicitly requests a proposal, a directive is appended."""
        proposal_json = json.dumps({
            "proposal_type": "qualification_rule",
            "summary": "Test rule",
            "reasoning": "Test reasoning",
            "confidence": 0.8,
            "affected_area": "qualification",
            "rule_type": "required_information",
            "rule_name": "Test Rule",
            "rule_data": {"fields": ["name"]},
        })
        ai_content = f"[PROPOSAL]\n```json\n{proposal_json}\n```\n[/PROPOSAL]"

        service = self._make_service_with_mock_ai(ai_content)

        # Use GroqProvider isinstance check path — mock it
        from app.adapters.ai.groq import GroqProvider
        service.ai_provider = MagicMock(spec=GroqProvider)
        service.ai_provider.chat = AsyncMock(
            return_value=AIResponse(
                content=ai_content,
                model="test-model",
                usage={"prompt_tokens": 0, "completion_tokens": 0},
            )
        )
        service.ai_provider.provider_name = "groq"

        owner_message = "Create a formal Qualification Rule proposal now."
        system_prompt = "You are the Brain."
        chat_messages = [{"role": "user", "content": owner_message}]

        display_text, proposal_data = await service._ai_response_with_proposal(
            system_prompt, chat_messages, owner_message
        )

        # Verify the directive was injected
        call_args = service.ai_provider.chat.call_args
        messages_sent = call_args[0][0]  # first positional arg
        assert len(messages_sent) == 2  # original + directive
        assert "IMPORTANT" in messages_sent[1]["content"]
        assert "Do NOT ask for confirmation" in messages_sent[1]["content"]

        # Verify proposal was extracted
        assert proposal_data is not None
        assert proposal_data["proposal_type"] == "qualification_rule"

    @pytest.mark.asyncio
    async def test_casual_message_no_directive(self):
        """Normal conversation messages should NOT get the directive."""
        service = self._make_service_with_mock_ai("Sure, tell me more.")

        from app.adapters.ai.groq import GroqProvider
        service.ai_provider = MagicMock(spec=GroqProvider)
        service.ai_provider.chat = AsyncMock(
            return_value=AIResponse(
                content="Sure, tell me more.",
                model="test-model",
                usage={"prompt_tokens": 0, "completion_tokens": 0},
            )
        )
        service.ai_provider.provider_name = "groq"

        owner_message = "What services can I improve?"
        chat_messages = [{"role": "user", "content": owner_message}]

        await service._ai_response_with_proposal("system", chat_messages, owner_message)

        call_args = service.ai_provider.chat.call_args
        messages_sent = call_args[0][0]
        assert len(messages_sent) == 1  # No directive appended

    @pytest.mark.asyncio
    async def test_bare_json_fallback_extracts_proposal(self):
        """When AI returns JSON without [PROPOSAL] markers, fallback extracts it."""
        proposal_json = json.dumps({
            "proposal_type": "qualification_rule",
            "summary": "Require budget range",
            "confidence": 0.75,
        })
        # AI response with bare JSON block (no [PROPOSAL] markers)
        ai_content = f"Here's the proposal:\n\n```json\n{proposal_json}\n```\n\nLet me know."

        service = self._make_service_with_mock_ai(ai_content)

        from app.adapters.ai.groq import GroqProvider
        service.ai_provider = MagicMock(spec=GroqProvider)
        service.ai_provider.chat = AsyncMock(
            return_value=AIResponse(
                content=ai_content,
                model="test-model",
                usage={"prompt_tokens": 0, "completion_tokens": 0},
            )
        )
        service.ai_provider.provider_name = "groq"

        owner_message = "Create a proposal for qualification."
        chat_messages = [{"role": "user", "content": owner_message}]

        display_text, proposal_data = await service._ai_response_with_proposal(
            "system", chat_messages, owner_message
        )

        # Fallback pattern should extract the proposal
        assert proposal_data is not None
        assert proposal_data["proposal_type"] == "qualification_rule"
        assert proposal_data["summary"] == "Require budget range"


# ---------------------------------------------------------------------------
# Empty display text fallback
# ---------------------------------------------------------------------------


class TestEmptyDisplayTextFallback:
    """When the AI response is entirely a [PROPOSAL] block, show a fallback."""

    @pytest.mark.asyncio
    async def test_empty_display_gets_fallback_text(self):
        """If the AI response is only a [PROPOSAL] block, display_text should
        contain a meaningful fallback message."""
        proposal_json = json.dumps({
            "proposal_type": "qualification_rule",
            "summary": "Require site address",
            "confidence": 0.8,
        })
        # AI response is ONLY the [PROPOSAL] block — nothing else
        ai_content = f"[PROPOSAL]\n```json\n{proposal_json}\n```\n[/PROPOSAL]"

        mock_session = MagicMock()
        from app.adapters.ai.groq import GroqProvider
        service = BrainConversationService(mock_session, MagicMock(spec=AIProvider))
        service.ai_provider = MagicMock(spec=GroqProvider)
        service.ai_provider.chat = AsyncMock(
            return_value=AIResponse(
                content=ai_content,
                model="test-model",
                usage={"prompt_tokens": 0, "completion_tokens": 0},
            )
        )
        service.ai_provider.provider_name = "groq"

        owner_message = "Create a proposal."
        chat_messages = [{"role": "user", "content": owner_message}]

        display_text, proposal_data = await service._ai_response_with_proposal(
            "system", chat_messages, owner_message
        )

        # display_text should NOT be empty
        assert display_text.strip() != ""
        assert "proposal" in display_text.lower()
        assert "Require site address" in display_text

    @pytest.mark.asyncio
    async def test_nonempty_display_preserved(self):
        """If the AI response has text outside the [PROPOSAL] block, that text
        should be preserved as-is."""
        proposal_json = json.dumps({
            "proposal_type": "pricing_rule",
            "summary": "Base rate",
            "confidence": 0.7,
        })
        ai_content = (
            f"Here's what I suggest:\n\n"
            f"[PROPOSAL]\n```json\n{proposal_json}\n```\n[/PROPOSAL]\n\n"
            f"Let me know if this works."
        )

        mock_session = MagicMock()
        from app.adapters.ai.groq import GroqProvider
        service = BrainConversationService(mock_session, MagicMock(spec=AIProvider))
        service.ai_provider = MagicMock(spec=GroqProvider)
        service.ai_provider.chat = AsyncMock(
            return_value=AIResponse(
                content=ai_content,
                model="test-model",
                usage={"prompt_tokens": 0, "completion_tokens": 0},
            )
        )
        service.ai_provider.provider_name = "groq"

        display_text, proposal_data = await service._ai_response_with_proposal(
            "system",
            [{"role": "user", "content": "Propose pricing"}],
            "Propose pricing",
        )

        assert "Here's what I suggest:" in display_text
        assert "Let me know if this works." in display_text
        assert "[PROPOSAL]" not in display_text


# ---------------------------------------------------------------------------
# Fix 1: Nested JSON stripping from display text
# ---------------------------------------------------------------------------


class TestNestedJsonStripping:
    """The AI often returns nested JSON inside [PROPOSAL] blocks.
    The old regex \\{.*?\\} only matched one level of braces, leaving
    raw JSON visible in the conversation. The fix matches on markers."""

    def _make_service(self) -> BrainConversationService:
        mock_session = MagicMock()
        mock_ai = MagicMock(spec=AIProvider)
        return BrainConversationService(mock_session, mock_ai)

    def test_nested_json_fully_stripped(self):
        """A [PROPOSAL] block containing nested JSON objects must be fully removed."""
        content = (
            "I've prepared the proposal.\n\n"
            "[PROPOSAL]\n"
            "```json\n"
            "{\n"
            '  "proposal_type": "qualification_rule",\n'
            '  "rule_data": {\n'
            '    "required_fields": ["desired_outcome", "timeline"],\n'
            '    "nested": { "deep": { "value": 1 } }\n'
            "  }\n"
            "}\n"
            "```\n"
            "[/PROPOSAL]\n"
        )
        service = self._make_service()
        cleaned = service._clean_proposal_from_text(content)
        assert "[PROPOSAL]" not in cleaned
        assert "[/PROPOSAL]" not in cleaned
        assert "proposal_type" not in cleaned
        assert "rule_data" not in cleaned
        assert "required_fields" not in cleaned
        assert "I've prepared the proposal." in cleaned

    def test_bare_json_block_outside_proposal_stripped(self):
        """Defence in depth: bare ```json blocks outside [PROPOSAL] are also stripped."""
        content = (
            "Here is my response.\n\n"
            "```json\n"
            '{"proposal_type": "pricing_rule", "confidence": 0.9}\n'
            "```\n"
            "\nEnd of message."
        )
        service = self._make_service()
        cleaned = service._clean_proposal_from_text(content)
        assert "proposal_type" not in cleaned
        assert "Here is my response." in cleaned
        assert "End of message." in cleaned

    def test_orphan_proposal_marker_stripped(self):
        """AI sometimes emits [PROPOSAL] without the closing marker or JSON."""
        content = "[PROPOSAL]"
        service = self._make_service()
        cleaned = service._clean_proposal_from_text(content)
        assert cleaned == ""

    def test_orphan_closing_proposal_marker_stripped(self):
        content = "Some text [/PROPOSAL] more text"
        service = self._make_service()
        cleaned = service._clean_proposal_from_text(content)
        assert "[/PROPOSAL]" not in cleaned
        assert "Some text" in cleaned
        assert "more text" in cleaned


# ---------------------------------------------------------------------------
# Fix 2: System prompt contains qualification constraint
# ---------------------------------------------------------------------------


class TestQualificationConstraintInPrompt:
    """Verify the system prompt constrains qualification rules to established fields."""

    def test_system_prompt_contains_qualification_constraint(self):
        from app.domain.business.conversation_service import BRAIN_SYSTEM_PROMPT

        assert "QUALIFICATION RULE CONSTRAINT" in BRAIN_SYSTEM_PROMPT
        assert "FORBIDDEN" in BRAIN_SYSTEM_PROMPT
        assert "company_name" in BRAIN_SYSTEM_PROMPT
        assert "desired_outcome" in BRAIN_SYSTEM_PROMPT
        assert "main_problem" in BRAIN_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_directive_includes_field_constraint(self):
        """The injected directive for explicit proposal requests must include
        the default fields and the forbidden list."""
        mock_session = MagicMock()
        from app.adapters.ai.groq import GroqProvider
        service = BrainConversationService(mock_session, MagicMock(spec=AIProvider))
        service.ai_provider = MagicMock(spec=GroqProvider)
        service.ai_provider.chat = AsyncMock(
            return_value=AIResponse(
                content="OK",
                model="test",
                usage={"prompt_tokens": 0, "completion_tokens": 0},
            )
        )
        service.ai_provider.provider_name = "groq"

        await service._ai_response_with_proposal(
            "system",
            [{"role": "user", "content": "Create a proposal."}],
            "Create a proposal.",
        )

        call_args = service.ai_provider.chat.call_args
        messages_sent = call_args[0][0]
        directive = messages_sent[-1]["content"]
        assert "desired_outcome" in directive
        assert "main_problem" in directive
        assert "Do NOT leave" in directive
        assert "company_name" in directive


# ---------------------------------------------------------------------------
# Fix 2 (post-processing): _sanitize_proposal_data
# ---------------------------------------------------------------------------


class TestSanitizeProposalData:
    """Deterministic post-processing of qualification_rule proposals.

    The AI model cannot be trusted to honour field constraints via prompts
    alone.  ``_sanitize_proposal_data`` enforces the rules in code:
    - Strip forbidden fields from required_fields.
    - If required_fields is empty after stripping (or was empty to begin
      with), inject the default consulting fields.
    """

    def test_non_qualification_proposal_unchanged(self):
        """Pricing, policy, and other proposal types pass through untouched."""
        data = {
            "proposal_type": "pricing_rule",
            "rule_data": {"base_rate": 150, "currency": "ZAR"},
        }
        result = BrainConversationService._sanitize_proposal_data(data)
        assert result is data  # same object, not modified

    def test_empty_required_fields_gets_defaults(self):
        """When the AI returns required_fields=[], defaults are injected."""
        data = {
            "proposal_type": "qualification_rule",
            "rule_data": {"required_fields": []},
        }
        result = BrainConversationService._sanitize_proposal_data(data)
        fields = result["rule_data"]["required_fields"]
        assert len(fields) == 5
        assert "desired_outcome" in fields
        assert "main_problem" in fields
        assert "expected_deliverables" in fields
        assert "desired_timeline" in fields
        assert "important_constraints" in fields

    def test_missing_required_fields_gets_defaults(self):
        """When rule_data has no required_fields key at all."""
        data = {
            "proposal_type": "qualification_rule",
            "rule_data": {"some_other_key": "value"},
        }
        result = BrainConversationService._sanitize_proposal_data(data)
        fields = result["rule_data"]["required_fields"]
        assert len(fields) == 5
        assert "desired_outcome" in fields

    def test_forbidden_fields_stripped(self):
        """AI-invented forbidden fields are removed."""
        data = {
            "proposal_type": "qualification_rule",
            "rule_data": {
                "required_fields": [
                    "desired_outcome",
                    "company_name",
                    "email",
                    "phone",
                    "budget",
                    "service_agreement",
                    "main_problem",
                ]
            },
        }
        result = BrainConversationService._sanitize_proposal_data(data)
        fields = result["rule_data"]["required_fields"]
        assert "desired_outcome" in fields
        assert "main_problem" in fields
        assert "company_name" not in fields
        assert "email" not in fields
        assert "phone" not in fields
        assert "budget" not in fields
        assert "service_agreement" not in fields

    def test_all_forbidden_fields_replaced_with_defaults(self):
        """If ALL fields are forbidden, defaults are injected."""
        data = {
            "proposal_type": "qualification_rule",
            "rule_data": {
                "required_fields": [
                    "company_name",
                    "contact_name",
                    "email",
                    "phone",
                    "budget",
                ]
            },
        }
        result = BrainConversationService._sanitize_proposal_data(data)
        fields = result["rule_data"]["required_fields"]
        assert len(fields) == 5
        assert "desired_outcome" in fields
        assert "company_name" not in fields

    def test_valid_fields_preserved(self):
        """Owner-established fields that aren't forbidden pass through."""
        data = {
            "proposal_type": "qualification_rule",
            "rule_data": {
                "required_fields": [
                    "desired_outcome",
                    "main_problem",
                    "expected_deliverables",
                    "desired_timeline",
                    "important_constraints",
                ]
            },
        }
        result = BrainConversationService._sanitize_proposal_data(data)
        fields = result["rule_data"]["required_fields"]
        assert len(fields) == 5
        assert "desired_outcome" in fields
        assert "important_constraints" in fields

    def test_no_rule_data_passes_through(self):
        """Qualification proposal without rule_data is not modified."""
        data = {
            "proposal_type": "qualification_rule",
            "summary": "Some rule",
        }
        result = BrainConversationService._sanitize_proposal_data(data)
        assert "rule_data" not in result

    def test_rule_data_not_dict_passes_through(self):
        """If rule_data is not a dict (edge case), don't crash."""
        data = {
            "proposal_type": "qualification_rule",
            "rule_data": "not a dict",
        }
        result = BrainConversationService._sanitize_proposal_data(data)
        assert result["rule_data"] == "not a dict"


# ---------------------------------------------------------------------------
# Integration: _ai_response_with_proposal applies sanitization
# ---------------------------------------------------------------------------


class TestProposalSanitizationIntegration:
    """End-to-end: AI returns bad data → sanitization fixes it."""

    @pytest.mark.asyncio
    async def test_ai_returns_forbidden_fields_they_get_stripped(self):
        """AI returns forbidden fields in required_fields; post-processing
        strips them and injects defaults."""
        proposal_json = json.dumps({
            "proposal_type": "qualification_rule",
            "summary": "Client intake fields",
            "confidence": 0.8,
            "rule_type": "required_information",
            "rule_name": "Client Intake",
            "rule_data": {
                "required_fields": [
                    "company_name",
                    "contact_name",
                    "email",
                    "phone",
                    "budget",
                    "desired_start_date",
                    "service_agreement",
                ]
            },
        })
        ai_content = f"[PROPOSAL]\n```json\n{proposal_json}\n```\n[/PROPOSAL]"

        mock_session = MagicMock()
        from app.adapters.ai.groq import GroqProvider
        service = BrainConversationService(mock_session, MagicMock(spec=AIProvider))
        service.ai_provider = MagicMock(spec=GroqProvider)
        service.ai_provider.chat = AsyncMock(
            return_value=AIResponse(
                content=ai_content,
                model="test-model",
                usage={"prompt_tokens": 0, "completion_tokens": 0},
            )
        )
        service.ai_provider.provider_name = "groq"

        _, proposal_data = await service._ai_response_with_proposal(
            "system",
            [{"role": "user", "content": "Create a proposal."}],
            "Create a proposal.",
        )

        assert proposal_data is not None
        fields = proposal_data["rule_data"]["required_fields"]
        # Forbidden fields must be gone
        assert "company_name" not in fields
        assert "email" not in fields
        assert "phone" not in fields
        assert "budget" not in fields
        assert "service_agreement" not in fields
        assert "contact_name" not in fields
        # Defaults must be present
        assert "desired_outcome" in fields
        assert "main_problem" in fields
        assert "expected_deliverables" in fields
        assert "desired_timeline" in fields
        assert "important_constraints" in fields

    @pytest.mark.asyncio
    async def test_ai_returns_empty_fields_defaults_injected(self):
        """AI returns empty required_fields; defaults are injected."""
        proposal_json = json.dumps({
            "proposal_type": "qualification_rule",
            "summary": "Qualification rule",
            "confidence": 0.7,
            "rule_data": {"required_fields": []},
        })
        ai_content = f"[PROPOSAL]\n```json\n{proposal_json}\n```\n[/PROPOSAL]"

        mock_session = MagicMock()
        from app.adapters.ai.groq import GroqProvider
        service = BrainConversationService(mock_session, MagicMock(spec=AIProvider))
        service.ai_provider = MagicMock(spec=GroqProvider)
        service.ai_provider.chat = AsyncMock(
            return_value=AIResponse(
                content=ai_content,
                model="test-model",
                usage={"prompt_tokens": 0, "completion_tokens": 0},
            )
        )
        service.ai_provider.provider_name = "groq"

        _, proposal_data = await service._ai_response_with_proposal(
            "system",
            [{"role": "user", "content": "Create a proposal."}],
            "Create a proposal.",
        )

        assert proposal_data is not None
        fields = proposal_data["rule_data"]["required_fields"]
        assert len(fields) == 5
        assert "desired_outcome" in fields
        assert "main_problem" in fields

    @pytest.mark.asyncio
    async def test_non_qualification_proposal_not_sanitized(self):
        """Pricing proposals pass through sanitization unchanged."""
        proposal_json = json.dumps({
            "proposal_type": "pricing_rule",
            "summary": "Base rate",
            "confidence": 0.9,
            "rule_data": {"base_rate": 150, "currency": "ZAR"},
        })
        ai_content = f"[PROPOSAL]\n```json\n{proposal_json}\n```\n[/PROPOSAL]"

        mock_session = MagicMock()
        from app.adapters.ai.groq import GroqProvider
        service = BrainConversationService(mock_session, MagicMock(spec=AIProvider))
        service.ai_provider = MagicMock(spec=GroqProvider)
        service.ai_provider.chat = AsyncMock(
            return_value=AIResponse(
                content=ai_content,
                model="test-model",
                usage={"prompt_tokens": 0, "completion_tokens": 0},
            )
        )
        service.ai_provider.provider_name = "groq"

        _, proposal_data = await service._ai_response_with_proposal(
            "system",
            [{"role": "user", "content": "Propose pricing"}],
            "Propose pricing",
        )

        assert proposal_data is not None
        assert proposal_data["proposal_type"] == "pricing_rule"
        assert proposal_data["rule_data"]["base_rate"] == 150
