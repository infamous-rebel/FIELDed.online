"use client";

import { useEffect, useState, useRef, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from "@stripe/react-stripe-js";
import {
  enquiries,
  quotes,
  bookings,
  invoices,
  serviceExecutions,
  reviews,
  type EnquiryData,
  type ConversationData,
  type MessageData,
  type QuoteData,
  type BookingData,
  type ServiceExecutionData,
  type ReviewData,
  type PaymentData,
  FieldedApiError,
} from "@/lib/api-client";
import { Badge, statusBadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

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

function formatAmount(amount: string, currency: string): string {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(amount));
}

/**
 * Stripe confirmation form — rendered inside <Elements> provider.
 * Shows the Payment Element and a "Confirm Payment" button.
 */
function StripeConfirmButton({
  paymentId,
  onSuccess,
  onError,
  onConfirmingChange,
}: {
  paymentId: string;
  onSuccess: () => void;
  onError: (msg: string) => void;
  onConfirmingChange: (v: boolean) => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [confirming, setConfirming] = useState(false);

  async function handleConfirm() {
    if (!stripe || !elements) return;
    setConfirming(true);
    onConfirmingChange(true);
    try {
      const { error, paymentIntent } = await stripe.confirmPayment({
        elements,
        confirmParams: {
          return_url: typeof window !== "undefined" ? `${window.location.origin}/customer/enquiries` : "",
        },
        redirect: "if_required",
      });
      if (error) {
        onError(error.message || "Payment confirmation failed");
      } else if (paymentIntent?.status === "succeeded") {
        onSuccess();
      } else if (paymentIntent?.status === "processing") {
        onSuccess();
      } else {
        onError(`Unexpected payment status: ${paymentIntent?.status || "unknown"}`);
      }
    } catch (err) {
      onError("Payment confirmation failed");
    } finally {
      setConfirming(false);
      onConfirmingChange(false);
    }
  }

  return (
    <div className="space-y-3">
      <PaymentElement />
      <Button
        variant="primary"
        size="sm"
        onClick={handleConfirm}
        loading={confirming}
        disabled={confirming}
        className="w-full"
      >
        Confirm Payment
      </Button>
    </div>
  );
}

export default function CustomerEnquiryDetail() {
  const params = useParams();
  const enquiryId = params.id as string;

  const [enquiry, setEnquiry] = useState<EnquiryData | null>(null);
  const [conversation, setConversation] = useState<ConversationData | null>(null);
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [booking, setBooking] = useState<BookingData | null>(null);
  const [newMessage, setNewMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [creatingBooking, setCreatingBooking] = useState(false);
  const [paying, setPaying] = useState(false);
  const [acceptingBooking, setAcceptingBooking] = useState(false);
  const [bookingDate, setBookingDate] = useState("");
  const [bookingNotes, setBookingNotes] = useState("");
  const [paymentResult, setPaymentResult] = useState<string | null>(null);
  const [execution, setExecution] = useState<ServiceExecutionData | null>(null);
  const [existingReview, setExistingReview] = useState<ReviewData | null>(null);
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewTitle, setReviewTitle] = useState("");
  const [reviewBody, setReviewBody] = useState("");
  const [submittingReview, setSubmittingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [paymentData, setPaymentData] = useState<PaymentData | null>(null);
  const [confirmingPayment, setConfirmingPayment] = useState(false);
  const [invoicePaid, setInvoicePaid] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Stripe publishable key from environment (public key, safe to expose)
  const stripePromise = useMemo(
    () => (process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ? loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY) : null),
    []
  );

  async function loadData() {
    try {
      const [enq, conv] = await Promise.all([
        enquiries.getMyEnquiry(enquiryId),
        enquiries.getConversation(enquiryId),
      ]);
      setEnquiry(enq);
      setConversation(conv);

      // Load quote for this enquiry
      const allQuotes = await quotes.listMine().catch(() => []);
      const enqQuote = allQuotes.find((q: QuoteData) => q.enquiry_id === enquiryId);
      setQuote(enqQuote || null);

      // Load booking if quote was accepted
      if (enqQuote?.status === "accepted" || ["customer_accepted", "booking_proposed", "booked", "in_progress", "completed"].includes(enq.status)) {
        const allBookings = await bookings.listMine().catch(() => []);
        const enqBooking = allBookings.find((b: BookingData) => b.enquiry_id === enquiryId);
        setBooking(enqBooking || null);

        // Load service execution and review for completed bookings
        if (enqBooking && ["completed", "in_progress", "confirmed"].includes(enqBooking.status)) {
          const execs = await serviceExecutions.listMy().catch(() => []);
          const bookingExec = execs.find((e: ServiceExecutionData) => e.booking_id === enqBooking.id);
          setExecution(bookingExec || null);

          if (bookingExec && bookingExec.status === "completed") {
            const myReviews = await reviews.listMine().catch(() => []);
            const execReview = myReviews.find((r: ReviewData) => r.service_execution_id === bookingExec.id);
            setExistingReview(execReview || null);

            // Check if invoice is already paid
            const myInvoices = await invoices.listMy().catch(() => []);
            const bookingInvoice = myInvoices.find((inv: { booking_id: string }) => inv.booking_id === enqBooking.id);
            setInvoicePaid(bookingInvoice?.payment_status === "paid");
          }
        }
      }
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

  async function handleAcceptQuote() {
    if (!quote) return;
    setAccepting(true);
    setError(null);
    try {
      await quotes.transitionMyQuote(quote.id, "accepted");
      // Reload everything
      await loadData();
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("Failed to accept quote");
      }
    } finally {
      setAccepting(false);
    }
  }

  async function handleDeclineQuote() {
    if (!quote) return;
    if (!confirm("Are you sure you want to decline this quote?")) return;
    setDeclining(true);
    setError(null);
    try {
      await quotes.transitionMyQuote(quote.id, "declined");
      await loadData();
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("Failed to decline quote");
      }
    } finally {
      setDeclining(false);
    }
  }

  async function handleCreateBooking() {
    if (!quote || !bookingDate) return;
    setCreatingBooking(true);
    setError(null);
    try {
      const created = await bookings.create({
        quote_id: quote.id,
        requested_at: new Date(bookingDate).toISOString(),
        notes: bookingNotes.trim() || undefined,
      });
      setBooking(created);
      setBookingDate("");
      setBookingNotes("");
      await loadData();
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("Failed to create booking");
      }
    } finally {
      setCreatingBooking(false);
    }
  }

  async function handleAcceptBooking() {
    if (!booking) return;
    setAcceptingBooking(true);
    setError(null);
    try {
      const updated = await bookings.transitionMyBooking(booking.id, "accepted");
      setBooking(updated);
      await loadData();
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("Failed to accept booking");
      }
    } finally {
      setAcceptingBooking(false);
    }
  }

  async function handlePay() {
    if (!booking) return;
    setPaying(true);
    setError(null);
    setPaymentResult(null);
    setPaymentData(null);
    try {
      const payment = await bookings.payMyBooking(booking.id);
      if (payment.confirmation_required && payment.client_secret) {
        // Stripe two-step flow: show Payment Element for customer confirmation
        setPaymentData(payment);
      } else {
        // Synchronous payment (stub provider or auto-confirmed)
        setPaymentResult(`Payment ${payment.status} — Reference: ${payment.id.slice(0, 8)}`);
        await loadData();
      }
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setError(err.error.message);
      } else {
        setError("Payment failed");
      }
    } finally {
      setPaying(false);
    }
  }

  async function handleReviewSubmit() {
    if (!execution || !reviewTitle.trim()) return;
    setSubmittingReview(true);
    setReviewError(null);
    try {
      await reviews.create({
        service_execution_id: execution.id,
        rating: reviewRating,
        title: reviewTitle.trim(),
        body: reviewBody.trim() || undefined,
      });
      setExistingReview({ id: "new", rating: reviewRating, title: reviewTitle.trim(), body: reviewBody.trim(), status: "visible" } as ReviewData);
      setReviewTitle("");
      setReviewBody("");
    } catch (err) {
      if (err instanceof FieldedApiError) {
        setReviewError(err.error.message);
      } else {
        setReviewError("Failed to submit review");
      }
    } finally {
      setSubmittingReview(false);
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
  const showQuote = quote && ["quoted", "customer_accepted", "booking_proposed", "booked", "in_progress", "completed"].includes(enquiry.status);
  const showBookingForm = quote?.status === "accepted" && !booking;
  const showBooking = booking;
  const showPayment = booking && booking.status === "completed" && !paymentResult && !paymentData && !invoicePaid;

  // Journey stage calculation
  const journeyStages = [
    { label: "Enquiry", active: true, color: "var(--accent)" },
    { label: "Quote", active: !!quote, color: "var(--info)" },
    { label: "Booking", active: !!booking, color: "var(--warning)" },
    { label: "Service", active: !!execution, color: "var(--accent)" },
    { label: "Review", active: !!existingReview, color: "var(--accent)" },
  ];

  return (
    <div className="space-y-5">
      <Link href="/customer/enquiries" className="inline-flex items-center gap-1 text-sm text-[var(--accent)] hover:underline transition-colors">
        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to enquiries
      </Link>

      {/* Journey progress strip */}
      <div className="glass rounded-lg p-4">
        <div className="flex items-center gap-2">
          {journeyStages.map((stage, i) => (
            <div key={stage.label} className="flex items-center gap-2 flex-1">
              <div className="flex items-center gap-1.5 flex-1">
                <span
                  className="h-2 w-2 rounded-full flex-shrink-0"
                  style={{
                    backgroundColor: stage.active ? stage.color : "var(--border-default)",
                    opacity: stage.active ? 1 : 0.4,
                  }}
                />
                <span className={`text-[10px] font-medium uppercase tracking-wider ${
                  stage.active ? "text-[var(--text-primary)]" : "text-[var(--text-muted)]"
                }`}>
                  {stage.label}
                </span>
              </div>
              {i < journeyStages.length - 1 && (
                <svg className="h-3 w-3 text-[var(--border-default)] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              )}
            </div>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]" role="alert">
          {error}
        </div>
      )}

      {paymentResult && (
        <div className="rounded-lg border border-green-500/30 bg-green-500/10 p-3 text-sm text-green-400" role="alert">
          {paymentResult}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Conversation — main area */}
        <div className="lg:col-span-2">
          <Card padding="sm">
            <div className="border-b border-white/[0.06] p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-[var(--text-primary)]">Conversation</h2>
                <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">
                  {conversation?.messages?.length || 0} messages
                </span>
              </div>
            </div>

            {/* Messages */}
            <div className="max-h-[500px] overflow-y-auto" aria-live="polite">
              {conversation && conversation.messages.length > 0 ? (
                <div className="divide-y divide-white/[0.04]">
                  {conversation.messages.map((msg: MessageData) => (
                    <div
                      key={msg.id}
                      className={`p-4 transition-colors ${
                        msg.sender_type === "customer" ? "bg-[var(--accent)]/[0.03]" : ""
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-[var(--text-primary)]">
                          {msg.sender_type === "customer" ? "You" : "Business"}
                        </span>
                        <span className="text-xs text-[var(--text-muted)]">
                          {formatDate(msg.created_at)}
                        </span>
                        {msg.read_at && (
                          <span className="text-xs text-[var(--text-muted)]">Read</span>
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
            <div className="border-t border-white/[0.06] px-3 py-2.5">
              <textarea
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                placeholder="Type your message..."
                rows={2}
                className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
              />
              <div className="mt-1.5 flex items-center justify-end">
                <button
                  onClick={handleSend}
                  disabled={!newMessage.trim() || sending}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-[var(--accent)] hover:bg-[var(--accent)]/10 disabled:opacity-40 disabled:hover:bg-transparent transition-colors"
                >
                  {sending ? (
                    <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                  ) : (
                    <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>
                  )}
                  {sending ? "Sending…" : "Send"}
                </button>
              </div>
            </div>
          </Card>
        </div>

        {/* Sidebar — enquiry info, quote, booking, payment */}
        <div className="space-y-3">
          {/* Enquiry header */}
          <Card>
            <p className="text-xs font-mono text-[var(--text-muted)]">{enquiry.reference}</p>
            <h1 className="mt-1 text-lg font-bold text-[var(--text-primary)]">{enquiry.subject}</h1>
            <div className="mt-3">
              <Badge variant={statusBadgeVariant(enquiry.status)}>
                {formatStatus(enquiry.status)}
              </Badge>
            </div>
            <p className="mt-3 text-sm text-[var(--text-secondary)]">{enquiry.message}</p>
            <p className="mt-3 text-xs text-[var(--text-muted)]">
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
          </Card>

          {/* Quote card */}
          {showQuote && quote && (
            <Card>
              <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide">Quote</h3>
              <p className="mt-1 text-xs font-mono text-[var(--text-muted)]">{quote.reference}</p>
              <p className="mt-2 text-2xl font-bold text-[var(--text-primary)]">
                {formatAmount(quote.amount, quote.currency)}
              </p>
              <div className="mt-2">
                <Badge variant={statusBadgeVariant(quote.status)}>
                  {formatStatus(quote.status)}
                </Badge>
              </div>
              {quote.notes && (
                <p className="mt-3 text-sm text-[var(--text-secondary)]">{quote.notes}</p>
              )}

              {/* Accept / Decline */}
              {quote.status === "issued" && (
                <div className="mt-4 flex gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleAcceptQuote}
                    loading={accepting}
                    disabled={accepting || declining}
                    className="flex-1"
                  >
                    Accept Quote
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={handleDeclineQuote}
                    loading={declining}
                    disabled={accepting || declining}
                  >
                    Decline
                  </Button>
                </div>
              )}

              {quote.status === "accepted" && (
                <p className="mt-3 text-xs text-green-400">You accepted this quote. Create a booking below.</p>
              )}
              {quote.status === "declined" && (
                <p className="mt-3 text-xs text-[var(--danger)]">You declined this quote.</p>
              )}
            </Card>
          )}

          {/* Booking creation form */}
          {showBookingForm && (
            <Card>
              <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide">Create Booking</h3>
              <p className="mt-2 text-xs text-[var(--text-secondary)]">
                Choose when you&apos;d like the service. The business will confirm the exact time.
              </p>
              <div className="mt-3 space-y-3">
                <div>
                  <label htmlFor="booking-datetime" className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
                    Preferred date &amp; time
                  </label>
                  <div className="relative z-10">
                    <input
                      id="booking-datetime"
                      name="booking-datetime"
                      type="datetime-local"
                      value={bookingDate}
                      min={new Date().toISOString().slice(0, 16)}
                      onChange={(e) => setBookingDate(e.target.value)}
                      className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
                    Notes (optional)
                  </label>
                  <textarea
                    value={bookingNotes}
                    onChange={(e) => setBookingNotes(e.target.value)}
                    placeholder="Any specific requirements..."
                    rows={2}
                    className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none"
                  />
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleCreateBooking}
                  loading={creatingBooking}
                  disabled={creatingBooking || !bookingDate}
                  className="w-full"
                >
                  Request Booking
                </Button>
              </div>
            </Card>
          )}

          {/* Booking status */}
          {showBooking && booking && (
            <Card>
              <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide">Booking</h3>
              <p className="mt-1 text-xs font-mono text-[var(--text-muted)]">{booking.reference}</p>
              <div className="mt-2">
                <Badge variant={statusBadgeVariant(booking.status)}>
                  {formatStatus(booking.status)}
                </Badge>
              </div>
              <p className="mt-2 text-xs text-[var(--text-secondary)]">
                Requested: {formatDate(booking.requested_at)}
              </p>
              {booking.notes && (
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{booking.notes}</p>
              )}

              {/* Accept proposed booking */}
              {booking.status === "proposed" && (
                <div className="mt-4 border-t border-[var(--border-subtle)] pt-3">
                  <p className="text-sm text-[var(--text-secondary)] mb-2">
                    The business has proposed this booking. Accept to proceed.
                  </p>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleAcceptBooking}
                    loading={acceptingBooking}
                    disabled={acceptingBooking}
                    className="w-full"
                  >
                    Accept Booking
                  </Button>
                </div>
              )}

              {/* Awaiting business confirmation */}
              {booking.status === "accepted" && (
                <p className="mt-3 text-xs text-[var(--accent)]">
                  Booking accepted. Awaiting business confirmation.
                </p>
              )}

              {/* Confirmed */}
              {booking.status === "confirmed" && (
                <p className="mt-3 text-xs text-green-400">
                  Booking confirmed! The business will perform the service.
                </p>
              )}

              {/* In progress */}
              {booking.status === "in_progress" && (
                <p className="mt-3 text-xs text-[var(--accent)]">
                  Service is in progress.
                </p>
              )}

              {/* Pay button for completed bookings */}
              {showPayment && (
                <div className="mt-4 border-t border-[var(--border-subtle)] pt-3">
                  <p className="text-sm text-[var(--text-secondary)] mb-2">
                    Service completed. Amount due:{" "}
                    <span className="font-bold text-[var(--text-primary)]">
                      {formatAmount(quote?.amount || "0", quote?.currency || "USD")}
                    </span>
                  </p>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handlePay}
                    loading={paying}
                    disabled={paying}
                    className="w-full"
                  >
                    Pay Now
                  </Button>
                </div>
              )}

              {booking.status === "completed" && !showPayment && paymentResult && (
                <div className="mt-3 rounded-md bg-green-500/10 p-2 text-xs text-green-400">
                  Payment completed
                </div>
              )}

              {/* Stripe Payment Element — shown when payment requires customer confirmation */}
              {paymentData?.confirmation_required && paymentData.client_secret && stripePromise && (
                <div className="mt-4 border-t border-[var(--border-subtle)] pt-3">
                  <p className="text-sm text-[var(--text-secondary)] mb-2">
                    Complete your payment of{" "}
                    <span className="font-bold text-[var(--text-primary)]">
                      {formatAmount(paymentData.amount, paymentData.currency)}
                    </span>
                  </p>
                  <Elements
                    stripe={stripePromise}
                    options={{
                      clientSecret: paymentData.client_secret,
                      appearance: {
                        theme: "night",
                        variables: { colorPrimary: "#3b82f6", colorBackground: "#1a1a2e" },
                      },
                    }}
                    key={paymentData.client_secret}
                  >
                    <StripeConfirmButton
                      paymentId={paymentData.id}
                      onSuccess={async () => {
                        setPaymentResult("Payment succeeded");
                        setPaymentData(null);
                        await loadData();
                      }}
                      onError={(msg) => setError(msg)}
                      onConfirmingChange={setConfirmingPayment}
                    />
                  </Elements>
                </div>
              )}

              {/* Fallback: payment processing awaiting webhook */}
              {paymentData && paymentData.status === "processing" && !paymentData.confirmation_required && (
                <div className="mt-3 rounded-md bg-amber-500/10 p-2 text-xs text-amber-400">
                  Payment processing — waiting for confirmation.
                </div>
              )}
            </Card>
          )}

          {/* Review section — shown when service is completed */}
          {execution?.status === "completed" && (
            <Card>
              <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide">Review</h3>
              {existingReview ? (
                <div className="mt-3">
                  <div className="flex items-center gap-0.5 text-amber-400">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <span key={i} className={i < existingReview.rating ? "opacity-100" : "opacity-30"}>&#9733;</span>
                    ))}
                  </div>
                  {existingReview.title && (
                    <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">{existingReview.title}</p>
                  )}
                  {existingReview.body && (
                    <p className="mt-1 text-sm text-[var(--text-secondary)]">{existingReview.body}</p>
                  )}
                  <p className="mt-2 text-xs text-green-400">Thank you for your review!</p>
                </div>
              ) : (
                <div className="mt-3 space-y-3">
                  <p className="text-xs text-[var(--text-secondary)]">
                    The service has been completed. Share your experience.
                  </p>
                  {reviewError && (
                    <div className="rounded-md bg-[var(--danger)]/10 p-2 text-xs text-[var(--danger)]">{reviewError}</div>
                  )}
                  <div>
                    <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1">Rating</label>
                    <div className="flex gap-1">
                      {[1, 2, 3, 4, 5].map((star) => (
                        <button
                          key={star}
                          type="button"
                          onClick={() => setReviewRating(star)}
                          className={`text-2xl transition-opacity ${star <= reviewRating ? "text-amber-400 opacity-100" : "text-amber-400 opacity-30"}`}
                        >
                          &#9733;
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1">Title</label>
                    <input
                      type="text"
                      value={reviewTitle}
                      onChange={(e) => setReviewTitle(e.target.value)}
                      placeholder="Summarize your experience"
                      className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1">Details (optional)</label>
                    <textarea
                      value={reviewBody}
                      onChange={(e) => setReviewBody(e.target.value)}
                      placeholder="Tell us more about your experience..."
                      rows={3}
                      className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none"
                    />
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleReviewSubmit}
                    loading={submittingReview}
                    disabled={submittingReview || !reviewTitle.trim()}
                    className="w-full"
                  >
                    Submit Review
                  </Button>
                </div>
              )}
            </Card>
          )}

          {/* Status guide */}
          <div className="glass rounded-lg p-4">
            <h4 className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">What happens next?</h4>
            <ul className="space-y-1.5 text-xs text-[var(--text-secondary)]">
              {enquiry.status === "submitted" && <li>The business will review your enquiry.</li>}
              {enquiry.status === "received" && <li>The business is reviewing your enquiry.</li>}
              {enquiry.status === "in_review" && <li>The business is preparing a response.</li>}
              {enquiry.status === "needs_information" && <li>The business needs more information. Send a message above.</li>}
              {enquiry.status === "quoted" && <li>The business has sent you a quote. Review it in the sidebar.</li>}
              {enquiry.status === "customer_accepted" && !booking && <li>You accepted the quote. Request a booking time above.</li>}
              {enquiry.status === "customer_accepted" && booking?.status === "requested" && <li>Booking requested. The business will propose a time.</li>}
              {enquiry.status === "customer_accepted" && booking?.status === "proposed" && <li>The business proposed a time. Accept the booking above.</li>}
              {enquiry.status === "customer_accepted" && booking?.status === "accepted" && <li>You accepted the booking. The business will confirm.</li>}
              {enquiry.status === "booked" && <li>Your booking is confirmed. The business will complete the service.</li>}
              {enquiry.status === "in_progress" && <li>The service is being performed.</li>}
              {enquiry.status === "completed" && !existingReview && <li>Service completed! Leave a review in the sidebar.</li>}
              {enquiry.status === "completed" && existingReview && <li>Service completed. Thank you for your review!</li>}
              {enquiry.status === "declined" && <li>The business declined this enquiry.</li>}
              {enquiry.status === "cancelled" && <li>This enquiry was cancelled.</li>}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
