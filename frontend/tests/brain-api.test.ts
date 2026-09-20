import { describe, it, expect, vi, beforeEach } from "vitest";
import { brain, FieldedApiError } from "@/lib/api-client";

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Helper to mock successful responses
function mockResponse<T>(data: T, status = 200) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    status,
    json: async () => data,
  });
}

// Helper to mock error responses
function mockError(status: number, error: { code: string; message: string }) {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    json: async () => ({ error }),
  });
}

describe("Brain API Client", () => {
  const businessId = "test-business-id";
  const versionId = "test-version-id";
  const ruleId = "test-rule-id";

  beforeEach(() => {
    vi.clearAllMocks();
    // Mock localStorage
    const store: Record<string, string> = {};
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => store[key] || null,
      setItem: (key: string, value: string) => {
        store[key] = value;
      },
      removeItem: (key: string) => {
        delete store[key];
      },
    });
  });

  describe("getDetail", () => {
    it("should fetch brain detail successfully", async () => {
      const mockBrain = {
        id: "brain-1",
        business_id: businessId,
        active_version_id: null,
        active_version: null,
        version_count: 0,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      };
      mockResponse(mockBrain);

      const result = await brain.getDetail(businessId);

      expect(result).toEqual(mockBrain);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain`),
        expect.any(Object)
      );
    });

    it("should throw FieldedApiError on failure", async () => {
      mockError(404, { code: "NOT_FOUND", message: "Brain not found" });

      await expect(brain.getDetail(businessId)).rejects.toThrow(FieldedApiError);
    });
  });

  describe("listVersions", () => {
    it("should fetch version list", async () => {
      const mockVersions = [
        {
          id: versionId,
          brain_id: "brain-1",
          version_number: 1,
          status: "draft",
          rule_count: 0,
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
      ];
      mockResponse(mockVersions);

      const result = await brain.listVersions(businessId);

      expect(result).toEqual(mockVersions);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions`),
        expect.any(Object)
      );
    });
  });

  describe("getVersion", () => {
    it("should fetch version detail with rules", async () => {
      const mockVersion = {
        id: versionId,
        brain_id: "brain-1",
        version_number: 1,
        status: "draft",
        rules: [],
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      };
      mockResponse(mockVersion);

      const result = await brain.getVersion(businessId, versionId);

      expect(result).toEqual(mockVersion);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions/${versionId}`),
        expect.any(Object)
      );
    });
  });

  describe("createVersion", () => {
    it("should create a new draft version", async () => {
      const mockVersion = {
        id: versionId,
        brain_id: "brain-1",
        version_number: 1,
        status: "draft",
        rules: [],
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      };
      mockResponse(mockVersion, 201);

      const result = await brain.createVersion(businessId, { test: "config" });

      expect(result).toEqual(mockVersion);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions`),
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("config"),
        })
      );
    });
  });

  describe("updateVersion", () => {
    it("should update version config", async () => {
      const mockVersion = {
        id: versionId,
        brain_id: "brain-1",
        version_number: 1,
        status: "draft",
        rules: [],
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      };
      mockResponse(mockVersion);

      const result = await brain.updateVersion(businessId, versionId, {
        identity_config: { test: "data" },
      });

      expect(result).toEqual(mockVersion);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions/${versionId}`),
        expect.objectContaining({
          method: "PATCH",
        })
      );
    });
  });

  describe("addRule", () => {
    it("should add a rule to a version", async () => {
      const mockRule = {
        id: ruleId,
        brain_version_id: versionId,
        rule_type: "pricing",
        name: "Test Rule",
        description: "Test description",
        rule_data: { test: "data" },
        priority: 0,
        is_active: true,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      };
      mockResponse(mockRule, 201);

      const result = await brain.addRule(businessId, versionId, {
        rule_type: "pricing",
        name: "Test Rule",
        description: "Test description",
        rule_data: { test: "data" },
        priority: 0,
      });

      expect(result).toEqual(mockRule);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions/${versionId}/rules`),
        expect.objectContaining({
          method: "POST",
        })
      );
    });
  });

  describe("updateRule", () => {
    it("should update an existing rule", async () => {
      const mockRule = {
        id: ruleId,
        brain_version_id: versionId,
        rule_type: "pricing",
        name: "Updated Rule",
        description: "Updated description",
        rule_data: { test: "data" },
        priority: 1,
        is_active: true,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      };
      mockResponse(mockRule);

      const result = await brain.updateRule(businessId, versionId, ruleId, {
        name: "Updated Rule",
        priority: 1,
      });

      expect(result).toEqual(mockRule);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions/${versionId}/rules/${ruleId}`),
        expect.objectContaining({
          method: "POST",
        })
      );
    });
  });

  describe("deleteRule", () => {
    it("should delete a rule", async () => {
      mockResponse({}, 204);

      await brain.deleteRule(businessId, versionId, ruleId);

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions/${versionId}/rules/${ruleId}`),
        expect.objectContaining({
          method: "DELETE",
        })
      );
    });
  });

  describe("validate", () => {
    it("should validate a version", async () => {
      const mockResult = {
        valid: true,
        error_count: 0,
        errors: [],
      };
      mockResponse(mockResult);

      const result = await brain.validate(businessId, versionId);

      expect(result).toEqual(mockResult);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions/${versionId}/validate`),
        expect.objectContaining({
          method: "POST",
        })
      );
    });

    it("should return validation errors", async () => {
      const mockResult = {
        valid: false,
        error_count: 2,
        errors: [
          { field: "identity_config", message: "Invalid structure", code: "INVALID_STRUCTURE" },
          { field: "pricing_config", message: "Missing required field", code: "MISSING_FIELD" },
        ],
      };
      mockResponse(mockResult);

      const result = await brain.validate(businessId, versionId);

      expect(result.valid).toBe(false);
      expect(result.error_count).toBe(2);
      expect(result.errors).toHaveLength(2);
    });
  });

  describe("transition", () => {
    it("should transition version status", async () => {
      const mockResult = {
        id: versionId,
        previous_status: "draft",
        current_status: "validating",
        version_number: 1,
      };
      mockResponse(mockResult);

      const result = await brain.transition(businessId, versionId, "validating");

      expect(result).toEqual(mockResult);
      expect(result.previous_status).toBe("draft");
      expect(result.current_status).toBe("validating");
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions/${versionId}/transition`),
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("validating"),
        })
      );
    });
  });

  describe("approve", () => {
    it("should approve a version", async () => {
      const mockResult = {
        decision: "approved",
        version_id: versionId,
        version_status: "approved",
        approver_role: "owner",
        comment: "Looks good",
      };
      mockResponse(mockResult);

      const result = await brain.approve(businessId, versionId, "Looks good");

      expect(result).toEqual(mockResult);
      expect(result.decision).toBe("approved");
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions/${versionId}/approve`),
        expect.objectContaining({
          method: "POST",
        })
      );
    });
  });

  describe("activate", () => {
    it("should activate a version", async () => {
      const mockBrain = {
        id: "brain-1",
        business_id: businessId,
        active_version_id: versionId,
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T00:00:00Z",
      };
      mockResponse(mockBrain);

      const result = await brain.activate(businessId, versionId);

      expect(result).toEqual(mockBrain);
      expect(result.active_version_id).toBe(versionId);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions/${versionId}/activate`),
        expect.objectContaining({
          method: "POST",
        })
      );
    });
  });

  describe("getProvenance", () => {
    it("should fetch provenance for a version", async () => {
      const mockProvenance = {
        version_id: versionId,
        brain_id: "brain-1",
        version_number: 1,
        status: "active",
        entries: [
          {
            action: "version_created",
            actor_id: null,
            timestamp: "2024-01-01T00:00:00Z",
            details: { version_number: 1, initial_status: "draft" },
          },
        ],
      };
      mockResponse(mockProvenance);

      const result = await brain.getProvenance(businessId, versionId);

      expect(result).toEqual(mockProvenance);
      expect(result.entries).toHaveLength(1);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${businessId}/brain/versions/${versionId}/provenance`),
        expect.any(Object)
      );
    });
  });

  describe("Error handling", () => {
    it("should handle authorization errors", async () => {
      mockError(403, { code: "FORBIDDEN", message: "Insufficient permissions" });

      try {
        await brain.createVersion(businessId);
        expect.fail("Should have thrown error");
      } catch (err) {
        expect(err).toBeInstanceOf(FieldedApiError);
        expect((err as FieldedApiError).status).toBe(403);
        expect((err as FieldedApiError).error.code).toBe("FORBIDDEN");
      }
    });

    it("should handle conflict errors", async () => {
      mockError(409, {
        code: "INVALID_TRANSITION",
        message: "Cannot transition from active to draft",
      });

      try {
        await brain.transition(businessId, versionId, "draft");
        expect.fail("Should have thrown error");
      } catch (err) {
        expect(err).toBeInstanceOf(FieldedApiError);
        expect((err as FieldedApiError).status).toBe(409);
      }
    });
  });
});
