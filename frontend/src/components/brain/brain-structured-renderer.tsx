"use client";

import type {
  BrainBlock,
  BrainStructuredResponseData,
} from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Renders a Brain structured response as semantic blocks.
 *
 * Falls back to the provided plain-text content when:
 * - structured_response is null/undefined
 * - blocks array is empty
 * - an unknown block type is encountered
 *
 * The user must never see a blank Brain response because structured
 * parsing failed.
 */
export function BrainStructuredRenderer({
  structured,
  fallbackContent,
}: {
  structured: BrainStructuredResponseData | null | undefined;
  fallbackContent: string;
}) {
  // No structured data → render plain text fallback
  if (!structured || !structured.blocks || structured.blocks.length === 0) {
    return <PlainTextFallback content={fallbackContent} />;
  }

  return (
    <div className="space-y-2">
      {structured.blocks.map((block, index) => (
        <BlockRenderer key={index} block={block} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Block dispatcher
// ---------------------------------------------------------------------------

function BlockRenderer({ block }: { block: BrainBlock }) {
  switch (block.type) {
    case "text":
      return <TextBlock block={block} />;
    case "observation":
      return <ObservationBlock block={block} />;
    case "reasoning":
      return <ReasoningBlock block={block} />;
    case "recommendation":
      return <RecommendationBlock block={block} />;
    case "question":
      return <QuestionBlock block={block} />;
    case "missing_information":
      return <MissingInformationBlock block={block} />;
    case "proposal":
      return <ProposalBlockRef block={block} />;
    case "initiative":
      return <InitiativeBlock block={block} />;
    case "navigation":
      return <NavigationBlock block={block} />;
    case "decision":
      return <DecisionBlock block={block} />;
    default:
      // Unknown block type — do not crash, silently skip
      return null;
  }
}

// ---------------------------------------------------------------------------
// Block renderers
// ---------------------------------------------------------------------------

function PlainTextFallback({ content }: { content: string }) {
  return (
    <p className="text-sm whitespace-pre-wrap leading-relaxed">
      {stripMarkdown(content)}
    </p>
  );
}

/**
 * Strip raw markdown syntax from display text.
 * Defence-in-depth: the backend should store clean content,
 * but historical messages may still contain markdown.
 */
function stripMarkdown(text: string): string {
  return text
    .replace(/```\w*\n?/g, "")
    .replace(/```/g, "")
    .replace(/^\s*[-*_]{3,}\s*$/gm, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/(?<!\w)_(.+?)_(?!\w)/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .replace(/^>\s?/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function TextBlock({ block }: { block: { type: "text"; content: string } }) {
  return (
    <p className="text-sm whitespace-pre-wrap leading-relaxed">
      {block.content}
    </p>
  );
}

function ObservationBlock({
  block,
}: {
  block: { type: "observation"; title: string; content: string; evidence: string[] };
}) {
  return (
    <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 px-3 py-2">
      <p className="text-xs font-semibold text-blue-400 mb-1">{block.title}</p>
      <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
        {block.content}
      </p>
      {block.evidence.length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {block.evidence.slice(0, 5).map((e, i) => (
            <li
              key={i}
              className="text-[11px] text-[var(--text-muted)] flex items-start gap-1.5"
            >
              <span className="text-blue-400 mt-0.5">·</span>
              {e}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReasoningBlock({
  block,
}: {
  block: { type: "reasoning"; title: string; content: string };
}) {
  return (
    <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 px-3 py-2">
      <p className="text-xs font-semibold text-purple-400 mb-1">
        {block.title}
      </p>
      <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
        {block.content}
      </p>
    </div>
  );
}

function RecommendationBlock({
  block,
}: {
  block: {
    type: "recommendation";
    title: string;
    content: string;
    actions: string[];
  };
}) {
  return (
    <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
      <p className="text-xs font-semibold text-emerald-400 mb-1">
        {block.title}
      </p>
      <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
        {block.content}
      </p>
      {block.actions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {block.actions.slice(0, 5).map((action, i) => (
            <span
              key={i}
              className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
            >
              {action}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function QuestionBlock({
  block,
}: {
  block: { type: "question"; question: string; options: string[]; allow_custom: boolean };
}) {
  return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
      <p className="text-sm text-[var(--text-primary)] font-medium mb-2">
        {block.question}
      </p>
      {block.options.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {block.options.slice(0, 8).map((opt, i) => (
            <span
              key={i}
              className="text-[11px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20"
            >
              {opt}
            </span>
          ))}
          {block.allow_custom && (
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-[var(--bg-elevated)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
              or type your answer
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function MissingInformationBlock({
  block,
}: {
  block: {
    type: "missing_information";
    title: string;
    content: string;
    field: string;
    options: string[];
  };
}) {
  return (
    <div className="rounded-lg border border-orange-500/20 bg-orange-500/5 px-3 py-2">
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-xs font-semibold text-orange-400">
          Missing: {block.title}
        </span>
      </div>
      <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
        {block.content}
      </p>
      {block.options.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {block.options.slice(0, 6).map((opt, i) => (
            <span
              key={i}
              className="text-[11px] px-2 py-0.5 rounded-full bg-orange-500/10 text-orange-400 border border-orange-500/20"
            >
              {opt}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ProposalBlockRef({
  block,
}: {
  block: {
    type: "proposal";
    proposal_id: string;
    title: string;
    summary: string;
    why: string;
    change: string;
    scope: string;
    expected_effect: string;
    evidence: string[];
    status: string;
  };
}) {
  return (
    <div className="rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5 px-3 py-2">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[9px] font-semibold uppercase tracking-wider text-[var(--warning)] px-1.5 py-0.5 rounded bg-[var(--warning)]/10">
          Proposal
        </span>
        <span className="text-[9px] text-[var(--text-muted)] capitalize">
          {block.status}
        </span>
      </div>
      <p className="text-xs font-semibold text-[var(--text-primary)] mb-1">
        {block.title}
      </p>
      <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed mb-1">
        {block.summary}
      </p>
      {block.why && (
        <p className="text-[11px] text-[var(--text-muted)]">
          <span className="font-medium">Why:</span> {block.why}
        </p>
      )}
      {block.scope && (
        <p className="text-[11px] text-[var(--text-muted)]">
          <span className="font-medium">Scope:</span> {block.scope}
        </p>
      )}
      {block.expected_effect && (
        <p className="text-[11px] text-[var(--text-muted)]">
          <span className="font-medium">Expected effect:</span>{" "}
          {block.expected_effect}
        </p>
      )}
    </div>
  );
}

function InitiativeBlock({
  block,
}: {
  block: {
    type: "initiative";
    initiative_id: string;
    title: string;
    summary: string;
    priority: string;
    actions: string[];
  };
}) {
  return (
    <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-semibold text-cyan-400">
          {block.title}
        </span>
        <span className="text-[9px] text-[var(--text-muted)] capitalize">
          {block.priority}
        </span>
      </div>
      <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
        {block.summary}
      </p>
      {block.actions.length > 0 && (
        <ul className="mt-1.5 space-y-0.5">
          {block.actions.slice(0, 5).map((a, i) => (
            <li
              key={i}
              className="text-[11px] text-[var(--text-muted)] flex items-start gap-1.5"
            >
              <span className="text-cyan-400 mt-0.5">→</span>
              {a}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NavigationBlock({
  block,
}: {
  block: { type: "navigation"; label: string; destination: string; context: Record<string, unknown> };
}) {
  return (
    <div className="inline-flex items-center gap-1.5 rounded-md bg-[var(--bg-elevated)] border border-[var(--border-subtle)] px-2.5 py-1">
      <svg
        className="w-3 h-3 text-[var(--accent)]"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M13 7l5 5m0 0l-5 5m5-5H6"
        />
      </svg>
      <span className="text-[11px] text-[var(--accent)] font-medium">
        {block.label}
      </span>
    </div>
  );
}

function DecisionBlock({
  block,
}: {
  block: { type: "decision"; title: string; content: string; status: string };
}) {
  const statusColor =
    block.status === "approved"
      ? "text-emerald-400 border-emerald-500/20 bg-emerald-500/5"
      : block.status === "rejected"
        ? "text-[var(--danger)] border-[var(--danger)]/20 bg-[var(--danger)]/5"
        : "text-[var(--text-muted)] border-[var(--border-subtle)] bg-[var(--bg-elevated)]";

  return (
    <div className={`rounded-lg border px-3 py-2 ${statusColor}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-semibold">{block.title}</span>
        {block.status && (
          <span className="text-[9px] uppercase tracking-wider capitalize">
            {block.status}
          </span>
        )}
      </div>
      <p className="text-[11px] leading-relaxed">{block.content}</p>
    </div>
  );
}
