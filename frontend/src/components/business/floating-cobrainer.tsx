"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  brainConversation,
  type BrainProposalData,
  type SendMessageResponse,
  FieldedApiError,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CoBrainMessage {
  id?: string;
  role: "brain" | "owner" | "system";
  content: string;
  created_at?: string;
  isPending?: boolean;
  metadata?: {
    kind?: "known" | "evidence" | "inference" | "proposal";
    proposal?: BrainProposalData;
  };
}

type CoBrainStatus = "ready" | "working" | "proposal_ready" | "attention" | "degraded" | "error";

interface FloatingCoBrainProps {
  businessId: string;
  /** Current application context for context-awareness */
  context?: {
    page: string;
    enquiryId?: string;
    quoteId?: string;
    bookingId?: string;
    summary?: string;
  };
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LAUNCHER_SIZE = 52;
const PANEL_WIDTH = 400;
const PANEL_HEIGHT = 560;
const EDGE_PADDING = 12;

const STATUS_CONFIG: Record<CoBrainStatus, { label: string; color: string }> = {
  ready: { label: "Ready", color: "var(--accent)" },
  working: { label: "Working…", color: "var(--info)" },
  proposal_ready: { label: "Proposal ready", color: "var(--warning)" },
  attention: { label: "Needs attention", color: "var(--warning)" },
  degraded: { label: "Degraded", color: "var(--warning)" },
  error: { label: "Error", color: "var(--danger)" },
};

const WORKING_MESSAGES = [
  "Analyzing current enquiry…",
  "Reviewing business context…",
  "Checking operational gaps…",
  "Processing your request…",
  "Consulting business knowledge…",
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FloatingCoBrain({ businessId, context }: FloatingCoBrainProps) {
  // Panel state
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);

  // Position (bottom-right default)
  const [position, setPosition] = useState<{ x: number; y: number }>({ x: -1, y: -1 }); // -1 = not yet initialized
  const [isDragging, setIsDragging] = useState(false);
  const dragOffset = useRef({ x: 0, y: 0 });
  const panelRef = useRef<HTMLDivElement>(null);

  // Conversation state
  const [status, setStatus] = useState<CoBrainStatus>("ready");
  const [messages, setMessages] = useState<CoBrainMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Working message rotation
  const [workingMsg, setWorkingMsg] = useState(WORKING_MESSAGES[0]);
  const workingMsgIndex = useRef(0);

  // Initialize position
  useEffect(() => {
    if (position.x === -1) {
      setPosition({
        x: window.innerWidth - LAUNCHER_SIZE - EDGE_PADDING,
        y: window.innerHeight - LAUNCHER_SIZE - EDGE_PADDING,
      });
    }
  }, [position.x]);

  // Rotate working messages
  useEffect(() => {
    if (status !== "working") return;
    const interval = setInterval(() => {
      workingMsgIndex.current = (workingMsgIndex.current + 1) % WORKING_MESSAGES.length;
      setWorkingMsg(WORKING_MESSAGES[workingMsgIndex.current]);
    }, 3000);
    return () => clearInterval(interval);
  }, [status]);

  // Auto-scroll messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Keep panel inside viewport
  const clampPosition = useCallback((x: number, y: number) => {
    const maxX = window.innerWidth - (isOpen && !isMinimized ? PANEL_WIDTH : LAUNCHER_SIZE) - EDGE_PADDING;
    const maxY = window.innerHeight - (isOpen && !isMinimized ? (isMaximized ? window.innerHeight - 40 : PANEL_HEIGHT) : LAUNCHER_SIZE) - EDGE_PADDING;
    return {
      x: Math.max(EDGE_PADDING, Math.min(x, maxX)),
      y: Math.max(EDGE_PADDING, Math.min(y, maxY)),
    };
  }, [isOpen, isMinimized, isMaximized]);

  // Drag handlers
  const handleDragStart = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    setIsDragging(true);
    const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
    const clientY = "touches" in e ? e.touches[0].clientY : e.clientY;
    dragOffset.current = { x: clientX - position.x, y: clientY - position.y };
  }, [position]);

  useEffect(() => {
    if (!isDragging) return;

    const handleMove = (e: MouseEvent | TouchEvent) => {
      const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
      const clientY = "touches" in e ? e.touches[0].clientY : e.clientY;
      const newPos = clampPosition(
        clientX - dragOffset.current.x,
        clientY - dragOffset.current.y,
      );
      setPosition(newPos);
    };

    const handleEnd = () => setIsDragging(false);

    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleEnd);
    window.addEventListener("touchmove", handleMove);
    window.addEventListener("touchend", handleEnd);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleEnd);
      window.removeEventListener("touchmove", handleMove);
      window.removeEventListener("touchend", handleEnd);
    };
  }, [isDragging, clampPosition]);

  // Send message
  const handleSend = useCallback(async () => {
    if (!input.trim() || sending || !isAuthenticated()) return;

    const userMsg = input.trim();
    setInput("");
    setSending(true);
    setStatus("working");
    setError("");

    // Add user message
    setMessages(prev => [...prev, { role: "owner", content: userMsg }]);

    try {
      // Get or create active conversation
      let convId = conversationId;
      if (!convId) {
        const conv = await brainConversation.getActive(businessId);
        convId = conv.id;
        setConversationId(convId);
      }

      // Send message
      const response: SendMessageResponse = await brainConversation.sendMessage(businessId, convId, userMsg);

      // Add brain response
      const brainMsg: CoBrainMessage = {
        role: "brain",
        content: response.brain_message?.content || "I've processed your request.",
        metadata: response.brain_message?.metadata as CoBrainMessage["metadata"],
      };
      setMessages(prev => [...prev, brainMsg]);

      // Check for pending proposals after this message
      try {
        const pendingProposals = await brainConversation.listPendingProposals(businessId);
        if (pendingProposals.length > 0) {
          setStatus("proposal_ready");
          for (const proposal of pendingProposals.slice(-2)) {
            setMessages(prev => [...prev, {
              role: "system",
              content: `Proposal: ${proposal.proposal_type}`,
              metadata: { kind: "proposal" as const, proposal },
            }]);
          }
        } else {
          setStatus("ready");
        }
      } catch {
        setStatus("ready");
      }
    } catch (err) {
      const errorMsg = err instanceof FieldedApiError ? err.error.message : "Co-Brain unavailable";
      setError(errorMsg);
      setStatus("error");
      setMessages(prev => [...prev, { role: "system", content: `Error: ${errorMsg}` }]);
    } finally {
      setSending(false);
    }
  }, [input, sending, conversationId, businessId, context]);

  // Handle Enter/Shift+Enter
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  // Handle proposal action
  const handleProposalAction = useCallback(async (proposalId: string, action: "approve" | "reject") => {
    try {
      if (action === "approve") {
        await brainConversation.approveProposal(businessId, proposalId);
      } else {
        await brainConversation.rejectProposal(businessId, proposalId);
      }
      setMessages(prev => prev.map(m =>
        m.metadata?.proposal?.id === proposalId
          ? { ...m, content: `${m.content} — ${action === "approve" ? "Approved" : "Rejected"}` }
          : m
      ));
      setStatus("ready");
    } catch {
      setError(`Failed to ${action} proposal`);
    }
  }, [businessId]);

  // Don't render if not in browser
  if (typeof window === "undefined") return null;
  if (position.x === -1) return null;

  const statusConfig = STATUS_CONFIG[status];

  return (
    <>
      {/* Launcher button */}
      {!isOpen && (
        <button
          onMouseDown={handleDragStart}
          onClick={() => !isDragging && setIsOpen(true)}
          className="fixed z-50 flex items-center justify-center rounded-full shadow-lg transition-shadow hover:shadow-xl cursor-grab active:cursor-grabbing"
          style={{
            left: position.x,
            top: position.y,
            width: LAUNCHER_SIZE,
            height: LAUNCHER_SIZE,
            background: "linear-gradient(135deg, var(--accent) 0%, #059669 100%)",
          }}
          aria-label="Open Co-Brain"
          title="Business Co-Brain"
        >
          <svg className="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          {/* Status indicator */}
          <span
            className="absolute -top-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-[var(--bg-primary)]"
            style={{ backgroundColor: statusConfig.color }}
            title={statusConfig.label}
          />
        </button>
      )}

      {/* Panel */}
      {isOpen && !isMinimized && (
        <div
          ref={panelRef}
          className="fixed z-50 flex flex-col glass rounded-xl overflow-hidden shadow-2xl"
          style={{
            left: position.x,
            top: position.y,
            width: isMaximized ? "calc(100vw - 24px)" : PANEL_WIDTH,
            height: isMaximized ? "calc(100vh - 24px)" : PANEL_HEIGHT,
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] bg-[var(--bg-surface)]/80">
            <div className="flex items-center gap-2">
              <div className="h-6 w-6 rounded-md bg-[var(--accent)]/20 flex items-center justify-center">
                <svg className="h-3.5 w-3.5 text-[var(--accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <div>
                <span className="text-xs font-semibold text-[var(--text-primary)]">Co-Brain</span>
                <div className="flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: statusConfig.color }} />
                  <span className="text-[10px] text-[var(--text-muted)]">{statusConfig.label}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {/* Context indicator */}
              {context?.page && (
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/[0.04] text-[var(--text-muted)] mr-1">
                  {context.page}
                </span>
              )}
              <button
                onClick={() => { setIsMinimized(true); setIsOpen(false); }}
                className="p-1 rounded hover:bg-white/[0.06] transition-colors"
                title="Minimize"
              >
                <svg className="h-3.5 w-3.5 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                </svg>
              </button>
              <button
                onClick={() => setIsMaximized(!isMaximized)}
                className="p-1 rounded hover:bg-white/[0.06] transition-colors"
                title={isMaximized ? "Restore" : "Maximize"}
              >
                <svg className="h-3.5 w-3.5 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {isMaximized
                    ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
                    : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                  }
                </svg>
              </button>
              <button
                onClick={() => { setIsOpen(false); }}
                className="p-1 rounded hover:bg-white/[0.06] transition-colors"
                title="Close"
              >
                <svg className="h-3.5 w-3.5 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Messages area */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="h-10 w-10 rounded-xl bg-[var(--accent)]/10 flex items-center justify-center mb-3">
                  <svg className="h-5 w-5 text-[var(--accent)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                </div>
                <p className="text-xs font-medium text-[var(--text-primary)]">Business Co-Brain</p>
                <p className="mt-1 text-[11px] text-[var(--text-muted)] max-w-[200px]">
                  Ask about your business operations, or I can analyze current context and suggest improvements.
                </p>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i}>
                {msg.role === "owner" ? (
                  <div className="flex justify-end">
                    <div className="max-w-[80%] rounded-lg rounded-tr-sm bg-[var(--accent)]/15 border border-[var(--accent)]/20 px-3 py-2">
                      <p className="text-xs text-[var(--text-primary)]">{msg.content}</p>
                    </div>
                  </div>
                ) : msg.role === "brain" ? (
                  <div className="flex justify-start">
                    <div className="max-w-[85%] rounded-lg rounded-tl-sm bg-white/[0.04] border border-white/[0.06] px-3 py-2">
                      <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{msg.content}</p>
                      {msg.metadata?.kind && (
                        <span className="mt-1 inline-block text-[9px] px-1.5 py-0.5 rounded bg-white/[0.03] text-[var(--text-muted)] uppercase">
                          {msg.metadata.kind}
                        </span>
                      )}
                    </div>
                  </div>
                ) : msg.metadata?.kind === "proposal" && msg.metadata.proposal ? (
                  <ProposalCard
                    proposal={msg.metadata.proposal}
                    onAction={handleProposalAction}
                  />
                ) : (
                  <div className="text-center">
                    <span className="text-[10px] text-[var(--text-muted)]">{msg.content}</span>
                  </div>
                )}
              </div>
            ))}

            {status === "working" && (
              <div className="flex justify-start">
                <div className="rounded-lg bg-white/[0.04] border border-white/[0.06] px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="flex gap-0.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-pulse" />
                      <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-pulse" style={{ animationDelay: "0.15s" }} />
                      <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-pulse" style={{ animationDelay: "0.3s" }} />
                    </div>
                    <span className="text-[10px] text-[var(--text-muted)] italic">{workingMsg}</span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Error */}
          {error && (
            <div className="mx-4 mb-2 rounded-md bg-[var(--danger)]/10 border border-[var(--danger)]/20 px-3 py-1.5">
              <p className="text-[10px] text-[var(--danger)]">{error}</p>
            </div>
          )}

          {/* Composer */}
          <div className="px-3 pb-3 pt-1 border-t border-white/[0.04]">
            <div className="flex items-end gap-2 rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask your Co-Brain…"
                disabled={sending}
                rows={1}
                className="flex-1 bg-transparent text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] resize-none focus:outline-none max-h-20"
                aria-label="Co-Brain message"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || sending}
                className="flex-shrink-0 p-1.5 rounded-md text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors disabled:opacity-30"
                title="Send"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Minimized indicator — click to restore */}
      {isMinimized && (
        <button
          onClick={() => { setIsMinimized(false); setIsOpen(true); }}
          className="fixed z-50 flex items-center gap-2 glass rounded-full px-3 py-2 shadow-lg hover:shadow-xl transition-shadow cursor-pointer"
          style={{
            left: position.x,
            top: position.y,
          }}
        >
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: statusConfig.color }} />
          <span className="text-[10px] font-medium text-[var(--text-secondary)]">Co-Brain</span>
        </button>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Proposal Card
