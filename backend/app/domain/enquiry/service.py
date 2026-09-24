"""Enquiry domain service.

Contains business logic for enquiry creation (atomic with conversation),
lifecycle transitions, message sending, and authorization enforcement.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.business.evaluator import (
    BrainDecision,
    BrainDecisionOutcome,
    BrainEvaluator,
    DecisionContext,
)
from app.domain.business.repository import BrainVersionRepository, BusinessBrainRepository
from app.domain.common.enums import (
    ENQUIRY_TRANSITIONS,
    BusinessMemberRole,
    BusinessProfileStatus,
    BusinessStatus,
    EnquiryStatus,
    ServiceOfferStatus,
)
from app.domain.enquiry.models import Conversation, Enquiry, Message
from app.domain.enquiry.repository import (
    ConversationRepository,
    EnquiryRepository,
    MessageRepository,
)
from app.domain.identity.models import Business, BusinessMember, BusinessProfile, User
from app.domain.outbox.models import OutboxEvent
from app.domain.services.models import ServiceOffer
from app.exceptions import (
    AuthorizationError,
    NotFoundError,
    StateTransitionError,
    ValidationError,
)
from app.logging import get_logger

logger = get_logger(__name__)

ROLE_HIERARCHY = {
    BusinessMemberRole.OWNER: 3,
    BusinessMemberRole.ADMIN: 2,
    BusinessMemberRole.STAFF: 1,
}

# Actor-specific transition authority.
# Customers can only cancel their own enquiries.
# Business members can advance the workflow (receive, review, decline, etc.).
# System-controlled transitions (e.g. EXPIRED) are reserved for future automation.
CUSTOMER_ALLOWED_TRANSITIONS: dict[EnquiryStatus, set[EnquiryStatus]] = {
    EnquiryStatus.DRAFT: {EnquiryStatus.CANCELLED},
    EnquiryStatus.SUBMITTED: {EnquiryStatus.CANCELLED},
    EnquiryStatus.RECEIVED: {EnquiryStatus.CANCELLED},
    EnquiryStatus.IN_REVIEW: {EnquiryStatus.CANCELLED},
    EnquiryStatus.NEEDS_INFORMATION: {EnquiryStatus.CANCELLED},
    # Terminal states — no further transitions
    EnquiryStatus.DECLINED: set(),
    EnquiryStatus.CANCELLED: set(),
    EnquiryStatus.EXPIRED: set(),
    EnquiryStatus.REJECTED: set(),
}

BUSINESS_ALLOWED_TRANSITIONS: dict[EnquiryStatus, set[EnquiryStatus]] = {
    EnquiryStatus.DRAFT: set(),  # Should not happen; enquiry starts at SUBMITTED
    EnquiryStatus.SUBMITTED: {
        EnquiryStatus.RECEIVED,
        EnquiryStatus.DECLINED,
        EnquiryStatus.EXPIRED,
    },
    EnquiryStatus.RECEIVED: {
        EnquiryStatus.IN_REVIEW,
        EnquiryStatus.DECLINED,
        EnquiryStatus.EXPIRED,
    },
    EnquiryStatus.IN_REVIEW: {
        EnquiryStatus.NEEDS_INFORMATION,
        EnquiryStatus.QUOTED,
        EnquiryStatus.DECLINED,
        EnquiryStatus.EXPIRED,
    },
    EnquiryStatus.NEEDS_INFORMATION: {
        EnquiryStatus.IN_REVIEW,
        EnquiryStatus.DECLINED,
        EnquiryStatus.EXPIRED,
    },
    # Terminal states — no further transitions
    EnquiryStatus.DECLINED: set(),
    EnquiryStatus.CANCELLED: set(),
    EnquiryStatus.EXPIRED: set(),
    EnquiryStatus.REJECTED: set(),
}

VALID_SENDER_TYPES = {"customer", "business"}


def _generate_reference() -> str:
    """Generate a customer-friendly enquiry reference number."""
    return f"ENQ-{uuid.uuid4().hex[:8]}"


class EnquiryService:
    """Enquiry lifecycle management with atomic conversation creation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.enquiry_repo = EnquiryRepository(session)
        self.conversation_repo = ConversationRepository(session)
        self.message_repo = MessageRepository(session)

    # --- Enquiry creation (atomic with conversation) ---

    async def create_enquiry(
        self,
        *,
        customer: User,
        business_id: uuid.UUID,
        service_offer_id: uuid.UUID,
        subject: str,
        message: str,
    ) -> Enquiry:
        """Create an enquiry and its dedicated conversation atomically.

        All relationships are resolved server-side.  The client is never
        trusted for ownership, authorization, or relationship claims.

        If the business has an active Business Brain, the brain evaluates
        the enquiry qualification before creation.  A DENY decision
        prevents creation; other decisions are recorded in metadata.

        The entire operation runs within the caller's database session.
        If conversation creation fails, the enquiry insert is rolled back
        when the session flushes/commits.
        """
        # 1. Validate business exists and is active
        business = await self._validate_business_eligible(business_id)

        # 2. Validate service offer exists, belongs to business, and is active
        offer = await self._validate_service_offer_eligible(service_offer_id, business_id)

        # 3. Evaluate the active Brain (if any) for qualification.
        decision = await self._evaluate_brain_for_enquiry(
            business_id=business_id,
            service_offer_id=offer.id,
            customer_id=customer.id,
            service_offer=offer,
        )

        # 4. Only an explicit ALLOW permits creation.
        #    DENY, REQUIRE_APPROVAL, ESCALATE, and FAILED all block.
        #    A non-ALLOW decision must NEVER silently allow creation.
        if not decision.is_allowed:
            logger.info(
                "enquiry_blocked_by_brain",
                business_id=str(business_id),
                customer_id=str(customer.id),
                brain_version_id=str(decision.brain_version_id)
                if decision.brain_version_id
                else None,
                brain_decision=decision.decision.value,
                reason=decision.reason,
            )
            raise ValidationError(
                f"Enquiry cannot be created: {decision.reason}",
                details=decision.to_dict(),
            )

        # 5. Create enquiry (DRAFT status — caller transitions to SUBMITTED)
        enquiry = Enquiry(
            reference=_generate_reference(),
            customer_id=customer.id,
            business_id=business.id,
            service_offer_id=offer.id,
            subject=subject,
            message=message,
            status=EnquiryStatus.DRAFT,
            brain_version_id=decision.brain_version_id,
            metadata_=decision.to_dict(),
        )
        enquiry = await self.enquiry_repo.create(enquiry)

        # 6. Create conversation atomically in the same session.
        #    If this fails, the session's transaction ensures the
        #    enquiry insert is also rolled back.
        conversation = Conversation(
            enquiry_id=enquiry.id,
            customer_id=customer.id,
            business_id=business.id,
            status="active",
        )
        conversation = await self.conversation_repo.create(conversation)

        # 7. Transition to SUBMITTED (both entities now exist)
        enquiry.status = EnquiryStatus.SUBMITTED
        await self.enquiry_repo.update(enquiry)

        # 8. Emit outbox event for notification/communication pipeline
        await self._emit_outbox_event(
            business_id=business.id,
            event_type="ENQUIRY_SUBMITTED",
            aggregate_id=enquiry.id,
            payload={
                "enquiry_id": str(enquiry.id),
                "customer_id": str(customer.id),
                "service_offer_id": str(offer.id),
                "status": EnquiryStatus.SUBMITTED,
                "reference": enquiry.reference,
                "subject": enquiry.subject,
                "notification_title": "New enquiry received",
                "notification_body": f"New enquiry {enquiry.reference}: {enquiry.subject}",
            },
        )

        logger.info(
            "enquiry_created",
            enquiry_id=str(enquiry.id),
            reference=enquiry.reference,
            customer_id=str(customer.id),
            business_id=str(business.id),
            service_offer_id=str(offer.id),
            conversation_id=str(conversation.id),
            brain_version_id=str(decision.brain_version_id) if decision.brain_version_id else None,
            brain_decision=decision.decision.value if decision.brain_version_id else None,
        )

        return enquiry

    # --- Customer operations ---

    async def get_customer_enquiry(
        self,
        enquiry_id: uuid.UUID,
        customer_id: uuid.UUID,
    ) -> Enquiry:
        """Get an enquiry, verifying customer ownership."""
        enquiry = await self.enquiry_repo.get_by_id(enquiry_id)
        if enquiry is None:
            raise NotFoundError("Enquiry not found")
        if enquiry.customer_id != customer_id:
            raise AuthorizationError("Not your enquiry")
        return enquiry

    async def list_customer_enquiries(
        self,
        customer_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Enquiry]:
        """List enquiries for a customer."""
        return await self.enquiry_repo.get_by_customer(
            customer_id, status=status, limit=limit, offset=offset
        )

    # --- Business operations ---

    async def get_business_enquiry(
        self,
        enquiry_id: uuid.UUID,
        business_id: uuid.UUID,
    ) -> Enquiry:
        """Get an enquiry, verifying it belongs to the business."""
        enquiry = await self.enquiry_repo.get_by_id(enquiry_id)
        if enquiry is None:
            raise NotFoundError("Enquiry not found")
        if enquiry.business_id != business_id:
            raise AuthorizationError("Enquiry does not belong to this business")
        return enquiry

    async def list_business_enquiries(
        self,
        business_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Enquiry]:
        """List enquiries for a business."""
        return await self.enquiry_repo.get_by_business(
            business_id, status=status, limit=limit, offset=offset
        )

    # --- Lifecycle transitions ---

    async def transition_enquiry(
        self,
        enquiry: Enquiry,
        target_status: EnquiryStatus,
        *,
        actor: str = "system",
    ) -> Enquiry:
        """Transition an enquiry to a new status.

        Validates:
        1. The transition is valid in the global state machine.
        2. The actor (customer/business/system) is authorized for this transition.

        Raises StateTransitionError if either check fails.
        """
        current = EnquiryStatus(enquiry.status)

        # Check global state machine validity
        globally_allowed = ENQUIRY_TRANSITIONS.get(current, set())
        if target_status not in globally_allowed:
            raise StateTransitionError(
                f"Cannot transition from '{current.value}' to "
                f"'{target_status.value}'. "
                f"Allowed: {[s.value for s in globally_allowed] or 'none (terminal state)'}"
            )

        # Check actor-specific authority
        if actor == "customer":
            actor_allowed = CUSTOMER_ALLOWED_TRANSITIONS.get(current, set())
        elif actor == "business":
            actor_allowed = BUSINESS_ALLOWED_TRANSITIONS.get(current, set())
        else:
            # System or future actors: use global transitions
            actor_allowed = globally_allowed

        if target_status not in actor_allowed:
            raise AuthorizationError(
                f"'{actor}' is not authorized to transition from "
                f"'{current.value}' to '{target_status.value}'"
            )

        old_status = enquiry.status
        enquiry.status = target_status
        result = await self.enquiry_repo.update(enquiry)

        # Emit outbox event for notification/communication pipeline
        notification_title = f"Enquiry {target_status.value}"
        notification_body = f"Enquiry {enquiry.reference} status: {target_status.value}"
        if target_status == EnquiryStatus.RECEIVED:
            notification_title = "Enquiry received"
            notification_body = f"Enquiry {enquiry.reference} has been received for review."
        elif target_status == EnquiryStatus.DECLINED:
            notification_title = "Enquiry declined"
            notification_body = f"Enquiry {enquiry.reference} has been declined."
        elif target_status == EnquiryStatus.NEEDS_INFORMATION:
            notification_title = "More information needed"
            notification_body = f"Enquiry {enquiry.reference} needs more information."
        elif target_status == EnquiryStatus.CANCELLED:
            notification_title = "Enquiry cancelled"
            notification_body = f"Enquiry {enquiry.reference} has been cancelled."

        await self._emit_outbox_event(
            business_id=enquiry.business_id,
            event_type=f"ENQUIRY_{target_status.value.upper()}",
            aggregate_id=enquiry.id,
            payload={
                "enquiry_id": str(enquiry.id),
                "customer_id": str(enquiry.customer_id),
                "status": target_status.value,
                "reference": enquiry.reference,
                "notification_title": notification_title,
                "notification_body": notification_body,
            },
        )

        logger.info(
            "enquiry_transition",
            enquiry_id=str(enquiry.id),
            actor=actor,
            from_status=old_status,
            to_status=target_status.value,
        )

        return result

    # --- Conversation access ---

    async def get_enquiry_conversation(
        self,
        enquiry_id: uuid.UUID,
    ) -> Conversation:
        """Get the conversation for an enquiry.

        Raises NotFoundError if the enquiry has no conversation (should
        never happen due to atomic creation, but guarded defensively).
        """
        conversation = await self.conversation_repo.get_by_enquiry_id(enquiry_id)
        if conversation is None:
            raise NotFoundError("Conversation not found for this enquiry")
        return conversation

    # --- Messages ---

    async def send_message(
        self,
        *,
        conversation: Conversation,
        sender: User,
        sender_type: str,
        content: str,
        message_type: str = "text",
    ) -> Message:
        """Send a message in a conversation.

        The caller must have already verified that the sender is authorized
        to access this conversation.

        sender_type is validated server-side to prevent impersonation.
        The sender identity comes from the authenticated context, never
        from client-supplied data.
        """
        if not content or not content.strip():
            raise ValidationError("Message content cannot be empty")

        # Validate sender_type to prevent impersonation
        if sender_type not in VALID_SENDER_TYPES:
            raise ValidationError(f"Invalid sender type: {sender_type}")

        msg = Message(
            conversation_id=conversation.id,
            sender_id=sender.id,
            sender_type=sender_type,
            content=content.strip(),
            message_type=message_type,
        )
        result = await self.message_repo.create(msg)

        logger.info(
            "message_sent",
            message_id=str(result.id),
            conversation_id=str(conversation.id),
            sender_id=str(sender.id),
            sender_type=sender_type,
        )

        return result

    async def list_messages(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        """List messages in a conversation (oldest first)."""
        return await self.message_repo.get_by_conversation(
            conversation_id, limit=limit, offset=offset
        )

    async def mark_messages_read(
        self,
        conversation_id: uuid.UUID,
        reader_id: uuid.UUID,
    ) -> int:
        """Mark unread messages as read for the given reader.

        Only marks messages NOT sent by the reader.
        Returns the count of messages marked as read.
        """
        from datetime import datetime

        messages = await self.message_repo.get_by_conversation(conversation_id, limit=500)
        count = 0
        now = datetime.now(UTC)
        for msg in messages:
            if msg.sender_id != reader_id and msg.read_at is None:
                msg.read_at = now
                await self.message_repo.update(msg)
                count += 1
        return count

    # --- Authorization helpers ---

    async def verify_customer_access(
        self,
        enquiry_or_conversation: Enquiry | Conversation,
        customer_id: uuid.UUID,
    ) -> None:
        """Verify that a customer owns the enquiry/conversation."""
        if enquiry_or_conversation.customer_id != customer_id:
            raise AuthorizationError("Not authorized to access this resource")

    async def verify_business_access(
        self,
        enquiry_or_conversation: Enquiry | Conversation,
        business_id: uuid.UUID,
    ) -> None:
        """Verify that an enquiry/conversation belongs to the business."""
        if enquiry_or_conversation.business_id != business_id:
            raise AuthorizationError("Enquiry does not belong to this business")

    async def verify_business_membership(
        self,
        business_id: uuid.UUID,
        user: User,
    ) -> BusinessMember:
        """Verify user is a member of the business and return the membership."""
        result = await self.session.execute(
            select(BusinessMember).where(
                BusinessMember.user_id == user.id,
                BusinessMember.business_id == business_id,
                BusinessMember.deleted_at.is_(None),
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            raise AuthorizationError("Not a member of this business")
        return membership

    # --- Internal validation ---

    async def _emit_outbox_event(
        self,
        *,
        business_id: uuid.UUID,
        event_type: str,
        aggregate_id: uuid.UUID,
        payload: dict,
    ) -> None:
        """Create an outbox event in the same transaction."""
        from datetime import datetime

        event = OutboxEvent(
            business_id=business_id,
            event_type=event_type,
            aggregate_type="enquiry",
            aggregate_id=aggregate_id,
            payload=payload,
            idempotency_key=f"{event_type}:enquiry:{aggregate_id}",
            status="PENDING",
            available_at=datetime.now(UTC),
        )
        self.session.add(event)
        await self.session.flush()

    async def _validate_business_eligible(self, business_id: uuid.UUID) -> Business:
        """Verify business exists, is active, and has an active public profile."""
        result = await self.session.execute(
            select(Business, BusinessProfile)
            .outerjoin(
                BusinessProfile,
                BusinessProfile.business_id == Business.id,
            )
            .where(
                Business.id == business_id,
                Business.deleted_at.is_(None),
            )
        )
        row = result.one_or_none()
        if row is None:
            raise NotFoundError("Business not found")

        business, profile = row

        if BusinessStatus(business.status) not in (BusinessStatus.ACTIVE, BusinessStatus.PENDING):
            raise ValidationError("Business is not currently active")

        if (
            profile is None
            or BusinessProfileStatus(profile.public_status) != BusinessProfileStatus.ACTIVE
        ):
            raise ValidationError("Business profile is not publicly available")

        return business

    async def _validate_service_offer_eligible(
        self,
        service_offer_id: uuid.UUID,
        business_id: uuid.UUID,
    ) -> ServiceOffer:
        """Verify service offer exists, belongs to business, and is active."""
        result = await self.session.execute(
            select(ServiceOffer).where(
                ServiceOffer.id == service_offer_id,
                ServiceOffer.business_id == business_id,
                ServiceOffer.deleted_at.is_(None),
            )
        )
        offer = result.scalar_one_or_none()
        if offer is None:
            raise NotFoundError("Service offer not found")

        if ServiceOfferStatus(offer.status) != ServiceOfferStatus.ACTIVE:
            raise ValidationError("Service offer is not currently accepting enquiries")

        return offer

    async def _resolve_active_brain_version(self, business_id: uuid.UUID) -> uuid.UUID | None:
        """Resolve the active Brain version for historical reconstruction.

        Returns the brain_version_id if the business has an active Brain
        version, or None if the business has no Brain configured.
        """
        brain_repo = BusinessBrainRepository(self.session)
        brain = await brain_repo.get_by_business_id(business_id)
        if brain is None:
            return None
        return brain.active_version_id

    # --- Brain runtime integration ---

    async def _evaluate_brain_for_enquiry(
        self,
        *,
        business_id: uuid.UUID,
        service_offer_id: uuid.UUID,
        customer_id: uuid.UUID,
        service_offer: ServiceOffer | None = None,
    ) -> BrainDecision:
        """Evaluate the active Brain for enquiry qualification.

        Safety invariant: this method NEVER returns ALLOW when brain
        governance is expected but unavailable.  Missing or broken
        governance produces REQUIRE_APPROVAL so the enquiry is held
        for human review rather than silently passing through.

        Returns:
            BrainDecision — ALLOW only when an active Brain was
            successfully evaluated and permits the transaction.
        """
        brain_repo = BusinessBrainRepository(self.session)
        brain = await brain_repo.get_by_business_id(business_id)
        if brain is None or brain.active_version_id is None:
            # No active Brain configured.  Brain governance is an opt-in
            # feature — when no Brain exists the enquiry proceeds normally.
            logger.info(
                "brain_not_configured",
                business_id=str(business_id),
            )
            return BrainDecision(
                decision=BrainDecisionOutcome.ALLOW,
                brain_version_id=None,
                reason="No active Business Brain — enquiry allowed by default",
            )

        version_repo = BrainVersionRepository(self.session)
        version = await version_repo.get_by_id(brain.active_version_id)
        if version is None:
            # Brain exists but active version record is missing — data inconsistency.
            logger.error(
                "brain_active_version_missing",
                brain_id=str(brain.id),
                active_version_id=str(brain.active_version_id),
            )
            return BrainDecision(
                decision=BrainDecisionOutcome.REQUIRE_APPROVAL,
                brain_version_id=brain.active_version_id,
                reason="Active BrainVersion record not found — manual approval required",
            )

        # Build the decision context from available data
        context_data: dict = {
            "business_id": str(business_id),
            "service_offer_id": str(service_offer_id),
            "customer_id": str(customer_id),
        }
        if service_offer is not None:
            context_data["service_offer"] = {
                "pricing_model": service_offer.pricing_model,
                "delivery_mode": service_offer.delivery_mode,
                "name": service_offer.name,
            }

        context = DecisionContext(
            business_id=business_id,
            service_offer_id=service_offer_id,
            customer_id=customer_id,
            context_data=context_data,
        )

        try:
            evaluator = BrainEvaluator()
            return evaluator.evaluate(version, context)
        except Exception as exc:
            # Evaluation failure → REQUIRE_APPROVAL, not FAILED.
            # FAILED could be misinterpreted by callers; REQUIRE_APPROVAL
            # explicitly holds the enquiry for human review.
            logger.exception(
                "brain_evaluation_failed",
                brain_version_id=str(version.id),
                business_id=str(business_id),
            )
            return BrainDecision(
                decision=BrainDecisionOutcome.REQUIRE_APPROVAL,
                brain_version_id=version.id,
                reason=f"Brain evaluation error — manual approval required: {exc}",
            )

    async def evaluate_enquiry_brain(
        self,
        enquiry: Enquiry,
    ) -> BrainDecision:
        """Evaluate the brain for an existing enquiry (post-creation).

        Useful for re-evaluating after the brain has been updated, or
        for auditing purposes.
        """
        return await self._evaluate_brain_for_enquiry(
            business_id=enquiry.business_id,
            service_offer_id=enquiry.service_offer_id,
            customer_id=enquiry.customer_id,
        )
