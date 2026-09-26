"use client";

import { useEffect, useState, useCallback } from "react";
import {
  businesses,
  voice,
  type BusinessSummary,
  type VoiceCallData,
  type CallAgentConfigData,
  type AgentTurnResponse,
} from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { statusToBadgeVariant } from "@/lib/status";

export default function CallAgentPage() {
  const [bizList, setBizList] = useState<BusinessSummary[]>([]);
  const [selectedBiz, setSelectedBiz] = useState<string>("");
  const [calls, setCalls] = useState<VoiceCallData[]>([]);
  const [config, setConfig] = useState<CallAgentConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [callsLoading, setCallsLoading] = useState(false);

  // New call form
  const [newPhone, setNewPhone] = useState("");
  const [newPurpose, setNewPurpose] = useState("booking_reminder");
  const [newCallType, setNewCallType] = useState("OUTBOUND");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  // Conversation panel
  const [selectedCall, setSelectedCall] = useState<VoiceCallData | null>(null);
  const [utterance, setUtterance] = useState("");
  const [turnHistory, setTurnHistory] = useState<AgentTurnResponse[]>([]);
  const [sendingTurn, setSendingTurn] = useState(false);

  useEffect(() => {
    async function loadBiz() {
      try {
        const bizData = await businesses.list();
        setBizList(bizData);
        if (bizData.length > 0) {
          setSelectedBiz(bizData[0].id);
        }
      } catch {
        // Auth error — page stays empty
      } finally {
        setLoading(false);
      }
    }
    loadBiz();
  }, []);

  const loadCalls = useCallback(async () => {
    if (!selectedBiz) return;
    setCallsLoading(true);
    try {
      const [callsData, configData] = await Promise.all([
        voice.listCalls(selectedBiz, { limit: 50 }).catch(() => [] as VoiceCallData[]),
        voice.getAgentConfig(selectedBiz).catch(() => null),
      ]);
      setCalls(callsData);
      setConfig(configData);
    } finally {
      setCallsLoading(false);
    }
  }, [selectedBiz]);

  useEffect(() => {
    if (selectedBiz) {
      loadCalls();
    }
  }, [selectedBiz, loadCalls]);

  const handleCreateCall = async () => {
    if (!selectedBiz || !newPhone.trim()) return;
    setCreating(true);
    setCreateError("");
    try {
      const call = await voice.createCall(selectedBiz, {
        to_number: newPhone.trim(),
        purpose: newPurpose,
        call_type: newCallType,
        initiate: false, // Create but don't initiate (no Twilio configured in prod yet)
      });
      setCalls((prev) => [call, ...prev]);
      setNewPhone("");
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create call");
    } finally {
      setCreating(false);
    }
  };

  const handleCancelCall = async (callId: string) => {
    if (!selectedBiz) return;
    try {
      await voice.cancelCall(selectedBiz, callId, "Cancelled from dashboard");
      await loadCalls();
    } catch {
      // Show error
    }
  };

  const handleSelectCall = async (call: VoiceCallData) => {
    setSelectedCall(call);
    setTurnHistory([]);
  };

  const handleSendTurn = async () => {
    if (!selectedBiz || !selectedCall || !utterance.trim()) return;
    setSendingTurn(true);
    try {
      const response = await voice.agentTurn(selectedBiz, selectedCall.id, utterance.trim());
      setTurnHistory((prev) => [...prev, response]);
      setUtterance("");
      // Refresh call status
      const updatedCall = await voice.getCall(selectedBiz, selectedCall.id);
      setSelectedCall(updatedCall);
    } catch {
      // Error handling
    } finally {
      setSendingTurn(false);
    }
  };

  if (loading) {
    return <LoadingSkeleton lines={5} />;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Call Agent</h1>
          <p className="mt-1 text-[var(--text-secondary)]">
            Manage voice calls, agent conversations, and call campaigns.
          </p>
        </div>
        {bizList.length > 1 && (
          <select
            value={selectedBiz}
            onChange={(e) => setSelectedBiz(e.target.value)}
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
          >
            {bizList.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Configuration status */}
      <Card>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Agent Status</h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              {config
                ? config.enabled
                  ? "Call Agent is enabled"
                  : "Call Agent is disabled"
                : "Call Agent not configured"}
            </p>
          </div>
          <Badge variant={config?.enabled ? "success" : "muted"}>
            {config?.enabled ? "Active" : "Inactive"}
          </Badge>
        </div>
        {config?.default_from_number && (
          <p className="mt-2 text-xs text-[var(--text-secondary)]">
            From: {config.default_from_number}
          </p>
        )}
      </Card>

      {/* New call form */}
      <Card>
        <h2 className="text-sm font-semibold text-[var(--text-primary)] mb-3">New Call</h2>
        <div className="grid gap-3 sm:grid-cols-4">
          <input
            type="tel"
            placeholder="Phone number (e.g. +44...)"
            value={newPhone}
            onChange={(e) => setNewPhone(e.target.value)}
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
          />
          <select
            value={newPurpose}
            onChange={(e) => setNewPurpose(e.target.value)}
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
          >
            <option value="booking_reminder">Booking Reminder</option>
            <option value="follow_up">Follow Up</option>
            <option value="confirmation">Confirmation</option>
            <option value="general">General</option>
          </select>
          <select
            value={newCallType}
            onChange={(e) => setNewCallType(e.target.value)}
            className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]"
          >
            <option value="OUTBOUND">Outbound</option>
            <option value="INBOUND">Inbound</option>
          </select>
          <button
            onClick={handleCreateCall}
            disabled={creating || !newPhone.trim()}
            className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {creating ? "Creating..." : "Create Call"}
          </button>
        </div>
        {createError && (
          <p className="mt-2 text-xs text-red-600">{createError}</p>
        )}
      </Card>

      {/* Calls list + conversation panel */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Calls list */}
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-3">
            Recent Calls
          </h2>
          {callsLoading ? (
            <LoadingSkeleton lines={3} />
          ) : calls.length === 0 ? (
            <EmptyState
              title="No calls yet"
              description="Create a call above to get started."
            />
          ) : (
            <div className="space-y-2">
              {calls.map((call) => (
                <Card
                  key={call.id}
                  padding="sm"
                  hover
                  className={selectedCall?.id === call.id ? "ring-2 ring-[var(--accent)]" : ""}
                >
                  <button
                    onClick={() => handleSelectCall(call)}
                    className="w-full text-left"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-[var(--text-primary)]">
                          {call.to_number}
                        </p>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5">
                          {call.purpose.replace(/_/g, " ")} &middot; {call.call_type} &middot;{" "}
                          {new Date(call.created_at).toLocaleString()}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={statusToBadgeVariant(call.status)}>
                          {call.status.replace(/_/g, " ")}
                        </Badge>
                        {["REQUESTED", "AUTHORIZED"].includes(call.status) && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCancelCall(call.id);
                            }}
                            className="text-xs text-red-600 hover:underline"
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </div>
                  </button>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Conversation panel */}
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-3">
            {selectedCall ? "Conversation" : "Select a Call"}
          </h2>
          {!selectedCall ? (
            <Card>
              <EmptyState
                title="No call selected"
                description="Select a call from the list to view or start a conversation."
              />
            </Card>
          ) : (
            <div className="space-y-4">
              {/* Call details */}
              <Card padding="sm">
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-[var(--text-muted)]">Status:</span>{" "}
                    <Badge variant={statusToBadgeVariant(selectedCall.status)}>
                      {selectedCall.status.replace(/_/g, " ")}
                    </Badge>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)]">Provider:</span>{" "}
                    <span className="text-[var(--text-primary)]">{selectedCall.provider}</span>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)]">To:</span>{" "}
                    <span className="text-[var(--text-primary)]">{selectedCall.to_number}</span>
                  </div>
                  <div>
                    <span className="text-[var(--text-muted)]">Created:</span>{" "}
                    <span className="text-[var(--text-primary)]">
                      {new Date(selectedCall.created_at).toLocaleString()}
                    </span>
                  </div>
                </div>
              </Card>

              {/* Turn history */}
              {turnHistory.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-sm font-medium text-[var(--text-primary)]">
                    Agent Replies
                  </h3>
                  {turnHistory.map((turn, idx) => (
                    <Card key={idx} padding="sm">
                      <p className="text-sm text-[var(--text-primary)]">{turn.reply}</p>
                      <div className="mt-1 flex gap-2 text-xs text-[var(--text-muted)]">
                        <span>Action: {turn.action}</span>
                        {turn.outcome && <span>Outcome: {turn.outcome}</span>}
                        <span>Turn {turn.turn_count}</span>
                      </div>
                    </Card>
                  ))}
                </div>
              )}

              {/* Conversation input */}
              <Card>
                <textarea
                  value={utterance}
                  onChange={(e) => setUtterance(e.target.value)}
                  placeholder="Type a message for the Call Agent..."
                  rows={2}
                  className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1.5 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] resize-none"
                />
                <div className="mt-1.5 flex items-center justify-end">
                  <button
                    onClick={handleSendTurn}
                    disabled={sendingTurn || !utterance.trim()}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-[var(--accent)] hover:bg-[var(--accent)]/10 disabled:opacity-40 disabled:hover:bg-transparent transition-colors"
                  >
                    {sendingTurn ? (
                      <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                    ) : (
                      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>
                    )}
                    {sendingTurn ? "Sending…" : "Send"}
                  </button>
                </div>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
