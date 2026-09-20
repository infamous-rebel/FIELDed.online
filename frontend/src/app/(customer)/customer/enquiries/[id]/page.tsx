"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  enquiries,
  EnquiryData,
  ConversationData,
  MessageData,
  FieldedApiError,
} from "@/lib/api-client";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
  submitted: "bg-blue-500/15 text-blue-400",
  received: "bg-blue-500/15 text-blue-400",
  in_review: "bg-amber-500/15 text-amber-400",
  needs_information: "bg-amber-500/15 text-amber-400",
  declined: "bg-red-500/15 text-red-400",
  cancelled: "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
  expired: "bg-[var(--bg-elevated)] text-[var(--text-muted)]",
  rejected: "bg-red-500/15 text-red-400",
};

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

export default function CustomerEnquiryDetail() {
  const params = useParams();
  const enquiryId = params.id as string;

  const [enquiry, setEnquiry] = useState<EnquiryData | null>(null);
  const [conversation, setConversation] = useState<ConversationData | null>(null);
  const [newMessage, setNewMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  async function loadData() {
    try {
      const [enq, conv] = await Promise.all([
        enquiries.getMyEnquiry(enquiryId),
        enquiries.getConversation(enquiryId),
      ]);
      setEnquiry(enq);
      setConversation(conv);
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
    loadData();
  }, [enquiryId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation?.messages]);

  async function handleSend() {
    if (!newMessage.trim() || sending) return;
    setSending(true);
    try {
      await enquiries.sendMessage(enquiryId, newMessage.trim());
      setNewMessage("");
      // Reload conversation to get updated messages
      const conv = await enquiries.getConversation(enquiryId);
      setConversation(conv);
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      }
    } finally {
      setSending(false);
    }
  }

  async function handleCancel() {
    if (!confirm("Are you sure you want to cancel this enquiry?")) return;
    try {
      const updated = await enquiries.transition(enquiryId, "cancelled");
      setEnquiry(updated);
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      }
    }
  }

  if (loading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Enquiry</h1>
        <p className="mt-4 text-[var(--text-secondary)]">Loading...</p>
      </div>
    );
  }

  if (error && !enquiry) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Enquiry</h1>
        <div className="mt-4 rounded-md bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">
          {error}
        </div>
        <Link href="/customer/enquiries" className="mt-4 text-sm text-[var(--accent)] hover:underline">
          Back to enquiries
        </Link>
      </div>
    );
  }

  if (!enquiry) return null;

  const canCancel = ["draft", "submitted"].includes(enquiry.status);

  return (
    <div>
      <Link href="/customer/enquiries" className="text-sm text-[var(--accent)] hover:underline">
        &larr; Back to enquiries
      </Link>

      {/* Enquiry header */}
      <div className="mt-4 rounded-lg border border-[var(--border-subtle)] p-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-mono text-[var(--text-muted)]">{enquiry.reference}</p>
            <h1 className="mt-1 text-xl font-bold text-[var(--text-primary)]">{enquiry.subject}</h1>
          </div>
          <span
            className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${
              STATUS_COLORS[enquiry.status] || "bg-[var(--bg-elevated)] text-[var(--text-muted)]"
            }`}
          >
            {formatStatus(enquiry.status)}
          </span>
        </div>
        <p className="mt-3 text-sm text-[var(--text-secondary)]">{enquiry.message}</p>
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          Submitted {formatDate(enquiry.created_at)}
        </p>
        {canCancel && (
          <button
            onClick={handleCancel}
            className="mt-3 rounded-md bg-[var(--danger)]/10 px-3 py-1.5 text-xs font-medium text-[var(--danger)] hover:bg-[var(--danger)]/20"
          >
            Cancel Enquiry
          </button>
        )}
      </div>

      {error && (
        <div className="mt-2 rounded-md bg-[var(--danger)]/10 p-2 text-xs text-[var(--danger)]">
          {error}
        </div>
      )}

      {/* Conversation */}
      <div className="mt-6">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">Conversation</h2>
        <div className="mt-3 rounded-lg border border-[var(--border-subtle)]" aria-live="polite">
          {conversation && conversation.messages.length > 0 ? (
            <div className="divide-y divide-[var(--border-subtle)]">
              {conversation.messages.map((msg: MessageData) => (
                <div
                  key={msg.id}
                  className={`p-4 ${
                    msg.sender_type === "customer" ? "bg-[var(--accent)]/5" : "bg-transparent"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-[var(--text-secondary)]">
                      {msg.sender_type === "customer" ? "You" : "Business"}
                    </span>
                    <span className="text-xs text-[var(--text-muted)]">
                      {formatDate(msg.created_at)}
                    </span>
                    {msg.read_at && (
                      <span className="text-xs text-[var(--text-muted)]">Read</span>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-[var(--text-primary)] whitespace-pre-wrap">
                    {msg.content}
                  </p>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          ) : (
            <div className="p-6 text-center text-sm text-[var(--text-muted)]">
              No messages yet. Start the conversation below.
            </div>
          )}

          {/* Message input */}
          <div className="border-t border-[var(--border-subtle)] p-3">
            <div className="flex gap-2">
              <textarea
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                placeholder="Type your message..."
                rows={2}
                className="flex-1 rounded-md border border-[var(--border-default)] px-3 py-2 text-sm focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
              />
              <button
                onClick={handleSend}
                disabled={!newMessage.trim() || sending}
                className="self-end rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--accent-hover)] disabled:opacity-50"
              >
                {sending ? "Sending..." : "Send"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
