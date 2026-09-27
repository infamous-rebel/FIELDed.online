"""Business Brain structured response contract.

Defines the semantic block types that the Brain can produce in response
to operator conversation. All LLM output is untrusted and must pass
validation before becoming application state.

Block types are semantic categories — not separate AI systems. They allow
the frontend renderer to display meaningful operational blocks rather than
raw Markdown.

Trust boundary:
- Every LLM-generated field is treated as untrusted.
- Server-side validation ensures block types are known, required fields
  exist, strings/arrays are bounded, and references are valid.
- Structured output represents intent/information only — it cannot
  directly activate BrainVersions, modify pricing, or bypass owner approval.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum length for string fields within blocks.
MAX_BLOCK_STRING_LENGTH = 5_000

#: Maximum number of blocks in a single response.
MAX_BLOCKS_PER_RESPONSE = 50

#: Maximum items in array fields (options, evidence, actions).
MAX_ARRAY_ITEMS = 20

#: Permitted navigation destinations (frontend route keys).
PERMITTED_NAVIGATION_DESTINATIONS: frozenset[str] = frozenset(
    {
        "brain",
        "brain.conversations",
        "brain.knowledge",
        "business.profile",
        "business.services",
        "business.enquiries",
        "business.quotes",
        "business.bookings",
        "business.schedule",
        "business.finance",
        "business.payments",
        "business.communications",
        "business.operations",
        "business.settings",
    }
)


# ---------------------------------------------------------------------------
# Block type enum
# ---------------------------------------------------------------------------


class BrainBlockType(StrEnum):
    """Known semantic block types in a Brain structured response."""

    TEXT = "text"
    OBSERVATION = "observation"
    REASONING = "reasoning"
    RECOMMENDATION = "recommendation"
    QUESTION = "question"
    MISSING_INFORMATION = "missing_information"
    PROPOSAL = "proposal"
    INITIATIVE = "initiative"
    NAVIGATION = "navigation"
    DECISION = "decision"


# ---------------------------------------------------------------------------
# Block models
# ---------------------------------------------------------------------------


class TextBlock(BaseModel):
    """Plain text block — conversational response content."""

    type: Literal["text"] = "text"
    content: str = Field(..., min_length=1, max_length=MAX_BLOCK_STRING_LENGTH)


class ObservationBlock(BaseModel):
    """An observation based on evidence or configuration."""

    type: Literal["observation"] = "observation"
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=MAX_BLOCK_STRING_LENGTH)
    evidence: list[str] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)

    @field_validator("evidence")
    @classmethod
    def validate_evidence_items(cls, v: list[str]) -> list[str]:
        for item in v:
            if not isinstance(item, str) or len(item) > MAX_BLOCK_STRING_LENGTH:
                raise ValueError(f"Evidence item must be a string ≤{MAX_BLOCK_STRING_LENGTH} chars")
        return v


class ReasoningBlock(BaseModel):
    """Concise operator-facing explanation based on observable evidence."""

    type: Literal["reasoning"] = "reasoning"
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=MAX_BLOCK_STRING_LENGTH)


class RecommendationBlock(BaseModel):
    """A recommendation with optional actions."""

    type: Literal["recommendation"] = "recommendation"
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=MAX_BLOCK_STRING_LENGTH)
    actions: list[str] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)

    @field_validator("actions")
    @classmethod
    def validate_action_items(cls, v: list[str]) -> list[str]:
        for item in v:
            if not isinstance(item, str) or len(item) > MAX_BLOCK_STRING_LENGTH:
                raise ValueError(f"Action item must be a string ≤{MAX_BLOCK_STRING_LENGTH} chars")
        return v


class QuestionBlock(BaseModel):
    """A question for the operator with optional choices."""

    type: Literal["question"] = "question"
    question: str = Field(..., min_length=1, max_length=MAX_BLOCK_STRING_LENGTH)
    options: list[str] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)
    allow_custom: bool = True


class MissingInformationBlock(BaseModel):
    """Identifies missing business knowledge the Brain needs."""

    type: Literal["missing_information"] = "missing_information"
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=MAX_BLOCK_STRING_LENGTH)
    field: str = Field(default="", max_length=200)
    options: list[str] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)


class ProposalBlock(BaseModel):
    """Reference to a governed BrainProposal.

    The proposal_id must reference a real proposal — the block is a
    rendering hint, not a second source of truth.
    """

    type: Literal["proposal"] = "proposal"
    proposal_id: str = Field(..., min_length=1, max_length=36)
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1, max_length=MAX_BLOCK_STRING_LENGTH)
    why: str = Field(default="", max_length=MAX_BLOCK_STRING_LENGTH)
    change: str = Field(default="", max_length=MAX_BLOCK_STRING_LENGTH)
    scope: str = Field(default="", max_length=200)
    expected_effect: str = Field(default="", max_length=MAX_BLOCK_STRING_LENGTH)
    evidence: list[str] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)
    status: str = Field(default="pending", max_length=50)

    @field_validator("proposal_id")
    @classmethod
    def validate_proposal_id(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("proposal_id must be a valid UUID") from None
        return v


class InitiativeBlock(BaseModel):
    """A multi-step initiative with actions."""

    type: Literal["initiative"] = "initiative"
    initiative_id: str = Field(default="", max_length=200)
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1, max_length=MAX_BLOCK_STRING_LENGTH)
    priority: str = Field(default="normal", max_length=50)
    actions: list[str] = Field(default_factory=list, max_length=MAX_ARRAY_ITEMS)


class NavigationBlock(BaseModel):
    """Suggests the operator navigate to a specific application destination."""

    type: Literal["navigation"] = "navigation"
    label: str = Field(..., min_length=1, max_length=200)
    destination: str = Field(..., min_length=1, max_length=200)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, v: str) -> str:
        if v not in PERMITTED_NAVIGATION_DESTINATIONS:
            raise ValueError(
                f"Navigation destination '{v}' is not permitted. Allowed: {sorted(PERMITTED_NAVIGATION_DESTINATIONS)}"
            )
        return v


class DecisionBlock(BaseModel):
    """Records a decision outcome (e.g. proposal approved/rejected)."""

    type: Literal["decision"] = "decision"
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=MAX_BLOCK_STRING_LENGTH)
    status: str = Field(default="", max_length=50)


# ---------------------------------------------------------------------------
# Union type for all blocks
# ---------------------------------------------------------------------------

BrainBlock = Annotated[
    TextBlock
    | ObservationBlock
    | ReasoningBlock
    | RecommendationBlock
    | QuestionBlock
    | MissingInformationBlock
    | ProposalBlock
    | InitiativeBlock
    | NavigationBlock
    | DecisionBlock,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Top-level structured response
# ---------------------------------------------------------------------------


class BrainStructuredResponse(BaseModel):
    """Validated structured response from the Brain.

    This is the semantic contract between the backend and frontend.
    The version field allows future evolution.
    """

    version: int = Field(default=1, ge=1, le=1)
    blocks: list[BrainBlock] = Field(default_factory=list, max_length=MAX_BLOCKS_PER_RESPONSE)

    @property
    def has_proposal(self) -> bool:
        """Check if the response contains a proposal block."""
        return any(b.type == BrainBlockType.PROPOSAL for b in self.blocks)

    @property
    def proposal_ids(self) -> list[str]:
        """Extract all proposal IDs from proposal blocks."""
        return [b.proposal_id for b in self.blocks if b.type == BrainBlockType.PROPOSAL]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_brain_response(data: dict[str, Any] | None) -> BrainStructuredResponse | None:
    """Validate a raw dict as a BrainStructuredResponse.

    Returns the validated response, or None if the data is None/empty.
    Raises ValueError if the data is malformed.

    Unknown block types are silently dropped rather than crashing.
    """
    if data is None:
        return None

    if not isinstance(data, dict):
        raise ValueError("Structured response must be a dict")

    version = data.get("version", 1)
    raw_blocks = data.get("blocks", [])

    if not isinstance(raw_blocks, list):
        raise ValueError("'blocks' must be a list")

    # Bound the number of blocks
    if len(raw_blocks) > MAX_BLOCKS_PER_RESPONSE:
        raw_blocks = raw_blocks[:MAX_BLOCKS_PER_RESPONSE]

    # Map type strings to model classes
    _block_type_map: dict[str, type[BaseModel]] = {
        "text": TextBlock,
        "observation": ObservationBlock,
        "reasoning": ReasoningBlock,
        "recommendation": RecommendationBlock,
        "question": QuestionBlock,
        "missing_information": MissingInformationBlock,
        "proposal": ProposalBlock,
        "initiative": InitiativeBlock,
        "navigation": NavigationBlock,
        "decision": DecisionBlock,
    }

    validated_blocks: list[BaseModel] = []
    for raw_block in raw_blocks:
        if not isinstance(raw_block, dict):
            continue  # Skip non-dict blocks

        block_type = raw_block.get("type")
        if not isinstance(block_type, str) or block_type not in _block_type_map:
            continue  # Skip unknown block types

        model_class = _block_type_map[block_type]
        try:
            block = model_class.model_validate(raw_block)
            validated_blocks.append(block)
        except Exception:
            continue  # Skip malformed blocks

    return BrainStructuredResponse(version=version, blocks=validated_blocks)


def safe_parse_brain_response(data: dict[str, Any] | None) -> BrainStructuredResponse | None:
    """Safely parse a brain response, never raising.

    Returns None if parsing fails for any reason. The caller should
    fall back to the plain-text message content.
    """
    try:
        return validate_brain_response(data)
    except Exception:
        return None
