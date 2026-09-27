/**
 * Tests for Brain structured response types and renderer logic.
 *
 * Since the vitest environment is "node" (not jsdom), these tests verify
 * the data structures and type contracts rather than DOM rendering.
 */

import { describe, it, expect } from "vitest";
import type {
  BrainBlock,
  BrainStructuredResponseData,
  BrainTextBlock,
  BrainObservationBlock,
  BrainReasonINGBlock,
  BrainRecommendationBlock,
  BrainQuestionBlock,
  BrainMissingInformationBlock,
  BrainProposalBlock,
  BrainInitiativeBlock,
  BrainNavigationBlock,
  BrainDecisionBlock,
} from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Type contract tests
// ---------------------------------------------------------------------------

describe("BrainStructuredResponse types", () => {
  it("text block has required fields", () => {
    const block: BrainTextBlock = {
      type: "text",
      content: "Hello world",
    };
    expect(block.type).toBe("text");
    expect(block.content).toBe("Hello world");
  });

  it("observation block has required fields", () => {
    const block: BrainObservationBlock = {
      type: "observation",
      title: "Pricing gap",
      content: "No base pricing configured",
      evidence: ["services_config is empty"],
    };
    expect(block.type).toBe("observation");
    expect(block.evidence).toHaveLength(1);
  });

  it("reasoning block has required fields", () => {
    const block: BrainReasonINGBlock = {
      type: "reasoning",
      title: "Why this matters",
      content: "Without pricing, quotes cannot be generated",
    };
    expect(block.type).toBe("reasoning");
  });

  it("recommendation block has required fields", () => {
    const block: BrainRecommendationBlock = {
      type: "recommendation",
      title: "Set base pricing",
      content: "Configure base pricing for your services",
      actions: ["Define hourly rate"],
    };
    expect(block.actions).toHaveLength(1);
  });

  it("question block has required fields", () => {
    const block: BrainQuestionBlock = {
      type: "question",
      question: "What is your hourly rate?",
      options: ["$50-100", "$100-200"],
      allow_custom: true,
    };
    expect(block.options).toHaveLength(2);
    expect(block.allow_custom).toBe(true);
  });

  it("missing_information block has required fields", () => {
    const block: BrainMissingInformationBlock = {
      type: "missing_information",
      title: "Cancellation policy",
      content: "No cancellation policy defined",
      field: "cancellation_policy",
      options: ["Full refund", "No refund"],
    };
    expect(block.field).toBe("cancellation_policy");
  });

  it("proposal block has required fields", () => {
    const block: BrainProposalBlock = {
      type: "proposal",
      proposal_id: "550e8400-e29b-41d4-a716-446655440000",
      title: "New consulting service",
      summary: "Add business consulting at $150/hr",
      why: "High demand",
      change: "Add service_definition rule",
      scope: "services",
      expected_effect: "Enable quoting",
      evidence: ["5 enquiries this month"],
      status: "pending",
    };
    expect(block.type).toBe("proposal");
    expect(block.status).toBe("pending");
  });

  it("initiative block has required fields", () => {
    const block: BrainInitiativeBlock = {
      type: "initiative",
      initiative_id: "init-1",
      title: "Onboarding improvement",
      summary: "Streamline customer onboarding",
      priority: "high",
      actions: ["Define steps"],
    };
    expect(block.priority).toBe("high");
  });

  it("navigation block has required fields", () => {
    const block: BrainNavigationBlock = {
      type: "navigation",
      label: "View services",
      destination: "business.services",
      context: {},
    };
    expect(block.destination).toBe("business.services");
  });

  it("decision block has required fields", () => {
    const block: BrainDecisionBlock = {
      type: "decision",
      title: "Proposal approved",
      content: "The pricing rule has been applied",
      status: "approved",
    };
    expect(block.status).toBe("approved");
  });

  it("full structured response is valid", () => {
    const response: BrainStructuredResponseData = {
      version: 1,
      blocks: [
        { type: "text", content: "Here is what I found" },
        {
          type: "observation",
          title: "Gap",
          content: "No pricing configured",
          evidence: [],
        },
      ],
    };
    expect(response.version).toBe(1);
    expect(response.blocks).toHaveLength(2);
  });

  it("null structured_response is handled", () => {
    const response: BrainStructuredResponseData | null = null;
    expect(response).toBeNull();
  });

  it("empty blocks array is valid", () => {
    const response: BrainStructuredResponseData = {
      version: 1,
      blocks: [],
    };
    expect(response.blocks).toHaveLength(0);
  });

  it("all block types are valid BrainBlock union members", () => {
    const blocks: BrainBlock[] = [
      { type: "text", content: "hello" },
      { type: "observation", title: "t", content: "c", evidence: [] },
      { type: "reasoning", title: "t", content: "c" },
      { type: "recommendation", title: "t", content: "c", actions: [] },
      { type: "question", question: "q?", options: [], allow_custom: true },
      { type: "missing_information", title: "t", content: "c", field: "", options: [] },
      {
        type: "proposal",
        proposal_id: "550e8400-e29b-41d4-a716-446655440000",
        title: "t",
        summary: "s",
        why: "",
        change: "",
        scope: "",
        expected_effect: "",
        evidence: [],
        status: "pending",
      },
      { type: "initiative", initiative_id: "", title: "t", summary: "s", priority: "normal", actions: [] },
      { type: "navigation", label: "l", destination: "brain", context: {} },
      { type: "decision", title: "t", content: "c", status: "" },
    ];
    expect(blocks).toHaveLength(10);
    // Verify each block type is present
    const types = blocks.map((b) => b.type);
    expect(types).toContain("text");
    expect(types).toContain("observation");
    expect(types).toContain("reasoning");
    expect(types).toContain("recommendation");
    expect(types).toContain("question");
    expect(types).toContain("missing_information");
    expect(types).toContain("proposal");
    expect(types).toContain("initiative");
    expect(types).toContain("navigation");
    expect(types).toContain("decision");
  });
});
