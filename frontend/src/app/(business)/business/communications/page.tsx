"use client";

import { useEffect, useState, useCallback } from "react";
import {
  businesses,
  communications,
  voice,
  type BusinessSummary,
  type ChannelConfigData,
  type PurposeConfigData,
  type CallAgentConfigData,
  type VoiceCallData,
  type EscalationData,
} from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { EmptyState } from "@/components/ui/empty-state";

type TabId = "overview" | "agent" | "calls";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "agent", label: "Call Agent" },
  { id: "calls", label: "Calls" },
];

export default function CommunicationsPage() {
  const [bizList, setBizList] = useState<BusinessSummary[]>([]);
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function init() {
      try {
        const data = await businesses.list();
        setBizList(data);
      } catch {
        // API error
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  const businessId = bizList[0]?.id;

  if (loading) {
    return <LoadingSkeleton variant="card" />;
  }

  if (!businessId) {
    return (
      <EmptyState
        title="No business found"
        description="Create a business to configure communications."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          Communications
        </h1>
        <p className="mt-1 text-[var(--text-secondary)]">
          Manage voice, messaging, and call agent configuration
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-[var(--border-subtle)]">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-[var(--accent)] text-[var(--accent)]"
                : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "overview" && <OverviewTab businessId={businessId} />}
      {activeTab === "agent" && <AgentTab businessId={businessId} />}
      {activeTab === "calls" && <CallsTab businessId={businessId} />}
    </div>
  );
}

/* ── Overview Tab ── */

function OverviewTab({ businessId }: { businessId: string }) {
  const [channels, setChannels] = useState<ChannelConfigData[]>([]);
  const [purposes, setPurposes] = useState<PurposeConfigData[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const [ch, pu] = await Promise.all([
        communications.listChannels(businessId),
        communications.listPurposes(businessId),
      ]);
      setChannels(ch);
      setPurposes(pu);
    } catch {
      // API error
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleToggleChannel = async (channel: string, enabled: boolean) => {
    try {
      await communications.upsertChannel(businessId, channel, { enabled });
      await loadData();
    } catch (err) {
      console.error("Failed to update channel:", err);
    }
  };

  const handleTogglePurpose = async (purpose: string, enabled: boolean) => {
    try {
      await communications.upsertPurpose(businessId, purpose, { enabled });
      await loadData();
    } catch (err) {
      console.error("Failed to update purpose:", err);
    }
  };

  if (loading) return <LoadingSkeleton lines={4} />;

  const enabledChannels = channels.filter((c) => c.enabled).length;

  return (
    <div className="space-y-6">
      {/* Status summary */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <p className="text-sm text-[var(--text-muted)]">Active Channels</p>
          <p className="mt-1 text-2xl font-bold text-[var(--text-primary)]">
            {enabledChannels} / {channels.length || "0"}
          </p>
        </Card>
        <Card>
          <p className="text-sm text-[var(--text-muted)]">Active Purposes</p>
          <p className="mt-1 text-2xl font-bold text-[var(--text-primary)]">
            {purposes.filter((p) => p.enabled).length} / {purposes.length || "0"}
          </p>
        </Card>
        <Card>
          <p className="text-sm text-[var(--text-muted)]">Provider Status</p>
          <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
            {channels.some((c) => c.provider_ref) ? (
              <span className="text-emerald-400">Configured</span>
            ) : (
              <span className="text-[var(--text-muted)]">Not configured</span>
            )}
          </p>
        </Card>
      </div>

      {/* Channels */}
      <Card>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
          Communication Channels
        </h3>
        {channels.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)] py-4">
            No channels configured. Channels are created when you configure a provider.
          </p>
        ) : (
          <div className="space-y-3">
            {channels.map((ch) => (
              <div
                key={ch.id}
                className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] p-3"
              >
                <div className="flex items-center gap-3">
                  <ChannelIcon channel={ch.channel} />
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">
                      {formatChannelName(ch.channel)}
                    </p>
                    <p className="text-xs text-[var(--text-muted)]">
                      {ch.provider_ref ? `Provider: ${ch.provider_ref}` : "No provider"}
                    </p>
                  </div>
                </div>
                <ToggleSwitch
                  checked={ch.enabled}
                  onChange={(v) => handleToggleChannel(ch.channel, v)}
                  label={ch.enabled ? "Enabled" : "Disabled"}
                />
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Purposes */}
      <Card>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
          Communication Purposes
        </h3>
        {purposes.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)] py-4">
            No purposes configured yet.
          </p>
        ) : (
          <div className="space-y-3">
            {purposes.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] p-3"
              >
                <div>
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    {formatPurposeName(p.purpose)}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    {p.permitted_channels
                      ? `Channels: ${Object.values(p.permitted_channels).join(", ")}`
                      : "All permitted channels"}
                  </p>
                </div>
                <ToggleSwitch
                  checked={p.enabled}
                  onChange={(v) => handleTogglePurpose(p.purpose, v)}
                  label={p.enabled ? "Enabled" : "Disabled"}
                />
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

/* ── Call Agent Tab ── */

function AgentTab({ businessId }: { businessId: string }) {
  const [config, setConfig] = useState<CallAgentConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Form state
  const [enabled, setEnabled] = useState(false);
  const [transactional, setTransactional] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [fromNumber, setFromNumber] = useState("");
  const [timezone, setTimezone] = useState("");
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [retryInterval, setRetryInterval] = useState(300);
  const [maxDaily, setMaxDaily] = useState<number | "">("");
  const [maxWeekly, setMaxWeekly] = useState<number | "">("");
  const [escalationEnabled, setEscalationEnabled] = useState(false);
  const [recordingEnabled, setRecordingEnabled] = useState(false);
  const [transcriptionEnabled, setTranscriptionEnabled] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const data = await voice.getAgentConfig(businessId);
        setConfig(data);
        populateForm(data);
      } catch {
        // 404 = not configured yet
        setConfig(null);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [businessId]);

  function populateForm(data: CallAgentConfigData) {
    setEnabled(data.enabled);
    setTransactional(data.transactional_calling_enabled);
    setMarketing(data.marketing_calling_enabled);
    setFromNumber(data.default_from_number || "");
    setTimezone(data.timezone || "");
    setMaxAttempts(data.max_attempts);
    setRetryInterval(data.retry_interval_seconds);
    setMaxDaily(data.max_daily_attempts || "");
    setMaxWeekly(data.max_weekly_attempts || "");
    setEscalationEnabled(data.human_escalation_enabled);
    setRecordingEnabled(data.recording_enabled);
    setTranscriptionEnabled(data.transcription_enabled);
    setInstructions(data.agent_instructions || "");
  }

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const payload: Record<string, unknown> = {
        enabled,
        transactional_calling_enabled: transactional,
        marketing_calling_enabled: marketing,
        default_from_number: fromNumber || null,
        timezone: timezone || null,
        max_attempts: maxAttempts,
        retry_interval_seconds: retryInterval,
        max_daily_attempts: maxDaily || null,
        max_weekly_attempts: maxWeekly || null,
        human_escalation_enabled: escalationEnabled,
        recording_enabled: recordingEnabled,
        transcription_enabled: transcriptionEnabled,
        agent_instructions: instructions || null,
      };
      if (webhookSecret.trim()) {
        payload.webhook_signature_secret = webhookSecret.trim();
      }
      const result = await voice.upsertAgentConfig(businessId, payload);
      setConfig(result);
      setSuccess(true);
      setWebhookSecret(""); // Clear after save
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSkeleton variant="card" />;

  return (
    <div className="space-y-6">
      {/* Status banner */}
      <Card padding="sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`h-3 w-3 rounded-full ${
                config?.enabled ? "bg-emerald-400" : "bg-[var(--text-muted)]"
              }`}
            />
            <div>
              <p className="text-sm font-medium text-[var(--text-primary)]">
                Call Agent {config?.enabled ? "Active" : "Inactive"}
              </p>
              <p className="text-xs text-[var(--text-muted)]">
                {config
                  ? `Last updated ${new Date(config.updated_at).toLocaleString()}`
                  : "Not yet configured"}
              </p>
            </div>
          </div>
          {config && (
            <div className="flex gap-2">
              {config.transactional_calling_enabled && (
                <Badge variant="info">Transactional</Badge>
              )}
              {config.marketing_calling_enabled && (
                <Badge variant="warning">Marketing</Badge>
              )}
            </div>
          )}
        </div>
      </Card>

      {/* Alerts */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}
      {success && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-400">
          Configuration saved successfully.
        </div>
      )}

      {/* General settings */}
      <Card>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
          General Settings
        </h3>
        <div className="space-y-4">
          <ToggleSwitch
            checked={enabled}
            onChange={setEnabled}
            label="Enable Call Agent"
            description="Allow the system to make and receive calls on behalf of this business."
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex items-center gap-3 rounded-lg border border-[var(--border-subtle)] p-3">
              <ToggleSwitch
                checked={transactional}
                onChange={setTransactional}
                label="Transactional Calling"
                description="Booking confirmations, reminders, status updates"
              />
            </div>
            <div className="flex items-center gap-3 rounded-lg border border-[var(--border-subtle)] p-3">
              <ToggleSwitch
                checked={marketing}
                onChange={setMarketing}
                label="Marketing Calling"
                description="Promotional campaigns, follow-ups, outreach"
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="From Number"
              value={fromNumber}
              onChange={(e) => setFromNumber(e.target.value)}
              placeholder="+1234567890"
              helperText="The phone number displayed to recipients"
            />
            <Input
              label="Timezone"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              placeholder="Australia/Sydney"
              helperText="Used for calling hours and quiet periods"
            />
          </div>
        </div>
      </Card>

      {/* Agent Instructions */}
      <Card>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
          Agent Instructions
        </h3>
        <p className="text-xs text-[var(--text-muted)] mb-3">
          Guide how the AI call agent behaves. These instructions govern the agent&apos;s
          conversation style and boundaries during calls.
        </p>
        <textarea
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          rows={5}
          maxLength={10000}
          className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-y"
          placeholder="e.g. Be professional and concise. Always confirm appointment details before ending the call. Escalate billing questions to a human."
        />
        <p className="text-xs text-[var(--text-muted)] mt-1">
          {instructions.length.toLocaleString()} / 10,000 characters
        </p>
      </Card>

      {/* Escalation & Limits */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
            Human Escalation
          </h3>
          <div className="space-y-4">
            <ToggleSwitch
              checked={escalationEnabled}
              onChange={setEscalationEnabled}
              label="Enable Human Escalation"
              description="Allow the agent to transfer calls to a human when needed"
            />
            <p className="text-xs text-[var(--text-muted)]">
              When enabled, the call agent can request human assistance during
              conversations. Escalations appear in the Calls tab.
            </p>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
            Retry & Limits
          </h3>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-[var(--text-primary)] mb-1.5">
                  Max Attempts
                </label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={maxAttempts}
                  onChange={(e) => setMaxAttempts(Number(e.target.value))}
                  className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--text-primary)] mb-1.5">
                  Retry Interval (s)
                </label>
                <input
                  type="number"
                  min={0}
                  max={86400}
                  value={retryInterval}
                  onChange={(e) => setRetryInterval(Number(e.target.value))}
                  className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-[var(--text-primary)] mb-1.5">
                  Daily Limit
                </label>
                <input
                  type="number"
                  min={1}
                  value={maxDaily}
                  onChange={(e) =>
                    setMaxDaily(e.target.value ? Number(e.target.value) : "")
                  }
                  placeholder="No limit"
                  className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--text-primary)] mb-1.5">
                  Weekly Limit
                </label>
                <input
                  type="number"
                  min={1}
                  value={maxWeekly}
                  onChange={(e) =>
                    setMaxWeekly(e.target.value ? Number(e.target.value) : "")
                  }
                  placeholder="No limit"
                  className="w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                />
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Recording & Transcription */}
      <Card>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
          Recording & Transcription
        </h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <ToggleSwitch
            checked={recordingEnabled}
            onChange={setRecordingEnabled}
            label="Call Recording"
            description="Record calls for quality and compliance"
          />
          <ToggleSwitch
            checked={transcriptionEnabled}
            onChange={setTranscriptionEnabled}
            label="Transcription"
            description="Generate transcripts of call conversations"
          />
        </div>
      </Card>

      {/* Webhook Secret */}
      <Card>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">
          Webhook Security
        </h3>
        <p className="text-xs text-[var(--text-muted)] mb-3">
          Configure a secret for authenticating provider webhook callbacks.
          This value is write-only and never displayed after saving.
        </p>
        <Input
          type="password"
          value={webhookSecret}
          onChange={(e) => setWebhookSecret(e.target.value)}
          placeholder="Enter webhook signature secret"
          helperText="Leave empty to keep the current secret"
        />
      </Card>

      {/* Save */}
      <div className="flex justify-end">
        <Button onClick={handleSave} loading={saving}>
          Save Configuration
        </Button>
      </div>
    </div>
  );
}

/* ── Calls Tab ── */

function CallsTab({ businessId }: { businessId: string }) {
  const [calls, setCalls] = useState<VoiceCallData[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCall, setSelectedCall] = useState<VoiceCallData | null>(null);
  const [escalations, setEscalations] = useState<EscalationData[]>([]);
  const [filterStatus, setFilterStatus] = useState<string>("");

  const loadCalls = useCallback(async () => {
    setLoading(true);
    try {
      const data = await voice.listCalls(businessId, {
        status: filterStatus || undefined,
        limit: 50,
      });
      setCalls(data);
    } catch {
      // API error
    } finally {
      setLoading(false);
    }
  }, [businessId, filterStatus]);

  useEffect(() => {
    loadCalls();
  }, [loadCalls]);

  const handleSelectCall = async (call: VoiceCallData) => {
    setSelectedCall(call);
    try {
      const escs = await voice.listEscalations(businessId, call.id);
      setEscalations(escs);
    } catch {
      setEscalations([]);
    }
  };

  const handleCancel = async (callId: string) => {
    try {
      await voice.cancelCall(businessId, callId);
      await loadCalls();
      if (selectedCall?.id === callId) {
        setSelectedCall(null);
      }
    } catch (err) {
      console.error("Failed to cancel call:", err);
    }
  };

  if (loading) return <LoadingSkeleton variant="list" lines={5} />;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3">
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
        >
          <option value="">All statuses</option>
          <option value="REQUESTED">Requested</option>
          <option value="INITIATING">Initiating</option>
          <option value="RINGING">Ringing</option>
          <option value="CONNECTED">Connected</option>
          <option value="IN_PROGRESS">In Progress</option>
          <option value="COMPLETED">Completed</option>
          <option value="FAILED">Failed</option>
          <option value="CANCELLED">Cancelled</option>
          <option value="NO_ANSWER">No Answer</option>
          <option value="BUSY">Busy</option>
          <option value="ESCALATED">Escalated</option>
        </select>
        <Button variant="secondary" size="sm" onClick={loadCalls}>
          Refresh
        </Button>
      </div>

      {calls.length === 0 ? (
        <EmptyState
          title="No calls found"
          description="Voice calls will appear here when the Call Agent is active and calls are made or received."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          {/* Call list */}
          <div className="lg:col-span-2 space-y-2">
            {calls.map((call) => (
              <button
                key={call.id}
                onClick={() => handleSelectCall(call)}
                className={`w-full text-left rounded-lg border p-3 transition-colors ${
                  selectedCall?.id === call.id
                    ? "border-[var(--accent)] bg-[var(--accent)]/5"
                    : "border-[var(--border-subtle)] hover:border-[var(--border-default)] hover:bg-[var(--bg-elevated)]"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <CallTypeIcon callType={call.call_type} />
                    <div>
                      <p className="text-sm font-medium text-[var(--text-primary)]">
                        {call.to_number}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        {formatPurpose(call.purpose)} · {new Date(call.requested_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={callStatusVariant(call.status)}>
                      {call.status}
                    </Badge>
                  </div>
                </div>
              </button>
            ))}
          </div>

          {/* Call detail panel */}
          <div className="lg:col-span-1">
            {selectedCall ? (
              <CallDetail
                call={selectedCall}
                escalations={escalations}
                onCancel={() => handleCancel(selectedCall.id)}
              />
            ) : (
              <Card>
                <p className="text-sm text-[var(--text-muted)] text-center py-8">
                  Select a call to view details
                </p>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Call Detail Panel ── */

function CallDetail({
  call,
  escalations,
  onCancel,
}: {
  call: VoiceCallData;
  escalations: EscalationData[];
  onCancel: () => void;
}) {
  const canCancel = ["REQUESTED", "INITIATING", "RINGING", "QUEUED"].includes(
    call.status.toUpperCase()
  );

  return (
    <Card padding="sm">
      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">
              Call Details
            </h4>
            {canCancel && (
              <Button size="sm" variant="danger" onClick={onCancel}>
                Cancel
              </Button>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <DetailRow label="Status">
              <Badge variant={callStatusVariant(call.status)}>{call.status}</Badge>
            </DetailRow>
            <DetailRow label="To">{call.to_number}</DetailRow>
            <DetailRow label="From">{call.from_number || "Not assigned"}</DetailRow>
            <DetailRow label="Type">{formatCallType(call.call_type)}</DetailRow>
            <DetailRow label="Purpose">{formatPurpose(call.purpose)}</DetailRow>
            <DetailRow label="Provider">{call.provider}</DetailRow>
            {call.customer_id && (
              <DetailRow label="Customer">
                <span className="font-mono">{call.customer_id.slice(0, 12)}...</span>
              </DetailRow>
            )}
          </div>
        </div>

        {/* Timeline */}
        <div>
          <h5 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">
            Timeline
          </h5>
          <div className="space-y-1.5 text-xs">
            <TimelineEntry label="Requested" time={call.requested_at} />
            {call.authorized_at && (
              <TimelineEntry label="Authorized" time={call.authorized_at} />
            )}
            {call.initiated_at && (
              <TimelineEntry label="Initiated" time={call.initiated_at} />
            )}
            {call.connected_at && (
              <TimelineEntry label="Connected" time={call.connected_at} />
            )}
            {call.completed_at && (
              <TimelineEntry label="Completed" time={call.completed_at} />
            )}
            {call.failed_at && (
              <TimelineEntry label="Failed" time={call.failed_at} highlight="danger" />
            )}
          </div>
          {call.failure_code && (
            <p className="mt-2 text-xs text-red-400">
              {call.failure_code}: {call.failure_reason || "No details"}
            </p>
          )}
        </div>

        {/* Duration */}
        {call.connected_at && call.completed_at && (
          <div>
            <h5 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-1">
              Duration
            </h5>
            <p className="text-sm font-medium text-[var(--text-primary)]">
              {formatDuration(call.connected_at, call.completed_at)}
            </p>
          </div>
        )}

        {/* Escalations */}
        {escalations.length > 0 && (
          <div>
            <h5 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">
              Escalations
            </h5>
            <div className="space-y-2">
              {escalations.map((esc) => (
                <div
                  key={esc.id}
                  className="rounded border border-[var(--border-subtle)] p-2"
                >
                  <div className="flex items-center justify-between mb-1">
                    <Badge variant={escalationVariant(esc.escalation_status)}>
                      {esc.escalation_status}
                    </Badge>
                    <span className="text-xs text-[var(--text-muted)]">
                      {new Date(esc.requested_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-secondary)]">
                    {esc.escalation_reason}
                  </p>
                  {esc.assigned_member_id && (
                    <p className="text-xs text-[var(--text-muted)] mt-1">
                      Assigned: {esc.assigned_member_id.slice(0, 12)}...
                    </p>
                  )}
                  {esc.resolution_notes && (
                    <p className="text-xs text-[var(--text-muted)] mt-1 italic">
                      {esc.resolution_notes}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

/* ── Shared Components ── */

function ToggleSwitch({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors ${
          checked ? "bg-[var(--accent)]" : "bg-[var(--bg-elevated)]"
        }`}
      >
        <span
          className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
            checked ? "translate-x-[18px]" : "translate-x-[3px]"
          }`}
        />
      </button>
      <div>
        <p className="text-sm font-medium text-[var(--text-primary)]">{label}</p>
        {description && (
          <p className="text-xs text-[var(--text-muted)] mt-0.5">{description}</p>
        )}
      </div>
    </label>
  );
}

function ChannelIcon({ channel }: { channel: string }) {
  const icons: Record<string, string> = {
    EMAIL: "\u2709",
    SMS: "\ud83d\udcf1",
    WHATSAPP: "\ud83d\udcac",
    VOICE: "\ud83d\udcde",
    PUSH: "\ud83d\udd14",
  };
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--bg-elevated)] text-base">
      {icons[channel.toUpperCase()] || "\ud83d\udce8"}
    </span>
  );
}

function CallTypeIcon({ callType }: { callType: string }) {
  const isOutbound = callType.toUpperCase() !== "INBOUND";
  return (
    <span
      className={`flex h-8 w-8 items-center justify-center rounded-lg text-sm ${
        isOutbound
          ? "bg-blue-500/15 text-blue-400"
          : "bg-emerald-500/15 text-emerald-400"
      }`}
    >
      {isOutbound ? "\u2197" : "\u2199"}
    </span>
  );
}

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[var(--text-muted)]">{label}</span>
      <span className="text-[var(--text-primary)]">{children}</span>
    </div>
  );
}

function TimelineEntry({
  label,
  time,
  highlight,
}: {
  label: string;
  time: string;
  highlight?: "danger";
}) {
  return (
    <div className="flex items-center justify-between">
      <span className={highlight === "danger" ? "text-red-400" : "text-[var(--text-secondary)]"}>
        {label}
      </span>
      <span className="text-[var(--text-muted)]">
        {new Date(time).toLocaleTimeString()}
      </span>
    </div>
  );
}

/* ── Helpers ── */

function formatChannelName(channel: string): string {
  const names: Record<string, string> = {
    EMAIL: "Email",
    SMS: "SMS",
    WHATSAPP: "WhatsApp",
    VOICE: "Voice",
    PUSH: "Push Notifications",
  };
  return names[channel.toUpperCase()] || channel;
}

function formatPurposeName(purpose: string): string {
  return purpose
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function formatPurpose(purpose: string): string {
  return purpose
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function formatCallType(callType: string): string {
  return callType.toUpperCase() === "INBOUND" ? "Inbound" : "Outbound";
}

function formatDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}m ${remaining}s`;
}

function callStatusVariant(
  status: string
): "info" | "warning" | "danger" | "success" | "muted" | "default" {
  switch (status.toUpperCase()) {
    case "REQUESTED":
    case "INITIATING":
    case "QUEUED":
      return "info";
    case "RINGING":
    case "CONNECTED":
    case "IN_PROGRESS":
      return "warning";
    case "COMPLETED":
      return "success";
    case "FAILED":
    case "NO_ANSWER":
    case "BUSY":
    case "DECLINED":
      return "danger";
    case "CANCELLED":
    case "EXPIRED":
      return "muted";
    case "ESCALATED":
      return "warning";
    default:
      return "default";
  }
}

function escalationVariant(
  status: string
): "info" | "warning" | "danger" | "success" | "muted" | "default" {
  switch (status.toUpperCase()) {
    case "PENDING":
      return "warning";
    case "ASSIGNED":
      return "info";
    case "ACCEPTED":
      return "info";
    case "RESOLVED":
      return "success";
    case "CANCELLED":
      return "muted";
    default:
      return "default";
  }
}
