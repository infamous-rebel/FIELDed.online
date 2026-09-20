"use client";

import { useCallback, useEffect, useState } from "react";
import {
  brain,
  businesses,
  type BusinessBrainDetail,
  type BusinessRuleDetail,
  type BrainVersionDetail,
  type BrainVersionSummary,
  type BusinessSummary,
  type ValidationResult,
  type Provenance,
  FieldedApiError,
} from "@/lib/api-client";
import { isAuthenticated } from "@/lib/auth";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { EmptyState } from "@/components/ui/empty-state";

// --- Constants ---

const CONFIG_AREAS = [
  { key: "identity_config", label: "Identity" },
  { key: "services_config", label: "Services" },
  { key: "pricing_config", label: "Pricing" },
  { key: "availability_config", label: "Availability" },
  { key: "qualification_config", label: "Qualification" },
  { key: "policies_config", label: "Policies" },
  { key: "escalation_config", label: "Escalation" },
  { key: "communication_config", label: "Communication" },
] as const;

const RULE_TYPES = [
  { value: "pricing", label: "Pricing" },
  { value: "policy", label: "Policy" },
  { value: "qualification", label: "Qualification" },
  { value: "availability", label: "Availability" },
  { value: "escalation", label: "Escalation" },
];

// --- Helpers ---

