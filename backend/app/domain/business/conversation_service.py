"""Business Brain Interactive Co-Brain service.

Contains business logic for Brain conversations with the business owner.
The Brain uses AI (Groq) to:
- Learn about the business through conversation
- Identify missing business knowledge
- Propose structured business rules
- Remember approved knowledge
- Connect approved proposals to governed Brain state

AI remains proposal-only. All proposals require explicit owner approval
before becoming governed Brain state through the existing version/rule system.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.ai.base import AIProvider
from app.domain.business.models import (
    BrainConversation,
    BrainMessage,
    BrainProposal,
    BrainVersion,
    BusinessBrain,
    BusinessRule,
)
from app.domain.business.registry import (
    ConfigCategory,
    is_known_rule_type,
)
from app.domain.business.repository import (
    BrainConversationRepository,
    BrainMessageRepository,
    BrainProposalRepository,
    BrainVersionRepository,
    BusinessBrainRepository,
    BusinessRuleRepository,
)
from app.domain.business.service import BrainService, BusinessRuleService
from app.domain.common.enums import (
    BrainConversationStatus,
    BrainMessageRole,
    BrainProposalStatus,
    BrainProposalType,
    BrainVersionStatus,
)
from app.exceptions import DomainError, NotFoundError
from app.logging import get_logger

logger = get_logger(__name__)

# Mapping from proposal type to Brain config area and rule type
_PROPOSAL_TYPE_TO_RULE: dict[BrainProposalType, tuple[str, str | None]] = {
    BrainProposalType.NEW_SERVICE: ("services_config", "service_definition"),
    BrainProposalType.PRICING_RULE: ("pricing_config", None),  # rule_type from data
    BrainProposalType.POLICY_RULE: ("policies_config", None),
    BrainProposalType.AVAILABILITY_RULE: ("availability_config", None),
    BrainProposalType.QUALIFICATION_RULE: ("qualification_config", None),
    BrainProposalType.ESCALATION_RULE: ("escalation_config", None),
    BrainProposalType.IDENTITY_UPDATE: ("identity_config", None),
    BrainProposalType.COMMUNICATION_UPDATE: ("communication_config", None),
    BrainProposalType.GENERAL_KNOWLEDGE: (None, None),
}

# System prompt for Brain conversation
BRAIN_SYSTEM_PROMPT = """You are the Business Brain — an interactive operational intelligence for a business owner.

You help the owner configure and operate their business by:
1. Learning about the business through natural conversation
2. Identifying missing business knowledge needed for operations
3. Proposing structured business rules when the owner provides information
4. Recalling and summarizing what the business already knows

CRITICAL CONSTRAINTS:
- You PROPOSE changes — the owner APPROVES them. You never change anything directly.
- Always confirm understanding before proposing a rule change.
- Distinguish between KNOWN (confirmed), PROPOSED (awaiting approval), and UNKNOWN.
- Be concise and practical. No filler.

PROPOSAL FORMAT:
When the owner provides information that should become a business rule, output a proposal block:

[PROPOSAL]
```json
{
  "proposal_type": "pricing_rule|policy_rule|availability_rule|qualification_rule|new_service|identity_update|communication_update|escalation_rule",
  "summary": "One-line description of the change",
  "reasoning": "Why this matters for the business",
  "confidence": 0.0-1.0,
  "affected_area": "pricing|policies|availability|qualification|services|identity|communication|escalation",
  "rule_type": "surcharge|base_pricing|operating_hours|cancellation_policy|service_definition|etc (use the correct registry type)",
  "rule_name": "Human-readable rule name",
  "rule_data": { ... structured data matching the rule type schema ... }
}
```
[/PROPOSAL]

RULE TYPE REFERENCE (use the correct rule_type for proposals):
- Services: service_definition, service_bundling, service_exclusion
- Pricing: base_pricing, surcharge, discount, price_floor, price_cap, payment_terms
- Availability: operating_hours, minimum_notice, maximum_advance, capacity_limit, blackout_period
- Qualification: required_information, document_requirement, eligibility_check
- Policies: cancellation_policy, refund_policy, deposit_rules, booking_creation, terms_of_service
- Communication: response_time, channel_preference, auto_response
- Escalation: value_threshold, complexity_trigger, customer_request

For config-only changes (identity, general settings), use the proposal_type without rule_type.

BUSINESS CONTEXT:
{business_context}

ACTIVE BRAIN CONFIGURATION:
{active_config}

APPROVED KNOWLEDGE (from previous conversations):
{approved_knowledge}