// ---------------------------------------------------------------------------

function ProposalCard({
  proposal,
  onAction,
}: {
  proposal: BrainProposalData;
  onAction: (id: string, action: "approve" | "reject") => void;
}) {
  const typeLabels: Record<string, string> = {
    new_service: "New Service",
    pricing_rule: "Pricing",
    policy_rule: "Policy",
    availability_rule: "Availability",
    qualification_rule: "Qualification",
    escalation_rule: "Escalation",
    identity_update: "Identity",
    general_knowledge: "Knowledge",
  };

  return (
    <div className="rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[9px] font-semibold uppercase tracking-wider text-[var(--warning)] px-1.5 py-0.5 rounded bg-[var(--warning)]/10">
          {typeLabels[proposal.proposal_type] || proposal.proposal_type}
        </span>
        <span className="text-[9px] text-[var(--text-muted)]">
          confidence: {Math.round(proposal.confidence * 100)}%
        </span>
      </div>
      {proposal.reasoning_summary && (
        <p className="text-[11px] text-[var(--text-secondary)] mb-2 leading-relaxed">
          {proposal.reasoning_summary}
        </p>
      )}
      {proposal.status === "pending" ? (
        <div className="flex items-center gap-2">
          <button
            onClick={() => onAction(proposal.id, "approve")}
            className="text-[10px] font-medium px-2.5 py-1 rounded bg-[var(--accent)]/15 text-[var(--accent)] border border-[var(--accent)]/20 hover:bg-[var(--accent)]/25 transition-colors"
          >
            Approve
          </button>
          <button
            onClick={() => onAction(proposal.id, "reject")}
            className="text-[10px] font-medium px-2.5 py-1 rounded bg-[var(--danger)]/10 text-[var(--danger)] border border-[var(--danger)]/20 hover:bg-[var(--danger)]/20 transition-colors"
          >
            Reject
          </button>
        </div>
      ) : (
        <span className="text-[10px] text-[var(--text-muted)] capitalize">{proposal.status}</span>
      )}
    </div>
  );
}