function brainStatusBadge(status: string): "default" | "success" | "warning" | "danger" | "info" | "muted" {
  switch (status.toLowerCase()) {
    case "draft":
      return "muted";
    case "validating":
      return "info";
    case "review":
      return "warning";
    case "approved":
      return "success";
    case "active":
      return "success";
    case "superseded":
      return "danger";
    default:
      return "default";
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

function formatJson(obj: Record<string, unknown> | null): string {
  if (!obj || Object.keys(obj).length === 0) return "{}";
  return JSON.stringify(obj, null, 2);
}

// --- Main Component ---

export default function BusinessBrainPage() {
  const [authed, setAuthed] = useState(false);
  const [business, setBusiness] = useState<BusinessSummary | null>(null);
  const [brainData, setBrainData] = useState<BusinessBrainDetail | null>(null);
  const [versions, setVersions] = useState<BrainVersionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Draft workspace
  const [draftVersion, setDraftVersion] = useState<BrainVersionDetail | null>(null);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [expandedConfig, setExpandedConfig] = useState<string | null>(null);
  const [configEdits, setConfigEdits] = useState<Record<string, string>>({});
  const [savingConfig, setSavingConfig] = useState(false);

  // Rule management
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [editingRule, setEditingRule] = useState<BusinessRuleDetail | null>(null);
  const [ruleForm, setRuleForm] = useState({
    name: "",
    rule_type: "pricing",
    description: "",
    priority: 0,
    rule_data: "{}",
  });
  const [ruleError, setRuleError] = useState("");
  const [savingRule, setSavingRule] = useState(false);

  // Version detail view
  const [selectedVersion, setSelectedVersion] = useState<BrainVersionDetail | null>(null);
  const [provenance, setProvenance] = useState<Provenance | null>(null);

  // Action states
  const [actionLoading, setActionLoading] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");

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

      const [brainDetail, versionList] = await Promise.all([
        brain.getDetail(bizList[0].id),
        brain.listVersions(bizList[0].id),
      ]);
      setBrainData(brainDetail);
      setVersions(versionList);

      // Find draft version if exists
      const draft = versionList.find((v) => v.status === "draft");
      if (draft) {
        const draftDetail = await brain.getVersion(bizList[0].id, draft.id);
        setDraftVersion(draftDetail);
      } else {
        setDraftVersion(null);
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

  // --- Handlers ---

  const handleCreateDraft = async () => {
    if (!business) return;
    try {
      setActionLoading("create");
      setActionError("");
      setActionSuccess("");
      const newVersion = await brain.createVersion(business.id);
      setDraftVersion(newVersion);
      setActionSuccess("Draft version created");
      await loadData();
    } catch (err) {
      setActionError(err instanceof FieldedApiError ? err.error.message : "Failed to create draft");
    } finally {
      setActionLoading("");
    }
  };

  const handleValidate = async () => {
    if (!business || !draftVersion) return;
    try {
      setActionLoading("validate");
      setActionError("");
      setActionSuccess("");
      const result = await brain.validate(business.id, draftVersion.id);
      setValidationResult(result);
      setActionSuccess(result.valid ? "Validation passed" : `Validation found ${result.error_count} error(s)`);
    } catch (err) {
      setActionError(err instanceof FieldedApiError ? err.error.message : "Validation failed");
    } finally {
      setActionLoading("");
    }
  };

  const handleSubmitForReview = async () => {
    if (!business || !draftVersion) return;
    try {
      setActionLoading("submit");
      setActionError("");
      setActionSuccess("");
      await brain.transition(business.id, draftVersion.id, "review");
      setActionSuccess("Submitted for review");
      await loadData();
    } catch (err) {
      setActionError(err instanceof FieldedApiError ? err.error.message : "Failed to submit");
    } finally {
      setActionLoading("");
    }
  };

  const handleApprove = async () => {
    if (!business || !draftVersion) return;
    try {
      setActionLoading("approve");
      setActionError("");
      setActionSuccess("");
      await brain.approve(business.id, draftVersion.id);
      setActionSuccess("Version approved");
      await loadData();
    } catch (err) {
      setActionError(err instanceof FieldedApiError ? err.error.message : "Failed to approve");
    } finally {
      setActionLoading("");
    }
  };

  const handleActivate = async () => {
    if (!business || !draftVersion) return;
    try {
      setActionLoading("activate");
      setActionError("");
      setActionSuccess("");
      await brain.activate(business.id, draftVersion.id);
      setActionSuccess("Version activated");
      await loadData();
    } catch (err) {
      setActionError(err instanceof FieldedApiError ? err.error.message : "Failed to activate");
    } finally {
      setActionLoading("");
    }
  };

  const handleSaveConfig = async (configKey: string) => {
    if (!business || !draftVersion) return;
    const configValue = configEdits[configKey];
    if (!configValue) return;

    try {
      setSavingConfig(true);
      setActionError("");
      setActionSuccess("");

      let parsed: unknown;
      try {
        parsed = JSON.parse(configValue);
      } catch {
        setActionError("Invalid JSON in config");
        return;
      }

      await brain.updateVersion(business.id, draftVersion.id, {
        [configKey]: parsed,
      });

      setActionSuccess("Config saved");
      setExpandedConfig(null);
      await loadData();
    } catch (err) {
      setActionError(err instanceof FieldedApiError ? err.error.message : "Failed to save config");
    } finally {
      setSavingConfig(false);
    }
  };

  const handleAddRule = async () => {
    if (!business || !draftVersion) return;
    try {
      setSavingRule(true);
      setRuleError("");

      let ruleData: Record<string, unknown>;
      try {
        ruleData = JSON.parse(ruleForm.rule_data);
      } catch {
        setRuleError("Invalid JSON in rule data");
        return;
      }

      if (editingRule) {
        await brain.updateRule(business.id, draftVersion.id, editingRule.id, {
          name: ruleForm.name,
          rule_type: ruleForm.rule_type,
          description: ruleForm.description || null,
          priority: ruleForm.priority,
          rule_data: ruleData,
        });
      } else {
        await brain.addRule(business.id, draftVersion.id, {
          name: ruleForm.name,
          rule_type: ruleForm.rule_type,
          description: ruleForm.description || undefined,
          priority: ruleForm.priority,
          rule_data: ruleData,
        });
      }

      resetRuleForm();
      await loadData();
    } catch (err) {
      setRuleError(err instanceof FieldedApiError ? err.error.message : "Failed to save rule");
    } finally {
      setSavingRule(false);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    if (!business || !draftVersion) return;
    if (!confirm("Delete this rule?")) return;

    try {
      setActionLoading(`delete-rule-${ruleId}`);
      setActionError("");
      await brain.deleteRule(business.id, draftVersion.id, ruleId);
      setActionSuccess("Rule deleted");
      await loadData();
    } catch (err) {
      setActionError(err instanceof FieldedApiError ? err.error.message : "Failed to delete rule");
    } finally {
      setActionLoading("");
    }
  };

  const handleViewVersion = async (version: BrainVersionSummary) => {
    if (!business) return;
    try {
      const detail = await brain.getVersion(business.id, version.id);
      setSelectedVersion(detail);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to load version");
    }
  };

  const handleViewProvenance = async (versionId: string) => {
    if (!business) return;
    try {
      const prov = await brain.getProvenance(business.id, versionId);
      setProvenance(prov);
    } catch (err) {
      setError(err instanceof FieldedApiError ? err.error.message : "Failed to load provenance");
    }
  };

  const resetRuleForm = () => {
    setRuleForm({ name: "", rule_type: "pricing", description: "", priority: 0, rule_data: "{}" });
    setEditingRule(null);
    setShowRuleForm(false);
    setRuleError("");
  };

  const startEditRule = (rule: BusinessRuleDetail) => {
    setEditingRule(rule);
    setRuleForm({
      name: rule.name,
      rule_type: rule.rule_type,
      description: rule.description || "",
      priority: rule.priority,
      rule_data: formatJson(rule.rule_data),
    });
    setShowRuleForm(true);
  };

  // --- Render ---

  if (!authed) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12">
        <p className="text-[var(--text-secondary)]">Please sign in to manage your Business Brain.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12 space-y-6">
        <LoadingSkeleton lines={2} />
        <LoadingSkeleton variant="card" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-12 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Business Brain</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Configure governed rules for pricing, qualification, availability, and escalation.
          </p>
        </div>
        {!draftVersion && (
          <Button onClick={handleCreateDraft} loading={actionLoading === "create"}>
            Create Draft
          </Button>
        )}
      </div>

      {/* Action feedback */}
      {actionError && (
        <div className="rounded-md border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">
          {actionError}
        </div>
      )}
      {actionSuccess && (
        <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-400">
          {actionSuccess}
        </div>
      )}

      {/* Brain Overview */}
      <Card>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">Overview</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-sm text-[var(--text-muted)]">Brain Status</p>
            <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
              {brainData ? "Active" : "Not Configured"}
            </p>
          </div>
          <div>
            <p className="text-sm text-[var(--text-muted)]">Active Version</p>
            <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
              {brainData?.active_version ? `v${brainData.active_version.version_number}` : "None"}
            </p>
          </div>
          <div>
            <p className="text-sm text-[var(--text-muted)]">Total Versions</p>
            <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
              {brainData?.version_count || 0}
            </p>
          </div>
          <div>
            <p className="text-sm text-[var(--text-muted)]">Draft Status</p>
            <p className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
              {draftVersion ? "In Progress" : "None"}
            </p>
          </div>
        </div>
        {brainData?.active_version && (
          <div className="mt-4 pt-4 border-t border-[var(--border-subtle)]">
            <p className="text-sm text-[var(--text-muted)]">
              Active version last updated: {formatDate(brainData.active_version.updated_at)}
            </p>
          </div>
        )}
      </Card>

      {/* Draft Workspace */}
      {draftVersion && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                Draft Version v{draftVersion.version_number}
              </h2>
              <p className="text-sm text-[var(--text-muted)]">
                Status: <Badge variant={brainStatusBadge(draftVersion.status)}>{draftVersion.status}</Badge>
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleValidate}
                loading={actionLoading === "validate"}
              >
                Validate
              </Button>
              {draftVersion.status === "draft" && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleSubmitForReview}
                  loading={actionLoading === "submit"}
                >
                  Submit for Review
                </Button>
              )}
              {draftVersion.status === "review" && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleApprove}
                  loading={actionLoading === "approve"}
                >
                  Approve
                </Button>
              )}
              {draftVersion.status === "approved" && (
                <Button
                  size="sm"
                  onClick={handleActivate}
                  loading={actionLoading === "activate"}
                >
                  Activate
                </Button>
              )}
            </div>
          </div>

          {/* Validation result */}
          {validationResult && (
            <div className="mb-4 rounded-lg border border-[var(--border-subtle)] p-4">
              <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-2">
                Validation Result
              </h3>
              {validationResult.valid ? (
                <p className="text-sm text-emerald-400">✓ Validation passed</p>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-[var(--danger)]">
                    {validationResult.error_count} error(s) found:
                  </p>
                  {validationResult.errors.map((err, i) => (
                    <div key={i} className="text-sm text-[var(--text-secondary)]">
                      <span className="font-mono text-[var(--danger)]">{err.field}</span>: {err.message}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Config Areas */}
          <div className="mb-6">
            <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3">
              Configuration Areas
            </h3>
            <div className="space-y-2">
              {CONFIG_AREAS.map((area) => {
                const configValue = draftVersion[area.key as keyof typeof draftVersion] as Record<string, unknown> | null;
                const isExpanded = expandedConfig === area.key;
                const editValue = configEdits[area.key] ?? formatJson(configValue);

                return (
                  <div
                    key={area.key}
                    className="rounded-lg border border-[var(--border-subtle)]"
                  >
                    <button
                      onClick={() => setExpandedConfig(isExpanded ? null : area.key)}
                      className="w-full flex items-center justify-between p-3 text-left hover:bg-[var(--bg-elevated)] transition-colors"
                    >
                      <span className="text-sm font-medium text-[var(--text-primary)]">
                        {area.label}
                      </span>
                      <span className="text-xs text-[var(--text-muted)]">
                        {configValue && Object.keys(configValue).length > 0
                          ? `${Object.keys(configValue).length} field(s)`
                          : "Empty"}
                      </span>
                    </button>
                    {isExpanded && (
                      <div className="p-3 border-t border-[var(--border-subtle)] space-y-2">
                        <textarea
                          value={editValue}
                          onChange={(e) =>
                            setConfigEdits({ ...configEdits, [area.key]: e.target.value })
                          }
                          rows={8}
                          className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm font-mono text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none"
                          placeholder="{}"
                        />
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            onClick={() => handleSaveConfig(area.key)}
                            loading={savingConfig}
                          >
                            Save
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setExpandedConfig(null);
                              setConfigEdits({ ...configEdits, [area.key]: formatJson(configValue) });
                            }}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Rules */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                Rules ({draftVersion.rules.length})
              </h3>
              <Button size="sm" onClick={() => { resetRuleForm(); setShowRuleForm(true); }}>
                Add Rule
              </Button>
            </div>

            {showRuleForm && (
              <div className="mb-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4 space-y-3">
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  {editingRule ? "Edit Rule" : "New Rule"}
                </h4>
                {ruleError && (
                  <div className="rounded-md border border-[var(--danger)]/30 bg-[var(--danger)]/10 p-2 text-sm text-[var(--danger)]">
                    {ruleError}
                  </div>
                )}
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                      Name
                    </label>
                    <input
                      type="text"
                      value={ruleForm.name}
                      onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })}
                      className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                      Type
                    </label>
                    <select
                      value={ruleForm.rule_type}
                      onChange={(e) => setRuleForm({ ...ruleForm, rule_type: e.target.value })}
                      className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                    >
                      {RULE_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                    Description
                  </label>
                  <input
                    type="text"
                    value={ruleForm.description}
                    onChange={(e) => setRuleForm({ ...ruleForm, description: e.target.value })}
                    className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                      Priority
                    </label>
                    <input
                      type="number"
                      value={ruleForm.priority}
                      onChange={(e) =>
                        setRuleForm({ ...ruleForm, priority: parseInt(e.target.value) || 0 })
                      }
                      className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                    Rule Data (JSON)
                  </label>
                  <textarea
                    value={ruleForm.rule_data}
                    onChange={(e) => setRuleForm({ ...ruleForm, rule_data: e.target.value })}
                    rows={4}
                    className="w-full rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm font-mono text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] resize-none"
                    placeholder="{}"
                  />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleAddRule} loading={savingRule}>
                    {editingRule ? "Update" : "Add"} Rule
                  </Button>
                  <Button size="sm" variant="ghost" onClick={resetRuleForm}>
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {draftVersion.rules.length === 0 ? (
              <EmptyState
                title="No rules yet"
                description="Add rules to configure pricing, qualification, availability, and escalation logic."
              />
            ) : (
              <div className="space-y-2">
                {draftVersion.rules.map((rule) => (
                  <div
                    key={rule.id}
                    className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                          {rule.name}
                        </p>
                        <Badge variant="default">{rule.rule_type}</Badge>
                        <span className="text-xs text-[var(--text-muted)]">
                          Priority: {rule.priority}
                        </span>
                      </div>
                      {rule.description && (
                        <p className="mt-1 text-xs text-[var(--text-secondary)] truncate">
                          {rule.description}
                        </p>
                      )}
                    </div>
                    <div className="ml-4 flex gap-2">
                      <Button size="sm" variant="ghost" onClick={() => startEditRule(rule)}>
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDeleteRule(rule.id)}
                        loading={actionLoading === `delete-rule-${rule.id}`}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Version History */}
      <Card>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">Version History</h2>
        {versions.length === 0 ? (
          <EmptyState
            title="No versions yet"
            description="Create a draft to start configuring your Business Brain."
          />
        ) : (
          <div className="space-y-2">
            {versions.map((version) => (
              <div
                key={version.id}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <p className="text-sm font-medium text-[var(--text-primary)]">
                      v{version.version_number}
                    </p>
                    <Badge variant={brainStatusBadge(version.status)}>{version.status}</Badge>
                    <span className="text-xs text-[var(--text-muted)]">
                      {version.rule_count} rule(s)
                    </span>
                    <span className="text-xs text-[var(--text-muted)]">
                      {formatDate(version.updated_at)}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" onClick={() => handleViewVersion(version)}>
                      View
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => handleViewProvenance(version.id)}>
                      Provenance
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Version Detail Modal */}
      {selectedVersion && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Version v{selectedVersion.version_number} Details
            </h2>
            <Button size="sm" variant="ghost" onClick={() => setSelectedVersion(null)}>
              Close
            </Button>
          </div>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-sm text-[var(--text-muted)]">Status</p>
                <Badge variant={brainStatusBadge(selectedVersion.status)}>
                  {selectedVersion.status}
                </Badge>
              </div>
              <div>
                <p className="text-sm text-[var(--text-muted)]">Created</p>
                <p className="text-sm text-[var(--text-primary)]">
                  {formatDate(selectedVersion.created_at)}
                </p>
              </div>
            </div>
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)] mb-2">
                Configuration
              </p>
              <div className="space-y-2">
                {CONFIG_AREAS.map((area) => {
                  const configValue = selectedVersion[area.key as keyof typeof selectedVersion] as Record<string, unknown> | null;
                  if (!configValue || Object.keys(configValue).length === 0) return null;
                  return (
                    <div key={area.key} className="rounded-lg border border-[var(--border-subtle)] p-3">
                      <p className="text-sm font-medium text-[var(--text-primary)] mb-2">
                        {area.label}
                      </p>
                      <pre className="text-xs font-mono text-[var(--text-secondary)] overflow-x-auto">
                        {formatJson(configValue)}
                      </pre>
                    </div>
                  );
                })}
              </div>
            </div>
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)] mb-2">
                Rules ({selectedVersion.rules.length})
              </p>
              {selectedVersion.rules.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">No rules</p>
              ) : (
                <div className="space-y-2">
                  {selectedVersion.rules.map((rule) => (
                    <div
                      key={rule.id}
                      className="rounded-lg border border-[var(--border-subtle)] p-3"
                    >
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-[var(--text-primary)]">
                          {rule.name}
                        </p>
                        <Badge variant="default">{rule.rule_type}</Badge>
                      </div>
                      {rule.description && (
                        <p className="mt-1 text-xs text-[var(--text-secondary)]">
                          {rule.description}
                        </p>
                      )}
                      <pre className="mt-2 text-xs font-mono text-[var(--text-muted)] overflow-x-auto">
                        {formatJson(rule.rule_data)}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* Provenance Modal */}
      {provenance && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Provenance — v{provenance.version_number}
            </h2>
            <Button size="sm" variant="ghost" onClick={() => setProvenance(null)}>
              Close
            </Button>
          </div>
          <div className="space-y-3">
            {provenance.entries.length === 0 ? (
              <p className="text-sm text-[var(--text-muted)]">No provenance entries</p>
            ) : (
              provenance.entries.map((entry, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-[var(--border-subtle)] p-3"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-[var(--text-primary)]">
                      {entry.action.replace(/_/g, " ")}
                    </p>
                    <p className="text-xs text-[var(--text-muted)]">
                      {formatDate(entry.timestamp)}
                    </p>
                  </div>
                  {Object.keys(entry.details).length > 0 && (
                    <pre className="mt-2 text-xs font-mono text-[var(--text-secondary)] overflow-x-auto">
                      {JSON.stringify(entry.details, null, 2)}
                    </pre>
                  )}
                </div>
              ))
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