PENDING PROPOSALS (awaiting owner decision):
{pending_proposals}

MISSING INFORMATION (needed for operations):
{missing_info}"""

# Schema for structured proposal extraction
PROPOSAL_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "has_proposal": {"type": "boolean"},
        "response_text": {"type": "string"},
        "proposal": {
            "type": "object",
            "properties": {
                "proposal_type": {"type": "string"},
                "summary": {"type": "string"},
                "reasoning": {"type": "string"},
                "confidence": {"type": "number"},
                "affected_area": {"type": "string"},
                "rule_type": {"type": "string"},
                "rule_name": {"type": "string"},
                "rule_data": {"type": "object"},
            },
        },
    },
    "required": ["has_proposal", "response_text"],
}


class BrainConversationService:
    """Business Brain interactive conversation management.

    Handles the conversational interface between the Brain and the
    business owner. AI interprets owner input and generates proposals,
    but all changes require explicit approval before entering the
    governed Brain version/rule system.
    """

    def __init__(self, session: AsyncSession, ai_provider: AIProvider) -> None:
        self.session = session
        self.ai_provider = ai_provider
        self.brain_repo = BusinessBrainRepository(session)
        self.conversation_repo = BrainConversationRepository(session)
        self.message_repo = BrainMessageRepository(session)
        self.proposal_repo = BrainProposalRepository(session)
        self.version_repo = BrainVersionRepository(session)
        self.rule_repo = BusinessRuleRepository(session)

    # ------------------------------------------------------------------
    # Conversation management
    # ------------------------------------------------------------------

    async def get_or_create_active_conversation(
        self, brain_id: uuid.UUID, business_id: uuid.UUID
    ) -> BrainConversation:
        """Get the active conversation for a brain, creating one if needed."""
        conversation = await self.conversation_repo.get_active_by_brain_id(brain_id)
        if conversation is not None:
            return conversation

        conversation = BrainConversation(
            brain_id=brain_id,
            business_id=business_id,
            status=BrainConversationStatus.ACTIVE,
            title="Brain Session",
        )
        conversation = await self.conversation_repo.create(conversation)

        # Generate initial Brain greeting based on real state
        greeting = await self._generate_initial_greeting(brain_id, business_id)
        await self.message_repo.create(
            BrainMessage(
                conversation_id=conversation.id,
                role=BrainMessageRole.BRAIN,
                content=greeting,
                metadata_={"type": "greeting"},
            )
        )

        return conversation

    async def send_owner_message(
        self,
        conversation_id: uuid.UUID,
        content: str,
    ) -> tuple[BrainMessage, BrainMessage]:
        """Process an owner message and generate a Brain response.

        Returns:
            Tuple of (owner_message, brain_response)
        """
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if conversation is None:
            raise NotFoundError(f"Conversation {conversation_id} not found")

        if conversation.status != BrainConversationStatus.ACTIVE:
            raise DomainError("Cannot send messages to an archived conversation")

        # Save owner message
        owner_message = await self.message_repo.create(
            BrainMessage(
                conversation_id=conversation_id,
                role=BrainMessageRole.OWNER,
                content=content,
            )
        )

        # Generate Brain response with proposal extraction
        brain_response_content, proposal_data = await self._generate_brain_response(
            conversation, content
        )

        brain_message = await self.message_repo.create(
            BrainMessage(
                conversation_id=conversation_id,
                role=BrainMessageRole.BRAIN,
                content=brain_response_content,
                metadata_={
                    "has_proposal": proposal_data is not None,
                    "proposal_type": proposal_data.get("proposal_type") if proposal_data else None,
                },
            )
        )

        # Create proposal if Brain identified one
        if proposal_data is not None:
            await self._create_proposal_from_conversation(
                conversation=conversation,
                source_message=owner_message,
                proposal_data=proposal_data,
            )

        return owner_message, brain_message

    async def list_messages(
        self, conversation_id: uuid.UUID, limit: int = 100
    ) -> list[BrainMessage]:
        return await self.message_repo.list_by_conversation_id(
            conversation_id, limit=limit
        )

    async def list_conversations(
        self, brain_id: uuid.UUID, limit: int = 20
    ) -> list[BrainConversation]:
        return await self.conversation_repo.list_by_brain_id(brain_id, limit=limit)

    async def archive_conversation(
        self, conversation_id: uuid.UUID
    ) -> BrainConversation:
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if conversation is None:
            raise NotFoundError(f"Conversation {conversation_id} not found")
        conversation.status = BrainConversationStatus.ARCHIVED
        return await self.conversation_repo.update(conversation)

    # ------------------------------------------------------------------
    # Proposal management + governance connection
    # ------------------------------------------------------------------

    async def list_proposals(
        self, brain_id: uuid.UUID, limit: int = 50
    ) -> list[BrainProposal]:
        return await self.proposal_repo.list_by_brain_id(brain_id, limit=limit)

    async def list_pending_proposals(
        self, brain_id: uuid.UUID
    ) -> list[BrainProposal]:
        return await self.proposal_repo.list_pending_by_brain_id(brain_id)

    async def approve_proposal(
        self,
        proposal_id: uuid.UUID,
        edited_change: dict | None = None,
    ) -> BrainProposal:
        """Approve a proposal and apply it to the governed Brain state.

        If edited_change is provided, the proposal is approved with edits.
        The approved change is applied to a DRAFT BrainVersion as either
        a config update or a new BusinessRule, using the existing governance.
        """
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            raise NotFoundError(f"Proposal {proposal_id} not found")

        if proposal.status != BrainProposalStatus.PENDING:
            raise DomainError(
                f"Cannot approve proposal in status {proposal.status}"
            )

        # Apply edits if provided
        final_change = edited_change if edited_change is not None else proposal.proposed_change
        if edited_change is not None:
            proposal.proposed_change = final_change
            proposal.status = BrainProposalStatus.EDITED
        else:
            proposal.status = BrainProposalStatus.APPROVED

        proposal.resolved_at = datetime.now(UTC)
        proposal = await self.proposal_repo.update(proposal)

        # Apply the approved change to governed Brain state
        try:
            await self._apply_proposal_to_brain(proposal, final_change)
            proposal.status = BrainProposalStatus.APPLIED
            proposal = await self.proposal_repo.update(proposal)
        except Exception as e:
            logger.error(
                "Failed to apply approved proposal to Brain",
                proposal_id=str(proposal_id),
                error=str(e),
            )
            # Proposal stays APPROVED but not APPLIED — owner can retry

        return proposal

    async def reject_proposal(self, proposal_id: uuid.UUID) -> BrainProposal:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            raise NotFoundError(f"Proposal {proposal_id} not found")

        if proposal.status != BrainProposalStatus.PENDING:
            raise DomainError(
                f"Cannot reject proposal in status {proposal.status}"
            )

        proposal.status = BrainProposalStatus.REJECTED
        proposal.resolved_at = datetime.now(UTC)
        return await self.proposal_repo.update(proposal)

    # ------------------------------------------------------------------
    # Brain knowledge & attention
    # ------------------------------------------------------------------

    async def get_brain_knowledge_summary(
        self, brain_id: uuid.UUID, business_id: uuid.UUID
    ) -> dict[str, Any]:
        """Return a comprehensive summary of Brain knowledge state.

        Includes: known (approved), proposed (pending), uncertain,
        missing information, and active Brain configuration.
        """
        brain = await self.brain_repo.get_by_business_id(business_id)
        all_proposals = await self.proposal_repo.list_by_brain_id(brain_id, limit=100)

        known = []
        proposed = []
        rejected = []

        for p in all_proposals:
            entry = {
                "id": str(p.id),
                "type": p.proposal_type,
                "summary": p.proposed_change.get("summary", ""),
                "affected_area": p.affected_area,
                "confidence": p.confidence,
                "created_at": p.created_at.isoformat(),
            }
            if p.status in (
                BrainProposalStatus.APPROVED,
                BrainProposalStatus.EDITED,
                BrainProposalStatus.APPLIED,
            ):
                known.append(entry)
            elif p.status == BrainProposalStatus.PENDING:
                proposed.append(entry)
            elif p.status == BrainProposalStatus.REJECTED:
                rejected.append(entry)

        # Determine what's configured in the active Brain version
        active_config_areas = []
        missing_areas = []
        if brain and brain.active_version_id:
            version = await self.version_repo.get_by_id(brain.active_version_id)
            if version:
                config_map = {
                    "identity": version.identity_config,
                    "services": version.services_config,
                    "pricing": version.pricing_config,
                    "availability": version.availability_config,
                    "qualification": version.qualification_config,
                    "policies": version.policies_config,
                    "escalation": version.escalation_config,
                    "communication": version.communication_config,
                }
                for area, config in config_map.items():
                    if config and len(config) > 0:
                        active_config_areas.append(area)
                    else:
                        missing_areas.append(area)
        else:
            missing_areas = [
                "identity", "services", "pricing", "availability",
                "qualification", "policies", "escalation", "communication",
            ]

        return {
            "known": known,
            "proposed": proposed,
            "rejected": rejected,
            "active_config_areas": active_config_areas,
            "missing_areas": missing_areas,
            "has_active_version": brain is not None and brain.active_version_id is not None,
        }

    async def get_needs_attention(self, brain_id: uuid.UUID) -> list[dict[str, Any]]:
        """Return real items requiring owner attention.

        Sources:
        - Pending proposals
        - Missing critical configuration areas
        - Operational events needing action (enquiries, quotes, bookings, invoices)
        """
        items: list[dict[str, Any]] = []

        # 1. Pending proposals
        pending = await self.proposal_repo.list_pending_by_brain_id(brain_id)
        for p in pending:
            items.append({
                "type": "pending_proposal",
                "id": str(p.id),
                "title": f"Proposal: {p.proposed_change.get('summary', p.proposal_type)}",
                "proposal_type": p.proposal_type,
                "is_urgent": p.is_urgent,
                "confidence": p.confidence,
            })

        # 2. Missing critical areas (services and pricing are critical)
        brain = await self.brain_repo.get_by_id(brain_id)

        if brain and brain.active_version_id:
            version = await self.version_repo.get_by_id(brain.active_version_id)
            if version:
                critical_missing = []
                if not version.services_config:
                    critical_missing.append("services")
                if not version.pricing_config:
                    critical_missing.append("pricing")
                if not version.availability_config:
                    critical_missing.append("availability")

                for area in critical_missing:
                    items.append({
                        "type": "missing_configuration",
                        "title": f"Missing {area} configuration",
                        "affected_area": area,
                        "is_urgent": area in ("services", "pricing"),
                    })
        elif brain is None or not brain.active_version_id:
            items.append({
                "type": "no_active_version",
                "title": "No active Brain version — business rules are not governing transactions",
                "affected_area": "all",
                "is_urgent": True,
            })

        # 3. Operational events needing business action
        await self._add_operational_attention_items(items, brain)

        return items

    async def _add_operational_attention_items(
        self, items: list[dict[str, Any]], brain: BusinessBrain | None
    ) -> None:
        """Add operational events that need business attention."""
        if not brain:
            return

        # Import repositories for operational queries
        from app.domain.enquiry.repository import EnquiryRepository
        from app.domain.quote.repository import QuoteRepository
        from app.domain.booking.repository import BookingRepository
        from app.domain.invoice.repository import InvoiceRepository

        enquiry_repo = EnquiryRepository(self.session)
        quote_repo = QuoteRepository(self.session)
        booking_repo = BookingRepository(self.session)
        invoice_repo = InvoiceRepository(self.session)

        # New enquiries awaiting business response (received, in_review, needs_information)
        all_enquiries = await enquiry_repo.get_by_business(brain.business_id, limit=20)
        awaiting_enquiries = [
            e for e in all_enquiries
            if e.status in ("received", "in_review", "needs_information")
        ]
        if awaiting_enquiries:
            items.append({
                "type": "new_enquiries",
                "title": f"{len(awaiting_enquiries)} enquiry{'s' if len(awaiting_enquiries) != 1 else ''} awaiting your response",
                "affected_area": "enquiries",
                "is_urgent": True,
                "count": len(awaiting_enquiries),
            })

        # Quotes issued awaiting customer response
        issued_quotes = await quote_repo.get_by_business(brain.business_id, status="issued", limit=10)
        if issued_quotes:
            items.append({
                "type": "pending_quotes",
                "title": f"{len(issued_quotes)} quote{'s' if len(issued_quotes) != 1 else ''} awaiting customer response",
                "affected_area": "quotes",
                "is_urgent": False,
                "count": len(issued_quotes),
            })

        # Bookings needing business action (requested, proposed)
        all_bookings = await booking_repo.get_by_business(brain.business_id, limit=20)
        action_bookings = [
            b for b in all_bookings
            if b.status in ("requested", "proposed")
        ]
        if action_bookings:
            items.append({
                "type": "pending_bookings",
                "title": f"{len(action_bookings)} booking{'s' if len(action_bookings) != 1 else ''} need{'s' if len(action_bookings) == 1 else ''} your action",
                "affected_area": "bookings",
                "is_urgent": True,
                "count": len(action_bookings),
            })

        # Unpaid invoices
        unpaid_invoices = await invoice_repo.get_by_business(
            brain.business_id,
            payment_status="unpaid",
            limit=10,
        )
        if unpaid_invoices:
            items.append({
                "type": "unpaid_invoices",
                "title": f"{len(unpaid_invoices)} unpaid invoice{'s' if len(unpaid_invoices) != 1 else ''}",
                "affected_area": "invoices",
                "is_urgent": False,
                "count": len(unpaid_invoices),
            })

    # ------------------------------------------------------------------
    # Private: Context building
    # ------------------------------------------------------------------

    async def _generate_initial_greeting(
        self, brain_id: uuid.UUID, business_id: uuid.UUID
    ) -> str:
        """Generate context-aware initial greeting."""
        brain = await self.brain_repo.get_by_business_id(business_id)
        has_active = brain is not None and brain.active_version_id is not None

        # Check what's configured
        if has_active and brain.active_version_id:
            version = await self.version_repo.get_by_id(brain.active_version_id)
            if version:
                configured = []
                missing = []
                for area, attr in [
                    ("services", "services_config"),
                    ("pricing", "pricing_config"),
                    ("availability", "availability_config"),
                    ("policies", "policies_config"),
                ]:
                    if getattr(version, attr, None):
                        configured.append(area)
                    else:
                        missing.append(area)

                if missing:
                    return (
                        f"Welcome back. Your Brain is active with {', '.join(configured)} configured.\n\n"
                        f"I still need information about: {', '.join(missing)}.\n\n"
                        "What would you like to set up?"
                    )
                return (
                    "Welcome back. Your business configuration is loaded and active. "
                    "What would you like to discuss or update?"
                )

        return (
            "Let's get your business operational. I know your business name "
            "and basic account info, but I need to understand your services, "
            "pricing, and policies before I can help handle enquiries.\n\n"
            "What services do you offer?"
        )

    async def _generate_brain_response(
        self,
        conversation: BrainConversation,
        owner_message: str,
    ) -> tuple[str, dict | None]:
        """Generate Brain response with structured proposal extraction."""
        # Build comprehensive context
        business_context = await self._build_business_context(
            conversation.business_id
        )
        active_config = await self._build_active_config_text(conversation.brain_id)
        approved_knowledge = await self._build_approved_knowledge_text(
            conversation.brain_id
        )
        pending_text = await self._build_pending_proposals_text(conversation.brain_id)
        missing_text = await self._build_missing_info_text(conversation.brain_id)

        system_prompt = BRAIN_SYSTEM_PROMPT.format(
            business_context=business_context,
            active_config=active_config,
            approved_knowledge=approved_knowledge,
            pending_proposals=pending_text,
            missing_info=missing_text,
        )

        # Build conversation history for multi-turn chat
        history = await self.message_repo.list_by_conversation_id(
            conversation.id, limit=20
        )
        chat_messages = [
            {"role": "assistant" if m.role == "brain" else m.role, "content": m.content}
            for m in history
            if m.role in ("brain", "owner")
        ]
        chat_messages.append({"role": "user", "content": owner_message})

        try:
            # Try structured output first for proposal extraction
            response_text, proposal_data = await self._ai_response_with_proposal(
                system_prompt, chat_messages, owner_message
            )
            return response_text, proposal_data

        except Exception as e:
            logger.error("Brain response generation failed", error=str(e))
            return (
                "I'm having trouble processing that right now. Could you try again?",
                None,
            )

    async def _ai_response_with_proposal(
        self,
        system_prompt: str,
        chat_messages: list[dict[str, str]],
        owner_message: str,
    ) -> tuple[str, dict | None]:
        """Get AI response and extract proposal using structured output."""
        from app.adapters.ai.groq import GroqProvider

        # Build a prompt that asks for both response and potential proposal
        conversation_text = "\n".join(
            f"{'Brain' if m['role'] == 'assistant' else 'Owner'}: {m['content']}"
            for m in chat_messages
        )

        full_prompt = (
            f"Conversation so far:\n{conversation_text}\n\n"
            f"Owner's latest message: \"{owner_message}\"\n\n"
            "Respond to the owner. If their message contains business information "
            "that should become a rule or configuration, include a [PROPOSAL] block "
            "with the structured data. Otherwise, just respond conversationally."
        )

        if isinstance(self.ai_provider, GroqProvider):
            response = await self.ai_provider.chat(
                chat_messages,
                system=system_prompt,
                max_tokens=2048,
                temperature=0.7,
            )
            content = response.content
        else:
            response = await self.ai_provider.complete(
                full_prompt,
                system=system_prompt,
                max_tokens=2048,
                temperature=0.7,
            )
            content = response.content

        # Extract proposal from response
        proposal_data = self._extract_proposal_from_response(content)
        # Clean the response text (remove proposal block for display)
        display_text = self._clean_proposal_from_text(content)

        return display_text, proposal_data

    async def _build_business_context(
        self, business_id: uuid.UUID
    ) -> str:
        """Build real business context from database."""
        from app.domain.identity.repository import BusinessRepository

        biz_repo = BusinessRepository(self.session)
        business = await biz_repo.get_by_id(business_id)
        if not business:
            return "Business not found."

        parts = [
            f"Business: {business.name}",
            f"Currency: {business.currency}",
            f"Status: {business.status}",
        ]

        # Include service offers
        from app.domain.services.repository import ServiceOfferRepository

        offer_repo = ServiceOfferRepository(self.session)
        offers = await offer_repo.get_by_business_id(business_id)
        if offers:
            active_offers = [o for o in offers if o.status == "active"]
            draft_offers = [o for o in offers if o.status == "draft"]
            if active_offers:
                parts.append(
                    f"Active services ({len(active_offers)}): "
                    + ", ".join(o.name for o in active_offers[:10])
                )
            if draft_offers:
                parts.append(
                    f"Draft services ({len(draft_offers)}): "
                    + ", ".join(o.name for o in draft_offers[:5])
                )
        else:
            parts.append("No service offers configured yet.")

        # Include business profile info if available
        if business.profile:
            profile = business.profile
            if profile.description:
                parts.append(f"Description: {profile.description[:200]}")

        # Include recent operational activity
        from app.domain.enquiry.repository import EnquiryRepository
        from app.domain.booking.repository import BookingRepository
        from app.domain.invoice.repository import InvoiceRepository

        enquiry_repo = EnquiryRepository(self.session)
        booking_repo = BookingRepository(self.session)
        invoice_repo = InvoiceRepository(self.session)

        # Recent enquiries
        recent_enquiries = await enquiry_repo.get_by_business(business_id, limit=5)
        if recent_enquiries:
            active_count = sum(1 for e in recent_enquiries if e.status in ("received", "in_review", "needs_information"))
            completed_count = sum(1 for e in recent_enquiries if e.status == "completed")
            parts.append(f"Recent enquiries: {len(recent_enquiries)} total, {active_count} active, {completed_count} completed")

        # Recent bookings
        recent_bookings = await booking_repo.get_by_business(business_id, limit=5)
        if recent_bookings:
            confirmed_count = sum(1 for b in recent_bookings if b.status == "confirmed")
            completed_count = sum(1 for b in recent_bookings if b.status == "completed")
            parts.append(f"Recent bookings: {len(recent_bookings)} total, {confirmed_count} confirmed, {completed_count} completed")

        # Unpaid invoices
        unpaid_invoices = await invoice_repo.get_by_business(business_id, payment_status="unpaid", limit=5)
        if unpaid_invoices:
            total_unpaid = sum(float(inv.total_amount or 0) for inv in unpaid_invoices)
            parts.append(f"Unpaid invoices: {len(unpaid_invoices)} outstanding, total A${total_unpaid:.2f}")

        return "\n".join(parts)

    async def _build_active_config_text(
        self, brain_id: uuid.UUID
    ) -> str:
        """Build text summary of active Brain configuration."""
        version = await self.version_repo.get_active_by_brain_id(brain_id)
        if not version:
            return "No active Brain version. Business has no governing rules."

        parts = [f"Active version: v{version.version_number}"]

        config_areas = {
            "Identity": version.identity_config,
            "Services": version.services_config,
            "Pricing": version.pricing_config,
            "Availability": version.availability_config,
            "Qualification": version.qualification_config,
            "Policies": version.policies_config,
            "Escalation": version.escalation_config,
            "Communication": version.communication_config,
        }

        for label, config in config_areas.items():
            if config:
                parts.append(f"{label}: {json.dumps(config, default=str)[:300]}")

        # Include active rules
        rules = await self.rule_repo.get_by_brain_version_id(version.id)
        if rules:
            parts.append(f"\nActive rules ({len(rules)}):")
            for r in rules[:15]:
                parts.append(f"  - [{r.rule_type}] {r.name}: {json.dumps(r.rule_data, default=str)[:150]}")

        return "\n".join(parts)

    async def _build_approved_knowledge_text(
        self, brain_id: uuid.UUID
    ) -> str:
        """Build text of approved/applied proposals (known knowledge)."""
        proposals = await self.proposal_repo.list_by_brain_id(brain_id, limit=30)
        approved = [
            p for p in proposals
            if p.status in (
                BrainProposalStatus.APPROVED,
                BrainProposalStatus.EDITED,
                BrainProposalStatus.APPLIED,
            )
        ]

        if not approved:
            return "No confirmed knowledge yet."

        lines = []
        for p in approved[:15]:
            summary = p.proposed_change.get("summary", "configured")
            status_label = "applied" if p.status == BrainProposalStatus.APPLIED else "approved"
            lines.append(f"- [{status_label}] {p.proposal_type}: {summary}")
        return "\n".join(lines)

    async def _build_pending_proposals_text(
        self, brain_id: uuid.UUID
    ) -> str:
        pending = await self.proposal_repo.list_pending_by_brain_id(brain_id)
        if not pending:
            return "No pending proposals."

        lines = []
        for p in pending[:5]:
            summary = p.proposed_change.get("summary", "pending decision")
            lines.append(f"- {p.proposal_type}: {summary} (confidence: {p.confidence:.0%})")
        return "\n".join(lines)

    async def _build_missing_info_text(self, brain_id: uuid.UUID) -> str:
        """Identify what information the Brain still needs."""
        version = await self.version_repo.get_active_by_brain_id(brain_id)
        if not version:
            return (
                "CRITICAL: No Brain version exists. Need: services, pricing, "
                "availability, policies, qualification requirements."
            )

        missing = []
        critical = []
        if not version.services_config:
            critical.append("services (what the business offers)")
        if not version.pricing_config:
            critical.append("pricing (how much things cost)")
        if not version.availability_config:
            missing.append("availability (when the business operates)")
        if not version.qualification_config:
            missing.append("qualification (what customers must provide)")
        if not version.policies_config:
            missing.append("policies (cancellation, refund, terms)")

        parts = []
        if critical:
            parts.append(f"CRITICAL: {', '.join(critical)}")
        if missing:
            parts.append(f"Needed: {', '.join(missing)}")
        if not parts:
            parts.append("All core areas are configured.")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Private: Proposal extraction
    # ------------------------------------------------------------------

    def _extract_proposal_from_response(self, content: str) -> dict | None:
        """Extract a structured proposal from AI response.

        Supports both [PROPOSAL]...[/PROPOSAL] blocks and
        ```json ... ``` code blocks after [PROPOSAL] markers.
        """
        import re

        # Pattern 1: [PROPOSAL] ```json {...} ``` [/PROPOSAL]
        pattern1 = r"\[PROPOSAL\]\s*```(?:json)?\s*(\{.*?\})\s*```\s*\[/PROPOSAL\]"
        match = re.search(pattern1, content, re.DOTALL)

        if not match:
            # Pattern 2: [PROPOSAL] {...} [/PROPOSAL]
            pattern2 = r"\[PROPOSAL\]\s*(\{.*?\})\s*\[/PROPOSAL\]"
            match = re.search(pattern2, content, re.DOTALL)

        if not match:
            return None

        try:
            data = json.loads(match.group(1))
            # Validate minimum required fields
            if "proposal_type" not in data:
                return None
            return data
        except json.JSONDecodeError:
            logger.warning("Failed to parse proposal JSON from Brain response")
            return None

    def _clean_proposal_from_text(self, content: str) -> str:
        """Remove proposal blocks from display text."""
        import re

        # Remove [PROPOSAL]...[/PROPOSAL] blocks (including code fences)
        cleaned = re.sub(
            r"\[PROPOSAL\]\s*(?:```(?:json)?\s*)?\{.*?\}(?:\s*```\s*)?\[/PROPOSAL\]",
            "",
            content,
            flags=re.DOTALL,
        )
        return cleaned.strip()

    async def _create_proposal_from_conversation(
        self,
        conversation: BrainConversation,
        source_message: BrainMessage,
        proposal_data: dict,
    ) -> BrainProposal:
        """Create a BrainProposal from AI interpretation."""
        proposal_type_str = proposal_data.get("proposal_type", "general_knowledge")

        try:
            proposal_type = BrainProposalType(proposal_type_str)
        except ValueError:
            proposal_type = BrainProposalType.GENERAL_KNOWLEDGE

        proposal = BrainProposal(
            brain_id=conversation.brain_id,
            conversation_id=conversation.id,
            business_id=conversation.business_id,
            proposal_type=proposal_type,
            status=BrainProposalStatus.PENDING,
            confidence=float(proposal_data.get("confidence", 0.7)),
            reasoning_summary=proposal_data.get("reasoning", ""),
            proposed_change=proposal_data,
            affected_area=proposal_data.get("affected_area"),
            source_message_id=source_message.id,
        )
        return await self.proposal_repo.create(proposal)

    # ------------------------------------------------------------------
    # Private: Apply approved proposal to governed Brain state
    # ------------------------------------------------------------------

    async def _apply_proposal_to_brain(
        self,
        proposal: BrainProposal,
        change_data: dict,
    ) -> None:
        """Apply an approved proposal to the Brain governance system.

        Creates or reuses a DRAFT BrainVersion and adds the appropriate
        config update or BusinessRule through the existing services.
        """
        brain_service = BrainService(self.session)
        rule_service = BusinessRuleService(self.session)

        # Get or create the brain
        brain = await brain_service.get_or_create_brain(proposal.business_id)

        # Find or create a DRAFT version to apply changes to
        draft_version = await self._get_or_create_draft_version(brain, brain_service)

        proposal_type = BrainProposalType(proposal.proposal_type)
        config_area_key, default_rule_type = _PROPOSAL_TYPE_TO_RULE.get(
            proposal_type, (None, None)
        )

        # Determine if this is a rule-based proposal or a config-only proposal
        rule_type = change_data.get("rule_type", default_rule_type)
        rule_data = change_data.get("rule_data")
        rule_name = change_data.get("rule_name", change_data.get("summary", "Brain proposal"))

        if rule_type and rule_data and is_known_rule_type(rule_type):
            # Add as a structured BusinessRule to the DRAFT version
            await rule_service.add_rule(
                brain_version_id=draft_version.id,
                rule_type=rule_type,
                name=rule_name,
                rule_data=rule_data,
                description=change_data.get("reasoning"),
            )
            logger.info(
                "proposal_applied_as_rule",
                proposal_id=str(proposal.id),
                rule_type=rule_type,
                version_id=str(draft_version.id),
            )
        elif config_area_key:
            # Update the config area on the DRAFT version
            config_key = f"{config_area_key}"  # e.g. "services_config"
            existing_config = getattr(draft_version, config_key, None) or {}

            # Merge the proposed change into existing config
            if rule_data:
                # If there's specific rule_data, merge it into the config area
                merged = {**existing_config, **rule_data}
            else:
                # Use the whole proposed_change as config (minus meta fields)
                meta_keys = {
                    "proposal_type", "summary", "reasoning", "confidence",
                    "affected_area", "rule_type", "rule_name", "rule_data",
                }
                config_update = {
                    k: v for k, v in change_data.items() if k not in meta_keys
                }
                merged = {**existing_config, **config_update} if config_update else existing_config

            if merged and merged != existing_config:
                await brain_service.update_version_config(
                    draft_version.id,
                    {config_area_key.replace("_config", ""): merged},
                )
                logger.info(
                    "proposal_applied_as_config",
                    proposal_id=str(proposal.id),
                    config_area=config_area_key,
                    version_id=str(draft_version.id),
                )
        else:
            # General knowledge — store as a rule with type "general"
            # so it's tracked but doesn't affect deterministic evaluation
            if change_data:
                meta_keys = {
                    "proposal_type", "summary", "reasoning", "confidence",
                    "affected_area", "rule_type", "rule_name", "rule_data",
                }
                knowledge_data = {
                    k: v for k, v in change_data.items() if k not in meta_keys
                }
                if not knowledge_data:
                    knowledge_data = {"summary": change_data.get("summary", "")}

                await rule_service.add_rule(
                    brain_version_id=draft_version.id,
                    rule_type="policy",  # Fallback category
                    name=rule_name,
                    rule_data=knowledge_data,
                    description=f"Knowledge from Brain proposal: {change_data.get('reasoning', '')}",
                )

    async def _get_or_create_draft_version(
        self,
        brain: BusinessBrain,
        brain_service: BrainService,
    ) -> BrainVersion:
        """Find an existing DRAFT version or create a new one.

        If there's an active version, the new DRAFT is based on its config.
        """
        # Check for existing DRAFT
        versions = await self.version_repo.get_by_brain_id(brain.id)
        for v in versions:
            if v.status == BrainVersionStatus.DRAFT:
                return v

        # Create new DRAFT based on active version config (if any)
        base_config: dict = {}
        if brain.active_version_id:
            active = await self.version_repo.get_by_id(brain.active_version_id)
            if active:
                base_config = {
                    "identity": active.identity_config,
                    "services": active.services_config,
                    "pricing": active.pricing_config,
                    "availability": active.availability_config,
                    "qualification": active.qualification_config,
                    "policies": active.policies_config,
                    "escalation": active.escalation_config,
                    "communication": active.communication_config,
                }
                # Remove None values
                base_config = {k: v for k, v in base_config.items() if v is not None}

        return await brain_service.create_version(brain.id, config=base_config)
