/**
 * Typed API client for the FIELDed backend.
 *
 * All request include proper authentication headers
 * and structured error handling.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
}

interface ApiErrorResponse {
  error: ApiError;
}

export class FieldedApiError extends Error {
  constructor(
    public status: number,
    public error: ApiError,
  ) {
    super(error.message);
    this.name = "FieldedApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_URL}/api/v1${path}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  // Attach auth token if available
  const token = getStoredToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    // FastAPI's default error shape is {detail: "..."}, not {error: {...}} —
    // fall back so unexpected responses produce a readable message.
    const apiError: ApiError =
      body?.error ?? {
        code: `HTTP_${response.status}`,
        message:
          body?.detail ?? `Request failed with status ${response.status}`,
      };
    throw new FieldedApiError(response.status, apiError);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

// --- Auth ---

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  is_active: boolean;
  is_verified: boolean;
  customer_profile?: {
    first_name: string;
    last_name: string;
    phone?: string;
    status?: string;
  };
}

export const auth = {
  register(data: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
  }): Promise<UserResponse> {
    return request("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  login(data: { email: string; password: string }): Promise<TokenResponse> {
    return request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  logout(refreshToken?: string): Promise<{ message: string }> {
    return request("/auth/logout", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken || undefined }),
    });
  },

  refresh(refreshToken: string): Promise<TokenResponse> {
    return request<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  },

  me(): Promise<UserResponse> {
    return request("/auth/me");
  },

  verifyEmail(token: string): Promise<{ message: string }> {
    return request("/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
  },

  forgotPassword(email: string): Promise<{ message: string }> {
    return request("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  },

  resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
    return request("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  },
};

// --- Customer Profile ---

export interface CustomerProfile {
  id: string;
  user_id: string;
  first_name: string;
  last_name: string;
  phone: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CustomerProfileUpdate {
  first_name?: string;
  last_name?: string;
  phone?: string;
  address_line1?: string;
  address_line2?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  country?: string;
}

export const customer = {
  getProfile(): Promise<CustomerProfile> {
    return request("/customer/profile");
  },

  updateProfile(data: CustomerProfileUpdate): Promise<CustomerProfile> {
    return request("/customer/profile", {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },
};

// --- Businesses ---

export interface BusinessSummary {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface SocialLinks {
  website: string | null;
  facebook: string | null;
  instagram: string | null;
  linkedin: string | null;
}

export interface BusinessProfileData {
  description: string | null;
  phone: string | null;
  email: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  service_area: Record<string, unknown> | null;
  social_links: SocialLinks | null;
  logo_url: string | null;
  cover_image_url: string | null;
  public_status: string;
  is_verified: boolean;
  average_rating: number | null;
  review_count: number;
}

export interface BusinessDetail extends BusinessSummary {
  profile: BusinessProfileData | null;
}

export interface BusinessMember {
  id: string;
  user_id: string;
  business_id: string;
  role: string;
  user_email: string | null;
  created_at: string;
}

export interface MemberInvitationData {
  id: string;
  business_id: string;
  email: string;
  role: string;
  expires_at: string;
  created_at: string;
}

export const businesses = {
  list(): Promise<BusinessSummary[]> {
    return request("/businesses");
  },

  get(businessId: string): Promise<BusinessDetail> {
    return request(`/businesses/${businessId}`);
  },

  create(data: { name: string; slug: string }): Promise<BusinessSummary> {
    return request("/businesses", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  update(businessId: string, data: Record<string, unknown>): Promise<BusinessDetail> {
    return request(`/businesses/${businessId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  getProfile(businessId: string): Promise<BusinessProfileData> {
    return request(`/businesses/${businessId}/profile`);
  },

  updateProfile(businessId: string, data: Record<string, unknown>): Promise<BusinessProfileData> {
    return request(`/businesses/${businessId}/profile`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  listMembers(businessId: string): Promise<BusinessMember[]> {
    return request(`/businesses/${businessId}/members`);
  },

  addMember(businessId: string, userEmail: string, role: string = "staff"): Promise<BusinessMember> {
    return request(`/businesses/${businessId}/members`, {
      method: "POST",
      body: JSON.stringify({ user_email: userEmail, role }),
    });
  },

  removeMember(businessId: string, memberId: string): Promise<{ message: string }> {
    return request(`/businesses/${businessId}/members/${memberId}`, {
      method: "DELETE",
    });
  },

  inviteMember(businessId: string, email: string, role: string = "staff"): Promise<MemberInvitationData> {
    return request(`/businesses/${businessId}/members/invite`, {
      method: "POST",
      body: JSON.stringify({ email, role }),
    });
  },

  listInvitations(businessId: string): Promise<MemberInvitationData[]> {
    return request(`/businesses/${businessId}/members/invitations`);
  },

  updateMemberRole(businessId: string, memberId: string, role: string): Promise<BusinessMember> {
    return request(`/businesses/${businessId}/members/${memberId}`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    });
  },

  /** Accept a pending invitation with the signed-in account. */
  acceptInvitation(token: string): Promise<BusinessMember> {
    return request(`/members/accept-invitation/${token}`, {
      method: "POST",
    });
  },
};

// --- Service Categories ---

export interface ServiceCategory {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  parent_id: string | null;
  created_at: string;
  updated_at: string;
}

export const categories = {
  list(): Promise<ServiceCategory[]> {
    return request("/categories");
  },

  listRoots(): Promise<ServiceCategory[]> {
    return request("/categories/roots");
  },
};

// --- Service Offers ---

