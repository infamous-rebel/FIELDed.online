"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  brain,
  brainConversation,
  businesses,
  type BrainContext,
  type BrainConversationDetail,
  type BrainProposalData,
  type BusinessBrainDetail,
  type BusinessSummary,
  type NeedsAttentionItem,
  FieldedApiError,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

// --- Types ---

interface Message {
  id?: string;
  role: "brain" | "owner" | "system";
  content: string;
  created_at?: string;
  isPending?: boolean;
}

// --- Helpers ---

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function proposalTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    new_service: "New Service",
    pricing_rule: "Pricing",
    policy_rule: "Policy",
    availability_rule: "Availability",
    qualification_rule: "Qualification",
    escalation_rule: "Escalation",
    identity_update: "Business Identity",
    communication_update: "Communication",
    general_knowledge: "Knowledge",
  };
  return labels[type] || type;
}

function areaLabel(area: string): string {
  return area.charAt(0).toUpperCase() + area.slice(1);
}

function deriveBrainStatus(
  brainData: BusinessBrainDetail | null,
  attentionCount: number,
  proposalCount: number,
): { label: string; variant: "success" | "warning" | "info" | "muted" } {
  if (!brainData) return { label: "Initializing", variant: "muted" };
  if (attentionCount > 0 || proposalCount > 0)
    return { label: "Needs your attention", variant: "warning" };
  if (brainData.active_version_id)
    return { label: "Active", variant: "success" };
  if (brainData.version_count > 0)
    return { label: "Getting to know your business", variant: "info" };
  return { label: "Ready to learn", variant: "muted" };
}

function attentionIcon(type: string): string {
  switch (type) {
    case "pending_proposal":
      return "A";
    case "missing_configuration":
      return "!";
    case "no_active_version":
      return "○";
    default:
      return "·";
  }
}

function attentionMessage(item: NeedsAttentionItem): string {
  if (item.type === "pending_proposal") {
    const what = proposalTypeLabel(item.proposal_type || "");
    return `A ${what.toLowerCase()} change is ready for your decision`;
  }
  if (item.type === "missing_configuration") {
    return `I still need to learn about ${areaLabel(item.affected_area || "this area")}`;
  }
  if (item.type === "no_active_version") {
    return "No active business knowledge yet — approve proposals to activate";
  }
  return item.title;
}

function proposalSummary(proposal: BrainProposalData): string {
  const change = proposal.proposed_change;
  const summary = change.summary;
  if (typeof summary === "string" && summary.trim()) return summary;
  if (proposal.reasoning_summary) return proposal.reasoning_summary;
  return `Brain proposes a ${proposalTypeLabel(proposal.proposal_type).toLowerCase()} change`;
}

function proposalDetail(proposal: BrainProposalData): string | null {
  const c = proposal.proposed_change;
  if (c.rule_name && c.rule_type) {
    return `${String(c.rule_type)} — ${String(c.rule_name)}`;
  }
  if (c.rule_type) return String(c.rule_type);
  return null;
}

// --- Main Component ---

