import { describe, it, expect, vi, beforeEach } from "vitest";
import { businesses, FieldedApiError, type BusinessDetail } from "@/lib/api-client";

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

const BUSINESS_ID = "3e2f6398-de3a-4abd-917c-1cd08ae8735f";

const pendingBusiness: BusinessDetail = {
  id: BUSINESS_ID,
  name: "Test Landscaping Co",
  slug: "test-landscaping-co",
  status: "pending",
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  profile: null,
};

const activeBusiness: BusinessDetail = {
  ...pendingBusiness,
  status: "active",
};

describe("Business Activation Flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock localStorage with a token so auth headers are attached
    const store: Record<string, string> = {
      fielded_access_token: "mock-jwt-token",
    };
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

  describe("businesses.transition() API client", () => {
    it("should POST to the correct endpoint with target_status", async () => {
      mockResponse(activeBusiness);

      const result = await businesses.transition(BUSINESS_ID, "active");

      expect(result.status).toBe("active");
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining(`/businesses/${BUSINESS_ID}/transition`),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ target_status: "active" }),
        }),
      );
    });

    it("should send Content-Type application/json", async () => {
      mockResponse(activeBusiness);

      await businesses.transition(BUSINESS_ID, "active");

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            "Content-Type": "application/json",
          }),
        }),
      );
    });

    it("should return the full BusinessDetail response", async () => {
      mockResponse(activeBusiness);

      const result = await businesses.transition(BUSINESS_ID, "active");

      expect(result.id).toBe(BUSINESS_ID);
      expect(result.name).toBe("Test Landscaping Co");
      expect(result.status).toBe("active");
      expect(result.slug).toBe("test-landscaping-co");
    });
  });

  describe("successful pending → active flow", () => {
    it("should transition from pending to active", async () => {
      // Mock the transition call
      mockResponse(activeBusiness);

      const result = await businesses.transition(BUSINESS_ID, "active");

      expect(result.status).toBe("active");
      expect(result.id).toBe(BUSINESS_ID);
    });

    it("should refresh business context after activation (list + get)", async () => {
      // Simulate the profile page flow: transition → list → get
      mockResponse(activeBusiness); // transition
      mockResponse([{ ...activeBusiness }]); // list
      mockResponse(activeBusiness); // get

      // Step 1: activate
      const transitionResult = await businesses.transition(BUSINESS_ID, "active");
      expect(transitionResult.status).toBe("active");

      // Step 2: refresh (as loadBusiness does)
      const bizList = await businesses.list();
      const detail = await businesses.get(bizList[0].id);

      expect(detail.status).toBe("active");
      expect(mockFetch).toHaveBeenCalledTimes(3);
    });
  });

  describe("failed transition handling", () => {
    it("should throw FieldedApiError on 403 (non-owner)", async () => {
      mockError(403, {
        code: "FORBIDDEN",
        message: "Owner role required for business activation",
      });

      try {
        await businesses.transition(BUSINESS_ID, "active");
        expect.fail("Should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(FieldedApiError);
        expect((err as FieldedApiError).status).toBe(403);
        expect((err as FieldedApiError).error.code).toBe("FORBIDDEN");
      }
    });

    it("should throw FieldedApiError on 409 (invalid transition)", async () => {
      mockError(409, {
        code: "STATE_TRANSITION_ERROR",
        message: "Cannot transition business from 'active' to 'active'.",
      });

      try {
        await businesses.transition(BUSINESS_ID, "active");
        expect.fail("Should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(FieldedApiError);
        expect((err as FieldedApiError).status).toBe(409);
        expect((err as FieldedApiError).error.code).toBe("STATE_TRANSITION_ERROR");
      }
    });

    it("should throw FieldedApiError on 404 (business not found)", async () => {
      mockError(404, {
        code: "NOT_FOUND",
        message: "Business not found",
      });

      try {
        await businesses.transition("nonexistent-id", "active");
        expect.fail("Should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(FieldedApiError);
        expect((err as FieldedApiError).status).toBe(404);
      }
    });
  });
});