export interface ServiceOffer {
  id: string;
  business_id: string;
  category_id: string | null;
  name: string;
  slug: string;
  description: string | null;
  delivery_mode: string;
  pricing_model: string;
  pricing_config: Record<string, unknown> | null;
  qualification_requirements: Record<string, unknown> | null;
  booking_rules: Record<string, unknown> | null;
  cancellation_policy: Record<string, unknown> | null;
  service_area: Record<string, unknown> | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ServiceOfferCreate {
  name: string;
  category_id?: string;
  description?: string;
  delivery_mode?: string;
  pricing_model?: string;
  pricing_config?: Record<string, unknown>;
  qualification_requirements?: Record<string, unknown>;
  booking_rules?: Record<string, unknown>;
  cancellation_policy?: Record<string, unknown>;
  service_area?: Record<string, unknown>;
}

export interface ServiceOfferUpdate {
  name?: string;
  description?: string;
  delivery_mode?: string;
  pricing_model?: string;
  pricing_config?: Record<string, unknown>;
  qualification_requirements?: Record<string, unknown>;
  booking_rules?: Record<string, unknown>;
  cancellation_policy?: Record<string, unknown>;
  service_area?: Record<string, unknown>;
  category_id?: string;
}

export const serviceOffers = {
  list(businessId: string): Promise<ServiceOffer[]> {
    return request(`/businesses/${businessId}/offers`);
  },

  get(businessId: string, offerId: string): Promise<ServiceOffer> {
    return request(`/businesses/${businessId}/offers/${offerId}`);
  },

  create(businessId: string, data: ServiceOfferCreate): Promise<ServiceOffer> {
    return request(`/businesses/${businessId}/offers`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  update(businessId: string, offerId: string, data: ServiceOfferUpdate): Promise<ServiceOffer> {
    return request(`/businesses/${businessId}/offers/${offerId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  transition(businessId: string, offerId: string, targetStatus: string): Promise<ServiceOffer> {
    return request(`/businesses/${businessId}/offers/${offerId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus }),
    });
  },
};

// --- Public ---

export interface PublicServiceOffer {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  delivery_mode: string;
  pricing_model: string;
  category_name: string | null;
  category_slug: string | null;
}

export interface PublicPricingSummary {
  pricing_model: string;
  starting_price: string | null;
  hourly_rate: string | null;
  fixed_price: string | null;
  currency: string | null;
}

export interface PublicServiceOfferDetail extends PublicServiceOffer {
  business_id: string;
  business_name: string;
  business_slug: string;
  business_is_verified: boolean;
  pricing_summary: PublicPricingSummary | null;
  service_area: Record<string, unknown> | null;
  qualification_requirements: Record<string, unknown> | null;
}

export interface PublicBusinessProfile {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  phone: string | null;
  email: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  service_area: Record<string, unknown> | null;
  social_links: SocialLinks | null;
  logo_url: string | null;
  cover_image_url: string | null;
  is_verified: boolean;
  average_rating: number | null;
  review_count: number;
  service_offers: PublicServiceOffer[];
  active_offer_count: number;
}

export interface PublicBusinessDirectoryItem {
  name: string;
  slug: string;
  description: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  logo_url: string | null;
  is_verified: boolean;
  average_rating: number | null;
  review_count: number;
  active_offer_count: number;
  top_categories: string[];
}

export interface PublicBusinessDirectoryResponse {
  businesses: PublicBusinessDirectoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export const publicApi = {
  getBusiness(slug: string): Promise<PublicBusinessProfile> {
    return request(`/public/business/${slug}`);
  },

  getBusinessServices(slug: string): Promise<PublicServiceOffer[]> {
    return request(`/public/business/${slug}/services`);
  },

  getServiceDetail(slug: string, offerSlug: string): Promise<PublicServiceOfferDetail> {
    return request(`/public/business/${slug}/services/${offerSlug}`);
  },

  listBusinesses(params?: {
    limit?: number;
    offset?: number;
    city?: string;
    country?: string;
    category?: string;
  }): Promise<PublicBusinessDirectoryResponse> {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    if (params?.city) qs.set("city", params.city);
    if (params?.country) qs.set("country", params.country);
    if (params?.category) qs.set("category", params.category);
    const query = qs.toString();
    return request(`/public/businesses${query ? `?${query}` : ""}`);
  },
};

// --- Discovery ---

export interface MatchedServiceOffer {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  delivery_mode: string;
  pricing_model: string;
  category_name: string | null;
  category_slug: string | null;
  match_reason: string | null;
}

export interface MatchedBusiness {
  business_id: string;
  business_name: string;
  business_slug: string;
  description: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  is_verified: boolean;
  logo_url: string | null;
  service_offers: MatchedServiceOffer[];
}

export interface DiscoveryResponse {
  status: string;
  matches: MatchedBusiness[];
  total_matches: number;
  categories_searched: string[];
  clarification: string | null;
  intent_summary: Record<string, unknown>;
}

export const discovery = {
  search(query: string, location?: { city?: string; state?: string; country?: string }): Promise<DiscoveryResponse> {
    return request("/discovery/search", {
      method: "POST",
      body: JSON.stringify({ query, ...location }),
    });
  },

  structured(data: {
    category_slug?: string;
    keywords?: string[];
    location_city?: string;
    location_state?: string;
    location_country?: string;
  }): Promise<DiscoveryResponse> {
    return request("/discovery/structured", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
};

// --- Health ---

export const health = {
  check(): Promise<{ status: string }> {
    return request("/health");
  },
};

// --- Enquiries ---

export interface EnquiryData {
  id: string;
  reference: string;
  customer_id: string;
  business_id: string;
  service_offer_id: string;
  subject: string;
  message: string;
  status: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface EnquiryCreateRequest {
  service_offer_id: string;
  subject: string;
  message: string;
}

export interface MessageData {
  id: string;
  conversation_id: string;
  sender_id: string;
  sender_type: string;
  content: string;
  message_type: string;
  delivered_at: string | null;
  read_at: string | null;
  created_at: string;
}

export interface ConversationData {
  id: string;
  enquiry_id: string;
  customer_id: string;
  business_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  messages: MessageData[];
}

export const enquiries = {
  /** Customer: create an enquiry for a business's service offer */
  create(businessId: string, data: EnquiryCreateRequest): Promise<EnquiryData> {
    return request(`/enquiries/${businessId}/enquiries`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /** Customer: list my enquiries */
  listMine(params?: { status?: string; limit?: number; offset?: number }): Promise<EnquiryData[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const query = qs.toString();
    return request(`/enquiries/my-enquiries${query ? `?${query}` : ""}`);
  },

  /** Customer: get my enquiry */
  getMyEnquiry(enquiryId: string): Promise<EnquiryData> {
    return request(`/enquiries/my-enquiries/${enquiryId}`);
  },

  /** Customer: get enquiry conversation with messages */
  getConversation(enquiryId: string): Promise<ConversationData> {
    return request(`/enquiries/my-enquiries/${enquiryId}/conversation`);
  },

  /** Customer: list messages */
  listMessages(enquiryId: string): Promise<MessageData[]> {
    return request(`/enquiries/my-enquiries/${enquiryId}/messages`);
  },

  /** Customer: send a message */
  sendMessage(enquiryId: string, content: string): Promise<MessageData> {
    return request(`/enquiries/my-enquiries/${enquiryId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  },

  /** Customer: transition my enquiry */
  transition(enquiryId: string, targetStatus: string): Promise<EnquiryData> {
    return request(`/enquiries/my-enquiries/${enquiryId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus }),
    });
  },

  /** Business: list enquiries for a business */
  listForBusiness(businessId: string, params?: { status?: string }): Promise<EnquiryData[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    const query = qs.toString();
    return request(`/businesses/${businessId}/enquiries${query ? `?${query}` : ""}`);
  },

  /** Business: get a specific enquiry */
  getBusinessEnquiry(businessId: string, enquiryId: string): Promise<EnquiryData> {
    return request(`/businesses/${businessId}/enquiries/${enquiryId}`);
  },

  /** Business: get enquiry conversation with messages */
  getBusinessConversation(businessId: string, enquiryId: string): Promise<ConversationData> {
    return request(`/businesses/${businessId}/enquiries/${enquiryId}/conversation`);
  },

  /** Business: send a message as business */
  sendBusinessMessage(businessId: string, enquiryId: string, content: string): Promise<MessageData> {
    return request(`/businesses/${businessId}/enquiries/${enquiryId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  },

  /** Business: transition enquiry */
  transitionBusiness(businessId: string, enquiryId: string, targetStatus: string): Promise<EnquiryData> {
    return request(`/businesses/${businessId}/enquiries/${enquiryId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus }),
    });
  },
};

// --- Business Brain ---

export interface BrainVersionDetail {
  id: string;
  brain_id: string;
  version_number: number;
  status: string;
  identity_config: Record<string, unknown> | null;
  services_config: Record<string, unknown> | null;
  pricing_config: Record<string, unknown> | null;
  availability_config: Record<string, unknown> | null;
  qualification_config: Record<string, unknown> | null;
  policies_config: Record<string, unknown> | null;
  escalation_config: Record<string, unknown> | null;
  communication_config: Record<string, unknown> | null;
  rules: BusinessRuleDetail[];
  created_at: string;
  updated_at: string;
}

export interface BrainVersionSummary {
  id: string;
  brain_id: string;
  version_number: number;
  status: string;
  identity_config: Record<string, unknown> | null;
  services_config: Record<string, unknown> | null;
  pricing_config: Record<string, unknown> | null;
  availability_config: Record<string, unknown> | null;
  qualification_config: Record<string, unknown> | null;
  policies_config: Record<string, unknown> | null;
  escalation_config: Record<string, unknown> | null;
  communication_config: Record<string, unknown> | null;
  rule_count: number;
  created_at: string;
  updated_at: string;
}

export interface BusinessRuleDetail {
  id: string;
  brain_version_id: string;
  rule_type: string;
  name: string;
  description: string | null;
  rule_data: Record<string, unknown>;
  priority: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface BusinessBrainDetail {
  id: string;
  business_id: string;
  active_version_id: string | null;
  active_version: BrainVersionDetail | null;
  version_count: number;
  created_at: string;
  updated_at: string;
}

export interface BusinessBrainSummary {
  id: string;
  business_id: string;
  active_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ValidationResult {
  valid: boolean;
  error_count: number;
  errors: Array<{
    field: string;
    message: string;
    code: string;
  }>;
}

export interface TransitionResult {
  id: string;
  previous_status: string;
  current_status: string;
  version_number: number;
}

export interface ApprovalResult {
  decision: string;
  version_id: string;
  version_status: string;
  approver_role: string;
  comment: string | null;
}

export interface ProvenanceEntry {
  action: string;
  actor_id: string | null;
  timestamp: string;
  details: Record<string, unknown>;
}

export interface Provenance {
  version_id: string;
  brain_id: string;
  version_number: number;
  status: string;
  entries: ProvenanceEntry[];
}

export const brain = {
  getDetail(businessId: string): Promise<BusinessBrainDetail> {
    return request(`/businesses/${businessId}/brain`);
  },

  listVersions(businessId: string): Promise<BrainVersionSummary[]> {
    return request(`/businesses/${businessId}/brain/versions`);
  },

  getVersion(businessId: string, versionId: string): Promise<BrainVersionDetail> {
    return request(`/businesses/${businessId}/brain/versions/${versionId}`);
  },

  createVersion(businessId: string, config?: Record<string, unknown>): Promise<BrainVersionDetail> {
    return request(`/businesses/${businessId}/brain/versions`, {
      method: "POST",
      body: JSON.stringify({ config: config || {} }),
    });
  },

  updateVersion(
    businessId: string,
    versionId: string,
    data: Record<string, unknown>,
  ): Promise<BrainVersionDetail> {
    return request(`/businesses/${businessId}/brain/versions/${versionId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  addRule(
    businessId: string,
    versionId: string,
    data: {
      rule_type: string;
      name: string;
      description?: string;
      rule_data?: Record<string, unknown>;
      priority?: number;
    },
  ): Promise<BusinessRuleDetail> {
    return request(`/businesses/${businessId}/brain/versions/${versionId}/rules`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  updateRule(
    businessId: string,
    versionId: string,
    ruleId: string,
    data: Record<string, unknown>,
  ): Promise<BusinessRuleDetail> {
    return request(`/businesses/${businessId}/brain/versions/${versionId}/rules/${ruleId}`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  deleteRule(businessId: string, versionId: string, ruleId: string): Promise<void> {
    return request(`/businesses/${businessId}/brain/versions/${versionId}/rules/${ruleId}`, {
      method: "DELETE",
    });
  },

  validate(businessId: string, versionId: string): Promise<ValidationResult> {
    return request(`/businesses/${businessId}/brain/versions/${versionId}/validate`, {
      method: "POST",
    });
  },

  transition(
    businessId: string,
    versionId: string,
    targetStatus: string,
  ): Promise<TransitionResult> {
    return request(`/businesses/${businessId}/brain/versions/${versionId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus }),
    });
  },

  approve(
    businessId: string,
    versionId: string,
    comment?: string,
  ): Promise<ApprovalResult> {
    return request(`/businesses/${businessId}/brain/versions/${versionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    });
  },

  activate(businessId: string, versionId: string): Promise<BusinessBrainSummary> {
    return request(`/businesses/${businessId}/brain/versions/${versionId}/activate`, {
      method: "POST",
    });
  },

  getProvenance(businessId: string, versionId: string): Promise<Provenance> {
    return request(`/businesses/${businessId}/brain/versions/${versionId}/provenance`);
  },
};

// --- Brain Conversation (Interactive Co-Brain) ---

export interface BrainMessageData {
  id: string;
  conversation_id: string;
  role: "brain" | "owner" | "system";
  content: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface BrainConversationSummary {
  id: string;
  brain_id: string;
  status: string;
  title: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface BrainConversationDetail {
  id: string;
  brain_id: string;
  business_id: string;
  status: string;
  title: string | null;
  context_summary: string | null;
  messages: BrainMessageData[];
  created_at: string;
  updated_at: string;
}

export interface BrainProposalData {
  id: string;
  brain_id: string;
  conversation_id: string | null;
  business_id: string;
  proposal_type: string;
  status: string;
  confidence: number;
  reasoning_summary: string | null;
  proposed_change: Record<string, unknown>;
  affected_area: string | null;
  source_message_id: string | null;
  resolved_at: string | null;
  is_urgent: boolean;
  created_at: string;
  updated_at: string;
}

export interface SendMessageResponse {
  owner_message: BrainMessageData;
  brain_message: BrainMessageData;
}

export interface KnowledgeSummary {
  known: Array<{
    id: string;
    type: string;
    summary: string;
    affected_area: string;
    confidence: number;
    created_at: string;
  }>;
  proposed: Array<{
    id: string;
    type: string;
    summary: string;
    affected_area: string;
    confidence: number;
    created_at: string;
  }>;
  rejected: Array<{
    id: string;
    type: string;
    summary: string;
    affected_area: string;
    confidence: number;
    created_at: string;
  }>;
  active_config_areas: string[];
  missing_areas: string[];
  has_active_version: boolean;
}

export interface NeedsAttentionItem {
  type: string;
  id: string | null;
  title: string;
  affected_area: string | null;
  is_urgent: boolean;
  confidence: number | null;
  proposal_type: string | null;
}

export interface BrainContext {
  knowledge: KnowledgeSummary;
  attention: NeedsAttentionItem[];
  active_config_summary: string;
}

export const brainConversation = {
  /** Get or create the active conversation for the Brain */
  getActive(businessId: string): Promise<BrainConversationDetail> {
    return request(`/businesses/${businessId}/brain/conversations/active`);
  },

  /** List all conversations for the Brain */
  list(businessId: string): Promise<BrainConversationSummary[]> {
    return request(`/businesses/${businessId}/brain/conversations`);
  },

  /** Get a specific conversation with messages */
  get(businessId: string, conversationId: string): Promise<BrainConversationDetail> {
    return request(`/businesses/${businessId}/brain/conversations/${conversationId}`);
  },

  /** Send a message from the owner to the Brain */
  sendMessage(
    businessId: string,
    conversationId: string,
    content: string,
  ): Promise<SendMessageResponse> {
    return request(`/businesses/${businessId}/brain/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  },

  /** Archive a conversation */
  archive(businessId: string, conversationId: string): Promise<BrainConversationDetail> {
    return request(`/businesses/${businessId}/brain/conversations/${conversationId}/archive`, {
      method: "POST",
    });
  },

  /** List all proposals for the Brain */
  listProposals(businessId: string): Promise<BrainProposalData[]> {
    return request(`/businesses/${businessId}/brain/proposals`);
  },

  /** List pending proposals awaiting owner decision */
  listPendingProposals(businessId: string): Promise<BrainProposalData[]> {
    return request(`/businesses/${businessId}/brain/proposals/pending`);
  },

  /** Approve a proposal (optionally with edits) */
  approveProposal(
    businessId: string,
    proposalId: string,
    editedChange?: Record<string, unknown>,
  ): Promise<BrainProposalData> {
    return request(`/businesses/${businessId}/brain/proposals/${proposalId}/approve`, {
      method: "POST",
      body: JSON.stringify({ edited_change: editedChange }),
    });
  },

  /** Reject a proposal */
  rejectProposal(businessId: string, proposalId: string): Promise<BrainProposalData> {
    return request(`/businesses/${businessId}/brain/proposals/${proposalId}/reject`, {
      method: "POST",
    });
  },

  /** Get Brain knowledge summary */
  getKnowledge(businessId: string): Promise<KnowledgeSummary> {
    return request(`/businesses/${businessId}/brain/knowledge`);
  },

  /** Get items needing owner attention */
  getNeedsAttention(businessId: string): Promise<NeedsAttentionItem[]> {
    return request(`/businesses/${businessId}/brain/needs-attention`);
  },

  /** Get full Brain context (knowledge + attention + config) */
  getContext(businessId: string): Promise<BrainContext> {
    return request(`/businesses/${businessId}/brain/context`);
  },
};

// --- Quotes ---

export interface QuoteData {
  id: string;
  reference: string;
  customer_id: string;
  business_id: string;
  enquiry_id: string;
  service_offer_id: string;
  amount: string;
  currency: string;
  status: string;
  brain_version_id: string | null;
  pricing_evidence: Record<string, unknown> | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuoteCreateRequest {
  enquiry_id: string;
  notes?: string;
}

export const quotes = {
  /** Business: create a quote for an enquiry */
  create(businessId: string, data: QuoteCreateRequest): Promise<QuoteData> {
    return request(`/businesses/${businessId}/quotes`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /** Business: list quotes for a business */
  listForBusiness(businessId: string, params?: { status?: string }): Promise<QuoteData[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    const query = qs.toString();
    return request(`/businesses/${businessId}/quotes${query ? `?${query}` : ""}`);
  },

  /** Business: get a specific quote */
  getBusinessQuote(businessId: string, quoteId: string): Promise<QuoteData> {
    return request(`/businesses/${businessId}/quotes/${quoteId}`);
  },

  /** Business: transition a quote */
  transitionBusiness(businessId: string, quoteId: string, targetStatus: string): Promise<QuoteData> {
    return request(`/businesses/${businessId}/quotes/${quoteId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus }),
    });
  },

  /** Customer: list my quotes */
  listMine(params?: { status?: string }): Promise<QuoteData[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    const query = qs.toString();
    return request(`/businesses/my-quotes${query ? `?${query}` : ""}`);
  },

  /** Customer: get my quote */
  getMyQuote(quoteId: string): Promise<QuoteData> {
    return request(`/businesses/my-quotes/${quoteId}`);
  },

  /** Customer: accept or decline a quote */
  transitionMyQuote(quoteId: string, targetStatus: string): Promise<QuoteData> {
    return request(`/businesses/my-quotes/${quoteId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus }),
    });
  },
};

// --- Bookings ---

export interface BookingData {
  id: string;
  reference: string;
  customer_id: string;
  business_id: string;
  quote_id: string;
  enquiry_id: string;
  service_offer_id: string;
  requested_at: string;
  currency: string;
  status: string;
  brain_version_id: string | null;
  decision_evidence: Record<string, unknown> | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface BookingCreateRequest {
  quote_id: string;
  requested_at: string;
  notes?: string;
}

export interface AvailabilityCheckRequest {
  service_offer_id: string;
  requested_at: string;
}

export interface AvailabilityCheckResponse {
  available: boolean;
  requested_at: string;
  reason: string;
  brain_version_id: string | null;
  matched_rules: Array<Record<string, unknown>>;
  blocked_by: string[];
}

export const bookings = {
  /** Customer: create a booking from an accepted quote */
  create(data: BookingCreateRequest): Promise<BookingData> {
    return request(`/businesses/my-bookings`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /** Customer: list my bookings */
  listMine(params?: { status?: string }): Promise<BookingData[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    const query = qs.toString();
    return request(`/businesses/my-bookings${query ? `?${query}` : ""}`);
  },

  /** Customer: get my booking */
  getMyBooking(bookingId: string): Promise<BookingData> {
    return request(`/businesses/my-bookings/${bookingId}`);
  },

  /** Customer: cancel my booking */
  cancelMyBooking(bookingId: string): Promise<BookingData> {
    return request(`/businesses/my-bookings/${bookingId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_status: "cancelled" }),
    });
  },

  /** Customer: transition my booking (accept proposed, cancel, etc.) */
  transitionMyBooking(bookingId: string, targetStatus: string): Promise<BookingData> {
    return request(`/businesses/my-bookings/${bookingId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus }),
    });
  },

  /** Customer: pay for a completed booking's invoice (deterministic key → idempotent) */
  payMyBooking(bookingId: string, paymentMethod: string = "card"): Promise<PaymentData> {
    return request(`/businesses/my-bookings/${bookingId}/pay`, {
      method: "POST",
      body: JSON.stringify({
        payment_method: paymentMethod,
        idempotency_key: `booking-pay-${bookingId}`,
      }),
    });
  },

  /** Business: list bookings for a business */
  listForBusiness(businessId: string, params?: { status?: string }): Promise<BookingData[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    const query = qs.toString();
    return request(`/businesses/${businessId}/bookings${query ? `?${query}` : ""}`);
  },

  /** Business: get a specific booking */
  getBusinessBooking(businessId: string, bookingId: string): Promise<BookingData> {
    return request(`/businesses/${businessId}/bookings/${bookingId}`);
  },

  /** Business: transition a booking */
  transitionBusiness(businessId: string, bookingId: string, targetStatus: string): Promise<BookingData> {
    return request(`/businesses/${businessId}/bookings/${bookingId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus }),
    });
  },

  /** Business: check availability */
  checkAvailability(businessId: string, data: AvailabilityCheckRequest): Promise<AvailabilityCheckResponse> {
    return request(`/businesses/${businessId}/availability`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
};

// --- Phase 13: Service Executions ---

export interface ServiceExecutionData {
  id: string;
  business_id: string;
  customer_id: string;
  booking_id: string;
  service_offer_id: string;
  quote_id: string | null;
  status: string;
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  completed_by: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export const serviceExecutions = {
  listForBusiness(businessId: string, status?: string): Promise<ServiceExecutionData[]> {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return request(`/businesses/${businessId}/service-executions${qs}`);
  },

  getForBusiness(businessId: string, executionId: string): Promise<ServiceExecutionData> {
    return request(`/businesses/${businessId}/service-executions/${executionId}`);
  },

  create(businessId: string, bookingId: string): Promise<ServiceExecutionData> {
    return request(`/businesses/${businessId}/service-executions`, {
      method: "POST",
      body: JSON.stringify({ booking_id: bookingId }),
    });
  },

  transition(businessId: string, executionId: string, targetStatus: string, notes?: string): Promise<ServiceExecutionData> {
    return request(`/businesses/${businessId}/service-executions/${executionId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_status: targetStatus, notes }),
    });
  },

  complete(businessId: string, executionId: string): Promise<ServiceExecutionData> {
    return request(`/businesses/${businessId}/service-executions/${executionId}/complete`, {
      method: "POST",
    });
  },

  listMy(status?: string): Promise<ServiceExecutionData[]> {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return request(`/businesses/my-service-executions${qs}`);
  },
};

// --- Phase 13: Invoices ---

export interface InvoiceLineItemData {
  id: string;
  description: string;
  quantity: string;
  unit_price: string;
  discount: string;
  tax: string;
  line_total: string;
  currency: string;
}

export interface InvoiceData {
  id: string;
  business_id: string;
  customer_id: string;
  service_execution_id: string;
  booking_id: string;
  invoice_number: string;
  issue_date: string;
  due_date: string | null;
  currency: string;
  subtotal: string;
  discount: string;
  tax: string;
  total: string;
  payment_status: string;
  status: string;
  notes: string | null;
  line_items: InvoiceLineItemData[];
  created_at: string;
}

export const invoices = {
  listForBusiness(businessId: string, paymentStatus?: string): Promise<InvoiceData[]> {
    const params = new URLSearchParams();
    if (paymentStatus) params.set("payment_status", paymentStatus);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return request(`/businesses/${businessId}/invoices${qs}`);
  },

  getForBusiness(businessId: string, invoiceId: string): Promise<InvoiceData> {
    return request(`/businesses/${businessId}/invoices/${invoiceId}`);
  },

  getPdfUrl(businessId: string, invoiceId: string): string {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return `${apiUrl}/api/v1/businesses/${businessId}/invoices/${invoiceId}/pdf`;
  },

  updatePaymentStatus(businessId: string, invoiceId: string, paymentStatus: string): Promise<InvoiceData> {
    return request(`/businesses/${businessId}/invoices/${invoiceId}/payment`, {
      method: "PATCH",
      body: JSON.stringify({ payment_status: paymentStatus }),
    });
  },

  listMy(paymentStatus?: string): Promise<InvoiceData[]> {
    const params = new URLSearchParams();
    if (paymentStatus) params.set("payment_status", paymentStatus);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return request(`/businesses/my-invoices${qs}`);
  },

  getMyPdfUrl(invoiceId: string): string {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return `${apiUrl}/api/v1/businesses/my-invoices/${invoiceId}/pdf`;
  },
};

// --- Phase 13: Ledger ---

export interface LedgerEntryData {
  id: string;
  business_id: string;
  customer_id: string;
  service_execution_id: string;
  booking_id: string;
  invoice_id: string | null;
  service_offer_id: string;
  completion_date: string;
  gross_amount: string;
  discount: string;
  tax: string;
  net_amount: string;
  currency: string;
  payment_status: string;
  is_primary: boolean;
  transaction_reference: string | null;
  notes: string | null;
}

export interface LedgerSummaryData {
  total_entries: number;
  total_gross: string;
  total_discount: string;
  total_tax: string;
  total_net: string;
  paid_amount: string;
  outstanding_amount: string;
}

export const ledger = {
  listForBusiness(businessId: string, params?: {
    payment_status?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<LedgerEntryData[]> {
    const qs = new URLSearchParams();
    if (params?.payment_status) qs.set("payment_status", params.payment_status);
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return request(`/businesses/${businessId}/ledger${query}`);
  },

  getSummary(businessId: string, params?: {
    date_from?: string;
    date_to?: string;
  }): Promise<LedgerSummaryData> {
    const qs = new URLSearchParams();
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return request(`/businesses/${businessId}/ledger/summary${query}`);
  },

  getCsvUrl(businessId: string): string {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return `${apiUrl}/api/v1/businesses/${businessId}/ledger/export/csv`;
  },

  getPdfUrl(businessId: string): string {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return `${apiUrl}/api/v1/businesses/${businessId}/ledger/export/pdf`;
  },
};

// --- Notifications ---

export interface NotificationData {
  id: string;
  business_id: string | null;
  customer_id: string | null;
  notification_type: string;
  title: string;
  body: string;
  is_read: boolean;
  related_entity_type: string | null;
  related_entity_id: string | null;
  created_at: string;
}

export const notifications = {
  /** Customer: list my notifications */
  listMy(limit = 20): Promise<NotificationData[]> {
    return request<{ items: NotificationData[] }>(`/notifications/my-notifications?limit=${limit}`).then(
      (r) => r.items
    );
  },

  /** Customer: mark notification as read */
  markRead(notificationId: string): Promise<void> {
    return request(`/notifications/my-notifications/${notificationId}/read`, { method: "POST" });
  },

  /** Customer: get unread count */
  async unreadCount(): Promise<number> {
    const items = await this.listMy(50);
    return items.filter((n) => !n.is_read).length;
  },
};

// --- Phase 14A: Communications ---

export interface CommunicationListData {
  id: string;
  business_id: string;
  customer_id: string | null;
  channel: string;
  purpose: string;
  status: string;
  provider_reference: string | null;
  created_at: string;
}

export interface CommunicationDetail extends CommunicationListData {
  idempotency_key: string;
  brain_version_id: string | null;
  decision_evidence: Record<string, unknown> | null;
  enquiry_id: string | null;
  quote_id: string | null;
  booking_id: string | null;
  service_execution_id: string | null;
  invoice_id: string | null;
  updated_at: string;
}

export interface ChannelConfigData {
  id: string;
  business_id: string;
  channel: string;
  enabled: boolean;
  provider_ref: string | null;
  settings: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ChannelConfigUpdate {
  enabled?: boolean;
  provider_ref?: string | null;
  settings?: Record<string, unknown> | null;
}

export interface PurposeConfigData {
  id: string;
  business_id: string;
  purpose: string;
  enabled: boolean;
  permitted_channels: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface PurposeConfigUpdate {
  enabled?: boolean;
  permitted_channels?: Record<string, unknown> | null;
}

export interface CommunicationTemplateData {
  id: string;
  business_id: string;
  channel: string;
  purpose: string;
  name: string;
  active_version_id: string | null;
  status: string;
  approval_state: string;
  created_at: string;
  updated_at: string;
}

export const communications = {
  listChannels(businessId: string): Promise<ChannelConfigData[]> {
    return request(`/${businessId}/communication-config/channels`);
  },

  upsertChannel(businessId: string, channel: string, data: ChannelConfigUpdate): Promise<ChannelConfigData> {
    return request(`/${businessId}/communication-config/channels/${channel}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  listPurposes(businessId: string): Promise<PurposeConfigData[]> {
    return request(`/${businessId}/communication-config/purposes`);
  },

  upsertPurpose(businessId: string, purpose: string, data: PurposeConfigUpdate): Promise<PurposeConfigData> {
    return request(`/${businessId}/communication-config/purposes/${purpose}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  listForBusiness(businessId: string, params?: {
    channel?: string;
    purpose?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<CommunicationListData[]> {
    const qs = new URLSearchParams();
    if (params?.channel) qs.set("channel", params.channel);
    if (params?.purpose) qs.set("purpose", params.purpose);
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return request(`/${businessId}/communications${query}`);
  },

  get(businessId: string, communicationId: string): Promise<CommunicationDetail> {
    return request(`/${businessId}/communications/${communicationId}`);
  },

  listTemplates(businessId: string): Promise<CommunicationTemplateData[]> {
    return request(`/${businessId}/communication-templates`);
  },

  activateTemplate(businessId: string, templateId: string): Promise<CommunicationTemplateData> {
    return request(`/${businessId}/communication-templates/${templateId}/activate`, {
      method: "POST",
    });
  },

  deactivateTemplate(businessId: string, templateId: string): Promise<CommunicationTemplateData> {
    return request(`/${businessId}/communication-templates/${templateId}/deactivate`, {
      method: "POST",
    });
  },
};

// --- Phase 14B/14C: Voice ---

export interface CallAgentConfigData {
  id: string;
  business_id: string;
  enabled: boolean;
  transactional_calling_enabled: boolean;
  marketing_calling_enabled: boolean;
  default_from_number: string | null;
  provider_reference: string | null;
  timezone: string | null;
  max_attempts: number;
  retry_interval_seconds: number;
  allowed_calling_hours: Record<string, unknown> | null;
  quiet_periods: Record<string, unknown>[] | null;
  max_daily_attempts: number | null;
  max_weekly_attempts: number | null;
  customer_frequency_limits: Record<string, unknown> | null;
  human_escalation_enabled: boolean;
  recording_enabled: boolean;
  transcription_enabled: boolean;
  agent_instructions: string | null;
  created_at: string;
  updated_at: string;
}

export interface CallAgentConfigUpdate {
  enabled?: boolean;
  transactional_calling_enabled?: boolean;
  marketing_calling_enabled?: boolean;
  default_from_number?: string | null;
  timezone?: string | null;
  max_attempts?: number;
  retry_interval_seconds?: number;
  allowed_calling_hours?: Record<string, unknown> | null;
  max_daily_attempts?: number | null;
  max_weekly_attempts?: number | null;
  human_escalation_enabled?: boolean;
  recording_enabled?: boolean;
  transcription_enabled?: boolean;
  agent_instructions?: string | null;
  webhook_signature_secret?: string | null;
}

export interface VoiceCallData {
  id: string;
  business_id: string;
  customer_id: string | null;
  call_type: string;
  purpose: string;
  status: string;
  to_number: string;
  from_number: string | null;
  provider: string;
  provider_reference: string | null;
  brain_version_id: string | null;
  communication_id: string | null;
  campaign_id: string | null;
  enquiry_id: string | null;
  quote_id: string | null;
  booking_id: string | null;
  service_execution_id: string | null;
  invoice_id: string | null;
  requested_at: string;
  authorized_at: string | null;
  queued_at: string | null;
  initiated_at: string | null;
  connected_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  failure_code: string | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface EscalationData {
  id: string;
  call_id: string;
  escalation_status: string;
  escalation_reason: string;
  requested_at: string;
  assigned_member_id: string | null;
  accepted_at: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
  created_at: string;
}

export const voice = {
  getAgentConfig(businessId: string): Promise<CallAgentConfigData> {
    return request(`/${businessId}/voice/agent-config`);
  },

  upsertAgentConfig(businessId: string, data: CallAgentConfigUpdate): Promise<CallAgentConfigData> {
    return request(`/${businessId}/voice/agent-config`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  listCalls(businessId: string, params?: {
    status?: string;
    purpose?: string;
    call_type?: string;
    limit?: number;
    offset?: number;
  }): Promise<VoiceCallData[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.purpose) qs.set("purpose", params.purpose);
    if (params?.call_type) qs.set("call_type", params.call_type);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return request(`/${businessId}/voice/calls${query}`);
  },

  getCall(businessId: string, callId: string): Promise<VoiceCallData> {
    return request(`/${businessId}/voice/calls/${callId}`);
  },

  cancelCall(businessId: string, callId: string, reason?: string): Promise<VoiceCallData> {
    return request(`/${businessId}/voice/calls/${callId}/cancel`, {
      method: "POST",
      body: JSON.stringify(reason ? { reason } : {}),
    });
  },

  listEscalations(businessId: string, callId: string): Promise<EscalationData[]> {
    return request(`/${businessId}/voice/calls/${callId}/escalations`);
  },
};

// --- Phase 15: Payments ---

export interface PaymentAttemptData {
  id: string;
  payment_id: string;
  attempt_number: number;
  provider: string;
  provider_reference: string | null;
  status: string;
  amount: string;
  currency: string;
  requested_at: string;
  completed_at: string | null;
  error_code: string | null;
  error_message: string | null;
  provider_response: Record<string, unknown> | null;
  created_at: string;
}

export interface PaymentData {
  id: string;
  idempotency_key: string;
  business_id: string;
  customer_id: string;
  invoice_id: string | null;
  amount: string;
  currency: string;
  payment_method: string;
  status: string;
  provider: string;
  provider_reference: string | null;
  refunded_amount: string;
  refund_provider_reference: string | null;
  paid_at: string | null;
  refunded_at: string | null;
  expires_at: string | null;
  provider_evidence: Record<string, unknown> | null;
  notes: string | null;
  failure_code: string | null;
  failure_message: string | null;
  attempts: PaymentAttemptData[];
  created_at: string;
  updated_at: string;
}

export interface PaymentCreateRequest {
  invoice_id: string;
  amount: string;
  currency: string;
  payment_method: string;
  idempotency_key: string;
  notes?: string;
}

export interface PaymentRefundRequest {
  amount?: string;
  reason?: string;
}

export interface InvoicePaymentStatusData {
  invoice_id: string;
  invoice_number: string;
  total: string;
  currency: string;
  paid_amount: string;
  outstanding_amount: string;
  payment_status: string;
  payments: PaymentData[];
}

export const payments = {
  /** Business: create a payment for an invoice */
  create(businessId: string, data: PaymentCreateRequest): Promise<PaymentData> {
    return request(`/businesses/${businessId}/payments`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /** Business: list payments for a business */
  listForBusiness(businessId: string, params?: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<PaymentData[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return request(`/businesses/${businessId}/payments${query}`);
  },

  /** Business: get a specific payment */
  getForBusiness(businessId: string, paymentId: string): Promise<PaymentData> {
    return request(`/businesses/${businessId}/payments/${paymentId}`);
  },

  /** Business: refund a payment */
  refund(businessId: string, paymentId: string, data: PaymentRefundRequest): Promise<PaymentData> {
    return request(`/businesses/${businessId}/payments/${paymentId}/refund`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /** Business: get invoice payment status */
  getInvoicePaymentStatus(businessId: string, invoiceId: string): Promise<InvoicePaymentStatusData> {
    return request(`/businesses/${businessId}/invoices/${invoiceId}/payment-status`);
  },

  /** Business: get transaction history */
  getTransactionHistory(businessId: string, params?: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<PaymentData[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return request(`/businesses/${businessId}/payments/transactions/history${query}`);
  },

  /** Customer: list my payments */
  listMine(params?: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<PaymentData[]> {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const query = qs.toString() ? `?${qs.toString()}` : "";
    return request(`/my-payments${query}`);
  },

  /** Customer: get my payment */
  getMyPayment(paymentId: string): Promise<PaymentData> {
    return request(`/my-payments/${paymentId}`);
  },
};

// --- Reviews ---

export interface ReviewData {
  id: string;
  business_id: string;
  customer_id: string;
  service_execution_id: string;
  booking_id: string;
  enquiry_id: string;
  service_offer_id: string;
  rating: number;
  title: string | null;
  body: string | null;
  status: string;
  response_body: string | null;
  responded_at: string | null;
  responded_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewCreateRequest {
  service_execution_id: string;
  rating: number;
  title?: string | null;
  body?: string | null;
}

export const reviews = {
  /** Customer: submit a review */
  create(data: ReviewCreateRequest): Promise<ReviewData> {
    return request(`/my-reviews`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /** Customer: list my reviews */
  listMine(params?: { limit?: number; offset?: number }): Promise<ReviewData[]> {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const query = qs.toString();
    return request<{ items: ReviewData[] }>(`/my-reviews${query ? `?${query}` : ""}`).then(
      (r) => r.items
    );
  },

  /** Customer: get my review */
  getMyReview(reviewId: string): Promise<ReviewData> {
    return request(`/my-reviews/${reviewId}`);
  },

  /** Public: get business reviews */
  getPublicBusinessReviews(slug: string): Promise<{
    items: ReviewData[];
    total: number;
    average_rating: number | null;
  }> {
    return request(`/public/business/${slug}/reviews`);
  },
};

// --- Token storage ---

const TOKEN_KEY = "fielded_access_token";
const REFRESH_KEY = "fielded_refresh_token";

export function storeTokens(tokens: TokenResponse): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(TOKEN_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  }
}

export function getStoredToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem(TOKEN_KEY);
  }
  return null;
}

export function getStoredRefreshToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem(REFRESH_KEY);
  }
  return null;
}

export function clearTokens(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }
}