export default function BusinessBrainPage() {
  const [authed, setAuthed] = useState(false);
  const [business, setBusiness] = useState<BusinessSummary | null>(null);
  const [brainData, setBrainData] = useState<BusinessBrainDetail | null>(null);
  const [conversation, setConversation] = useState<BrainConversationDetail | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pendingProposals, setPendingProposals] = useState<BrainProposalData[]>([]);
  const [brainContext, setBrainContext] = useState<BrainContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // UI state
  const [inputValue, setInputValue] = useState("");
  const [sending, setSending] = useState(false);
  const [showKnowledge, setShowKnowledge] = useState(false);
  const [editingProposal, setEditingProposal] = useState<BrainProposalData | null>(null);
  const [editValue, setEditValue] = useState("");
  const [dismissingAttention, setDismissingAttention] = useState<Set<string>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load data
  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const bizList = await businesses.list();
      if (bizList.length === 0) {
        setError("No business found. Create one first.");
        return;
      }
      setBusiness(bizList[0]);

      const [brainDetail, activeConv, proposals, context] = await Promise.all([
        brain.getDetail(bizList[0].id),
        brainConversation.getActive(bizList[0].id),
        brainConversation.listPendingProposals(bizList[0].id),
        brainConversation.getContext(bizList[0].id).catch(() => null),
      ]);

      setBrainData(brainDetail);
      setConversation(activeConv);
      setPendingProposals(proposals);
      if (context) setBrainContext(context);

      if (activeConv?.messages) {
        setMessages(
          activeConv.messages.map((m) => ({
            id: m.id,
            role: m.role as "brain" | "owner" | "system",
            content: m.content,
            created_at: m.created_at,
          }))
        );
      }
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authed) loadData();
  }, [authed, loadData]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 160) + "px";
    }
  }, [inputValue]);

  // --- Handlers ---

  const handleSendMessage = async () => {
    if (!business || !conversation || !inputValue.trim()) return;

    const content = inputValue.trim();
    setInputValue("");

    const ownerMessage: Message = { role: "owner", content, isPending: true };
    setMessages((prev) => [...prev, ownerMessage]);
    setSending(true);

    try {
      const response = await brainConversation.sendMessage(
        business.id,
        conversation.id,
        content
      );

      setMessages((prev) => {
        const updated = prev.map((m) =>
          m.isPending && m.content === content
            ? { ...response.owner_message, role: "owner" as const }
            : m
        );
        return [
          ...updated,
          { ...response.brain_message, role: "brain" as const },
        ];
      });

      const [proposals, context] = await Promise.all([
        brainConversation.listPendingProposals(business.id),
        brainConversation.getContext(business.id).catch(() => null),
      ]);
      setPendingProposals(proposals);
      if (context) setBrainContext(context);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to send message");
      setMessages((prev) => prev.filter((m) => !m.isPending));
    } finally {
      setSending(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleApproveProposal = async (proposal: BrainProposalData) => {
    if (!business) return;
    try {
      await brainConversation.approveProposal(business.id, proposal.id);
      setPendingProposals((prev) => prev.filter((p) => p.id !== proposal.id));
      if (business) {
        const context = await brainConversation.getContext(business.id).catch(() => null);
        if (context) setBrainContext(context);
      }
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to approve");
    }
  };

  const handleApproveWithEdit = async (proposal: BrainProposalData) => {
    if (!business) return;
    try {
      let editedChange: Record<string, unknown> | undefined;
      try {
        editedChange = JSON.parse(editValue);
      } catch {
        editedChange = { summary: editValue };
      }
      await brainConversation.approveProposal(business.id, proposal.id, editedChange);
      setPendingProposals((prev) => prev.filter((p) => p.id !== proposal.id));
      setEditingProposal(null);
      setEditValue("");
      const context = await brainConversation.getContext(business.id).catch(() => null);
      if (context) setBrainContext(context);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to approve with edit");
    }
  };

  const handleRejectProposal = async (proposalId: string) => {
    if (!business) return;
    try {
      await brainConversation.rejectProposal(business.id, proposalId);
      setPendingProposals((prev) => prev.filter((p) => p.id !== proposalId));
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to reject");
    }
  };

  // --- Render ---

  if (!authed) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12">
        <p className="text-[var(--text-secondary)]">Please sign in to access Business Brain.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-12 space-y-6">
        <LoadingSkeleton lines={2} />
        <LoadingSkeleton variant="card" />
      </div>
    );
  }

  const hasActiveVersion = brainData?.active_version_id != null;
  const knowledge = brainContext?.knowledge;
  const attentionItems = brainContext?.attention ?? [];
  const missingAreas = knowledge?.missing_areas ?? [];
  const activeAreas = knowledge?.active_config_areas ?? [];
  const status = deriveBrainStatus(brainData, attentionItems.length, pendingProposals.length);
  const knownCount = knowledge?.known?.length ?? 0;
  const proposedCount = knowledge?.proposed?.length ?? 0;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 space-y-6">
      {/* ── Brain Identity Header ── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-xl flex items-center justify-center text-lg font-semibold
                ${
                  status.variant === "success"
                    ? "bg-emerald-500/15 text-emerald-400"
                    : status.variant === "warning"
                    ? "bg-amber-500/15 text-amber-400"
                    : status.variant === "info"
                    ? "bg-blue-500/15 text-blue-400"
                    : "bg-[var(--bg-elevated)] text-[var(--text-muted)]"
                }`}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a8 8 0 0 0-8 8c0 3.4 2.1 6.3 5 7.5V20a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2v-2.5c2.9-1.2 5-4.1 5-7.5a8 8 0 0 0-8-8z" />
                <path d="M10 22h4" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-semibold text-[var(--text-primary)] tracking-tight">
                Business Brain
              </h1>
              <p className="text-sm text-[var(--text-secondary)] mt-0.5">
                Your intelligent business partner
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <Badge variant={status.variant}>{status.label}</Badge>
            {hasActiveVersion && brainData?.active_version && (
              <span className="text-xs text-[var(--text-muted)] tabular-nums">
                v{brainData.active_version.version_number}
              </span>
            )}
          </div>
        </div>

        {/* Compact context line */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--text-muted)]">
          {knownCount > 0 && (
            <span>{knownCount} thing{knownCount !== 1 ? "s" : ""} known</span>
          )}
          {missingAreas.length > 0 && (
            <span>{missingAreas.length} area{missingAreas.length !== 1 ? "s" : ""} to learn</span>
          )}
          {proposedCount > 0 && (
            <span>{proposedCount} proposed</span>
          )}
          {hasActiveVersion && <span>Governing transactions</span>}
          {knownCount === 0 && missingAreas.length === 0 && !hasActiveVersion && (
            <span>Tell your Brain about your business to get started</span>
          )}
        </div>
      </div>

      {/* ── Error display ── */}
      {error && (
        <div className="rounded-lg border border-[var(--danger)]/20 bg-[var(--danger)]/10 px-4 py-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      )}

      {/* ── Needs Attention ── */}
      {attentionItems.length > 0 && (
        <div className="space-y-2">
          {attentionItems.slice(0, 5).map((item, idx) => {
            const key = `${item.type}-${item.id || idx}`;
            const isDismissed = dismissingAttention.has(key);
            if (isDismissed) return null;
            return (
              <div
                key={key}
                className={`flex items-start gap-3 rounded-lg border px-4 py-3 transition-colors
                  ${
                    item.is_urgent
                      ? "border-amber-500/25 bg-amber-500/5"
                      : "border-[var(--border-subtle)] bg-[var(--bg-surface)]"
                  }`}
              >
                <div
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold
                    ${item.is_urgent ? "bg-amber-500/20 text-amber-400" : "bg-blue-500/15 text-blue-400"}`}
                >
                  {attentionIcon(item.type)}
                </div>
                <p className="flex-1 text-sm text-[var(--text-primary)] leading-relaxed">
                  {attentionMessage(item)}
                </p>
                <button
                  onClick={() =>
                    setDismissingAttention((prev) => new Set(prev).add(key))
                  }
                  className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors text-xs mt-0.5"
                  aria-label="Dismiss"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Pending Proposals ── */}
      {pendingProposals.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-medium text-[var(--text-secondary)]">
            {pendingProposals.length === 1
              ? "A decision for you"
              : `${pendingProposals.length} decisions for you`}
          </h2>
          {pendingProposals.map((proposal) => (
            <div
              key={proposal.id}
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] overflow-hidden"
            >
              {editingProposal?.id === proposal.id ? (
                /* ── Edit mode ── */
                <div className="p-5 space-y-3">
                  <p className="text-xs text-[var(--text-muted)]">
                    Adjust the change before approving. Type a plain description or paste structured data.
                  </p>
                  <textarea
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none"
                    rows={3}
                    placeholder={proposalSummary(proposal)}
                    autoFocus
                  />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={() => handleApproveWithEdit(proposal)}
                    >
                      Approve adjusted
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditingProposal(null);
                        setEditValue("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                /* ── Display mode ── */
                <div className="p-5">
                  <div className="flex items-center gap-2 mb-2.5">
                    <Badge variant="info">{proposalTypeLabel(proposal.proposal_type)}</Badge>
                    {proposal.confidence > 0 && (
                      <span className="text-xs text-[var(--text-muted)]">
                        {Math.round(proposal.confidence * 100)}% confident
                      </span>
                    )}
                    {proposal.is_urgent && (
                      <Badge variant="warning">Important</Badge>
                    )}
                  </div>

                  <p className="text-sm text-[var(--text-primary)] leading-relaxed mb-1">
                    {proposalSummary(proposal)}
                  </p>

                  {proposalDetail(proposal) && (
                    <p className="text-xs text-[var(--text-muted)] mb-4">
                      {proposalDetail(proposal)}
                    </p>
                  )}
                  {!proposalDetail(proposal) && <div className="mb-4" />}

                  <div className="flex items-center gap-2 pt-2 border-t border-[var(--border-subtle)]">
                    <Button
                      size="sm"
                      onClick={() => handleApproveProposal(proposal)}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setEditingProposal(proposal);
                        setEditValue("");
                      }}
                    >
                      Adjust &amp; approve
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleRejectProposal(proposal.id)}
                    >
                      Dismiss
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Conversation Workspace ── */}
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] flex flex-col">
        {/* Conversation header */}
        <div className="px-5 py-4 border-b border-[var(--border-subtle)]">
          <div className="flex items-center gap-2.5">
            <div className="relative">
              <div className="w-8 h-8 rounded-lg bg-[var(--accent)]/15 flex items-center justify-center">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent)]">
                  <path d="M12 2a8 8 0 0 0-8 8c0 3.4 2.1 6.3 5 7.5V20a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2v-2.5c2.9-1.2 5-4.1 5-7.5a8 8 0 0 0-8-8z" />
                  <path d="M10 22h4" />
                </svg>
              </div>
              {conversation?.status === "active" && (
                <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-[var(--accent)] border-2 border-[var(--bg-surface)]" />
              )}
            </div>
            <div>
              <h2 className="text-sm font-medium text-[var(--text-primary)]">
                Conversation
              </h2>
              <p className="text-xs text-[var(--text-muted)]">
                {conversation?.status === "active"
                  ? "Active session"
                  : "Start talking to your Brain"}
              </p>
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4 min-h-[320px] max-h-[520px]">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-8">
              <div className="w-12 h-12 rounded-2xl bg-[var(--bg-elevated)] flex items-center justify-center mb-4">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--text-muted)]">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <p className="text-sm font-medium text-[var(--text-primary)] mb-1">
                Start a conversation
              </p>
              <p className="text-xs text-[var(--text-muted)] max-w-xs leading-relaxed">
                Tell your Brain about your services, pricing, availability, and
                policies. It learns, remembers, and brings important decisions to
                you.
              </p>
            </div>
          ) : (
            messages.map((message, index) => (
              <div
                key={message.id || index}
                className={`flex ${message.role === "owner" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-2.5 ${
                    message.role === "owner"
                      ? "bg-[var(--accent)] text-white rounded-br-md"
                      : message.role === "system"
                      ? "bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-secondary)] rounded-bl-md"
                      : "bg-[var(--bg-elevated)] text-[var(--text-primary)] rounded-bl-md"
                  }`}
                >
                  {message.role === "brain" && (
                    <p className="text-xs font-medium text-[var(--accent)] mb-1">
                      Brain
                    </p>
                  )}
                  <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
                  {(message.created_at || message.isPending) && (
                    <p
                      className={`text-[10px] mt-1 ${
                        message.role === "owner"
                          ? "text-white/60"
                          : "text-[var(--text-muted)]"
                      }`}
                    >
                      {message.isPending ? "Sending..." : formatTime(message.created_at!)}
                    </p>
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="px-5 py-4 border-t border-[var(--border-subtle)]">
          <div className="flex gap-3 items-end">
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="Tell the Brain about your business..."
              rows={1}
              disabled={sending || !conversation}
              className="flex-1 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3.5 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none disabled:opacity-50 leading-relaxed"
            />
            <Button
              onClick={handleSendMessage}
              disabled={sending || !inputValue.trim() || !conversation}
              loading={sending}
              className="shrink-0"
            >
              Send
            </Button>
          </div>
        </div>
      </div>

      {/* ── Brain Knowledge (secondary, progressive disclosure) ── */}
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] overflow-hidden">
        <button
          onClick={() => setShowKnowledge(!showKnowledge)}
          className="w-full flex items-center justify-between px-5 py-4 cursor-pointer hover:bg-[var(--bg-elevated)]/50 transition-colors"
        >
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-medium text-[var(--text-primary)]">
              What the Brain knows
            </h2>
            <div className="flex items-center gap-1.5">
              {activeAreas.length > 0 && (
                <span className="text-xs text-[var(--text-muted)]">
                  {activeAreas.length} area{activeAreas.length !== 1 ? "s" : ""} active
                </span>
              )}
              {missingAreas.length > 0 && (
                <span className="text-xs text-[var(--text-muted)]">
                  {activeAreas.length > 0 ? "·" : ""} {missingAreas.length} to learn
                </span>
              )}
            </div>
          </div>
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`text-[var(--text-muted)] transition-transform duration-200 ${showKnowledge ? "rotate-180" : ""}`}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {showKnowledge && (
          <div className="px-5 pb-5 space-y-5 border-t border-[var(--border-subtle)] pt-5">
            {/* Active areas */}
            {activeAreas.length > 0 && (
              <div>
                <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2.5">
                  Active areas
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {activeAreas.map((area) => (
                    <span
                      key={area}
                      className="inline-flex items-center rounded-md bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400"
                    >
                      {areaLabel(area)}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Missing areas */}
            {missingAreas.length > 0 && (
              <div>
                <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2.5">
                  Still learning
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {missingAreas.map((area) => (
                    <span
                      key={area}
                      className="inline-flex items-center rounded-md bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-400"
                    >
                      {areaLabel(area)}
                    </span>
                  ))}
                </div>
                <p className="mt-2 text-xs text-[var(--text-muted)] leading-relaxed">
                  Mention these topics in conversation and the Brain will learn.
                </p>
              </div>
            )}

            {/* Known items */}
            {knowledge && knowledge.known.length > 0 && (
              <div>
                <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2.5">
                  Known ({knowledge.known.length})
                </h3>
                <div className="space-y-1.5">
                  {knowledge.known.slice(0, 12).map((item) => (
                    <div
                      key={item.id}
                      className="flex items-start gap-2.5 text-sm"
                    >
                      <Badge variant="success" className="text-[10px] shrink-0 mt-0.5">
                        {proposalTypeLabel(item.type)}
                      </Badge>
                      <span className="text-[var(--text-primary)] leading-relaxed">{item.summary}</span>
                    </div>
                  ))}
                  {knowledge.known.length > 12 && (
                    <p className="text-xs text-[var(--text-muted)] pt-1">
                      +{knowledge.known.length - 12} more
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Proposed items */}
            {knowledge && knowledge.proposed.length > 0 && (
              <div>
                <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2.5">
                  Awaiting decision ({knowledge.proposed.length})
                </h3>
                <div className="space-y-1.5">
                  {knowledge.proposed.slice(0, 6).map((item) => (
                    <div
                      key={item.id}
                      className="flex items-start gap-2.5 text-sm"
                    >
                      <Badge variant="warning" className="text-[10px] shrink-0 mt-0.5">
                        {proposalTypeLabel(item.type)}
                      </Badge>
                      <span className="text-[var(--text-secondary)] leading-relaxed">{item.summary}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* No active version notice */}
            {!hasActiveVersion && (
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3">
                <p className="text-sm text-amber-400/90 leading-relaxed">
                  Business rules are not yet governing transactions. Approve proposals through conversation to activate your Brain.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
