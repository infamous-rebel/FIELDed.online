"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import {
  businesses,
  enquiries,
  quotes,
  type EnquiryData,
  type ConversationData,
  type MessageData,
  type QuoteData,
  FieldedApiError,
} from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge, statusBadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

const TRANSITION_OPTIONS: Record<string, { label: string; target: string; variant: "primary" | "secondary" | "danger" }[]> = {
  submitted: [
    { label: "Mark Received", target: "received", variant: "primary" },
    { label: "Decline", target: "declined", variant: "danger" },
  ],
  received: [
    { label: "Start Review", target: "in_review", variant: "primary" },
    { label: "Decline", target: "declined", variant: "danger" },
  ],
  in_review: [
    { label: "Request Info", target: "needs_information", variant: "secondary" },
    { label: "Decline", target: "declined", variant: "danger" },
  ],
  needs_information: [
    { label: "Resume Review", target: "in_review", variant: "primary" },
    { label: "Decline", target: "declined", variant: "danger" },
  ],
};

// Enquiry states where a quote can be created
const QUOTABLE_STATES = new Set(["received", "in_review", "needs_information"]);

function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function BusinessEnquiryDetailPage() {
  const params = useParams();
  const enquiryId = params.id as string;

  const [businessId, setBusinessId] = useState<string | null>(null);
  const [enquiry, setEnquiry] = useState<EnquiryData | null>(null);
  const [conversation, setConversation] = useState<ConversationData | null>(null);
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [newMessage, setNewMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creatingQuote, setCreatingQuote] = useState(false);
  const [issuingQuote, setIssuingQuote] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Resolve business ID client-side (same pattern as enquiries list)
  useEffect(() => {
    async function resolveBusiness() {
      try {
        const bizList = await businesses.list();
        if (bizList.length > 0) {
          setBusinessId(bizList[0].id);
        } else {
          setError("No business found for this account.");
          setLoading(false);
        }
      } catch {
        setError("Failed to resolve business.");
        setLoading(false);
      }
    }
    resolveBusiness();
  }, []);

  async function loadData() {
    if (!businessId) return;
    try {
      const [enq, conv, quoteList] = await Promise.all([
        enquiries.getBusinessEnquiry(businessId, enquiryId),
        enquiries.getBusinessConversation(businessId, enquiryId),
        quotes.listForBusiness(businessId).catch(() => []),
      ]);
      setEnquiry(enq);
      setConversation(conv);
      // Find the quote for this enquiry
      const enqQuote = quoteList.find((q: QuoteData) => q.enquiry_id === enquiryId);
      setQuote(enqQuote || null);
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("Failed to load enquiry");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (businessId) {
      loadData();
    }
  }, [businessId, enquiryId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation?.messages]);

  async function handleSend() {
    if (!newMessage.trim() || sending || !businessId) return;
    setSending(true);
    try {
      await enquiries.sendBusinessMessage(businessId, enquiryId, newMessage.trim());
      setNewMessage("");
      const conv = await enquiries.getBusinessConversation(businessId, enquiryId);
      setConversation(conv);
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      }
    } finally {
      setSending(false);
    }
  }

  async function handleTransition(targetStatus: string) {
    if (!businessId) return;
    try {
      const updated = await enquiries.transitionBusiness(businessId, enquiryId, targetStatus);
      setEnquiry(updated);
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      }
    }
  }

  async function handleCreateQuote() {
    if (!businessId || !enquiry) return;
    setCreatingQuote(true);
    setError(null);
    try {
      const created = await quotes.create(businessId, { enquiry_id: enquiryId });
      setQuote(created);
      // Reload to get updated enquiry status (now QUOTED)
      await loadData();
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("Failed to create quote");
      }
    } finally {
      setCreatingQuote(false);
    }
  }

  async function handleIssueQuote() {
    if (!businessId || !quote) return;
    setIssuingQuote(true);
    setError(null);
    try {
      const issued = await quotes.transitionBusiness(businessId, quote.id, "issued");
      setQuote(issued);
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("Failed to issue quote");
      }
    } finally {
      setIssuingQuote(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <LoadingSkeleton variant="card" />
        <LoadingSkeleton variant="card" />
      </div>
    );
  }

  if (error && !enquiry) {
    return (
      <div className="space-y-4">
        <div
          className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]"
          role="alert"
        >
          {error}
        </div>
        <a
          href="/business/enquiries"
          className="text-sm text-[var(--accent)] hover:underline"
        >
          &larr; Back to enquiries
        </a>
      </div>
    );
  }

  if (!enquiry) return null;

  const transitions = TRANSITION_OPTIONS[enquiry.status] || [];

  return (
    <div className="space-y-6">
      <a
        href="/business/enquiries"
        className="text-sm text-[var(--accent)] hover:underline"
      >
        &larr; Back to enquiries
      </a>

      {error && (
        <div
          className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]"
          role="alert"
        >
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Conversation — main area */}
        <div className="lg:col-span-2">
          <Card padding="sm">
            <div className="border-b border-[var(--border-subtle)] p-4">
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                Conversation
              </h2>
            </div>

            {/* Messages */}
            <div className="max-h-[500px] overflow-y-auto" aria-live="polite">
              {conversation && conversation.messages.length > 0 ? (
                <div className="divide-y divide-[var(--border-subtle)]">
                  {conversation.messages.map((msg: MessageData) => (
                    <div
                      key={msg.id}
                      className={`p-4 ${
                        msg.sender_type === "business"
                          ? "bg-[var(--accent)]/5"
                          : ""
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-[var(--text-primary)]">
                          {msg.sender_type === "business"
                            ? "You (Business)"
                            : "Customer"}
                        </span>
                        <span className="text-xs text-[var(--text-muted)]">
                          {formatDate(msg.created_at)}
                        </span>
                        {msg.read_at && (
                          <span className="text-xs text-[var(--text-muted)]">
                            Read
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-sm text-[var(--text-secondary)] whitespace-pre-wrap">
                        {msg.content}
                      </p>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              ) : (
                <div className="p-8 text-center text-sm text-[var(--text-muted)]">
                  No messages yet. Start the conversation below.
                </div>
              )}
            </div>

            {/* Message input */}
            <div className="border-t border-[var(--border-subtle)] p-3">
              <div className="flex gap-2">
                <textarea
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  placeholder="Type your reply..."
                  rows={2}
                  className="flex-1 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                />
                <Button
                  onClick={handleSend}
                  disabled={!newMessage.trim() || sending}
                  loading={sending}
                  className="self-end"
                >
                  Reply
                </Button>
              </div>
            </div>
          </Card>
        </div>

        {/* Enquiry header — sidebar */}
        <div className="space-y-4">
          <Card>
            <p className="text-xs font-mono text-[var(--text-muted)]">
              {enquiry.reference}
            </p>
            <h1 className="mt-1 text-lg font-bold text-[var(--text-primary)]">
              {enquiry.subject}
            </h1>
            <div className="mt-3">
              <Badge variant={statusBadgeVariant(enquiry.status)}>
                {formatStatus(enquiry.status)}
              </Badge>
            </div>
            <p className="mt-3 text-sm text-[var(--text-secondary)]">
              {enquiry.message}
            </p>
            <p className="mt-3 text-xs text-[var(--text-muted)]">
              Received {formatDate(enquiry.created_at)}
            </p>

            {/* Transition buttons */}
            {transitions.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {transitions.map((t) => (
                  <Button
                    key={t.target}
                    variant={t.variant}
                    size="sm"
                    onClick={() => handleTransition(t.target)}
                  >
                    {t.label}
                  </Button>
                ))}
              </div>
            )}

            {/* Create / Issue quote */}
            {QUOTABLE_STATES.has(enquiry.status) && !quote && (
              <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleCreateQuote}
                  loading={creatingQuote}
                  disabled={creatingQuote}
                >
                  Create Quote
                </Button>
                <p className="mt-2 text-xs text-[var(--text-muted)]">
                  Pricing is calculated from your service offer and active pricing rules.
                </p>
              </div>
            )}

            {/* Quote card — shown once created */}
            {quote && (
              <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
                <p className="text-xs font-mono text-[var(--text-muted)]">{quote.reference}</p>
                <p className="mt-1 text-lg font-bold text-[var(--text-primary)]">
                  {new Intl.NumberFormat(undefined, { style: "currency", currency: quote.currency }).format(Number(quote.amount))}
                </p>
                <div className="mt-1">
                  <Badge variant={statusBadgeVariant(quote.status)}>
                    {formatStatus(quote.status)}
                  </Badge>
                </div>
                {quote.notes && (
                  <p className="mt-2 text-xs text-[var(--text-secondary)]">{quote.notes}</p>
                )}
                {quote.status === "draft" && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleIssueQuote}
                    loading={issuingQuote}
                    disabled={issuingQuote}
                    className="mt-3"
                  >
                    Issue Quote to Customer
                  </Button>
                )}
                {quote.status === "issued" && (
                  <p className="mt-2 text-xs text-[var(--accent)]">
                    Quote sent to customer. Awaiting their response.
                  </p>
                )}
                {quote.status === "accepted" && (
                  <p className="mt-2 text-xs text-green-400">
                    Customer accepted this quote.
                  </p>
                )}
                {quote.status === "declined" && (
                  <p className="mt-2 text-xs text-[var(--danger)]">
                    Customer declined this quote.
                  </p>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
