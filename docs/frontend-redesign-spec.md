# FIELDed Frontend Redesign — Specification

**Date**: 2026-09-19
**Status**: Approved for implementation planning
**Visual Reference**: PNG mockups in `frontend/src/components/ui/` (visual direction only, not literal reproduction)

---

## Non-Negotiable Principles

1. **Real FIELDed frontend, not a visual prototype.** The PNG establishes visual direction. The existing backend establishes functional authority. The existing API/client architecture establishes the integration boundary.
2. **No mock data, no fake API responses, no fabricated records.** Not in components, pages, demos, or loading states.
3. **No simulated success states.** "Publish", "Save", "Activate" controls must not claim success when no backend operation occurred.
4. **Honest unavailable states.** Where backend capability does not exist, the UI communicates that clearly. Never makes "not yet available" look like it has successfully executed.
5. **FIELDed branding throughout.** No unrelated product names (e.g., "Nova"). Business Brain is a FIELDed capability.
6. **Reuse existing architecture.** Inspect `frontend/src/components/ui/`, existing routes, API client, auth flow, and conventions before creating anything new. Do not create parallel implementations.

---

## Feature Classification

Every feature is classified as one of:

| Classification | Meaning | Rule |
|---|---|---|
| **REAL** | Backend endpoint/domain functionality exists | Connect via `api-client.ts`. Show real loading, empty, error, success states. |
| **STATIC** | Marketing, explanatory, instructional content | No backend needed. Content is fixed. |
| **NOT YET AVAILABLE** | UI concept exists but no backend capability | Show honest "not configured" / "coming soon" state. Never fake success or data. |

---

## 1. Design System

### 1.1 Visual Tokens

Applied via CSS custom properties in `globals.css`.

| Token | Value | Usage |
|---|---|---|
| `--bg-primary` | `#0B1120` | Page background |
| `--bg-surface` | `#111827` | Card/panel backgrounds |
| `--bg-elevated` | `#1E293B` | Hover states, modals, dropdowns |
| `--border-subtle` | `#1E293B` | Card borders |
| `--border-default` | `#334155` | Input borders, dividers |
| `--accent` | `#10B981` | Primary actions, active nav, highlights |
| `--accent-hover` | `#059669` | Hover state for accent |
| `--text-primary` | `#F1F5F9` | Headings, primary text |
| `--text-secondary` | `#94A3B8` | Body text, descriptions |
| `--text-muted` | `#64748B` | Timestamps, hints, placeholders |
| `--danger` | `#EF4444` | Error states, destructive actions |
| `--warning` | `#F59E0B` | Warning states |
| `--info` | `#3B82F6` | Info states |
| `--auth-light-bg` | `#F8FAFC` | Left panel of auth pages |

### 1.2 Typography

- Font: System sans-serif stack (prefers Inter if available)
- Scale: 12px → 14px → 16px → 18px → 20px → 24px → 30px → 36px → 48px
- Headings: `font-bold` (700) / `font-semibold` (600)
- Body: `font-normal` (400)
- Mono: `font-mono` for references, IDs, code

### 1.3 Spacing & Layout

- Base unit: 4px
- Card padding: 24px (`p-6`)
- Section gaps: 24px (`gap-6`)
- Element gaps: 16px (`gap-4`)
- Border radius: 8px (cards), 12px (large containers), 9999px (badges, avatars)

### 1.4 Visual Direction

- Dark, cinematic, intelligent, operational
- Deep navy/dark surfaces with restrained luminous accents
- Strong typography, generous negative space
- Technical/network-oriented visual language
- **Avoid**: generic chatbot aesthetics, stock photography, cartoon AI imagery, generic SaaS templates

---

## 2. Component Library

### 2.1 Inspection First

Before creating any component, inspect:
- `frontend/src/components/ui/` — currently contains only PNG reference images
- Existing page files for inline patterns that should be extracted
- `frontend/src/app/` route structure and layout patterns

### 2.2 New Components (Minimal Set)

Only create components that are genuinely reusable (used in 2+ places or establish a critical pattern):

| Component | Classification | Purpose |
|---|---|---|
| `Button` | REAL | Primary (accent), secondary (outline), ghost variants. Proper focus states, disabled states, loading states. |
| `Card` | REAL | Surface container with border, padding, optional header/footer. Dark theme variant. |
| `Badge` | REAL | Status pills colored by state. Maps to enquiry status colors. |
| `Input` | REAL | Form field with dark/light variants. Label, error message, helper text support. |
| `Avatar` | REAL | Circular user image with fallback to initials. |
| `Sidebar` | REAL | Dark navigation sidebar. Logo, nav items with active state, optional bottom section. |
| `EmptyState` | REAL | Empty content area with icon, message, optional action. |
| `LoadingSkeleton` | REAL | Skeleton loader for async content. Matches card/layout structure. |

### 2.3 Component Rules

- One component per file
- TypeScript strict mode, no `any`
- Props typed with interfaces
- Support `className` override for composition
- Accessible: proper ARIA, keyboard navigation, focus management
- Respect `prefers-reduced-motion` for any animated components

---

## 3. Landing Page (`/`)

**Classification**: STATIC (marketing sections) + REAL (enquiry interaction)

### 3.1 Static Marketing Sections

All content is fixed, no backend calls:

1. **Hero**: Headline "Tell us what you need. FIELDed finds where it can be done." + subtext + enquiry input field + CTA
2. **What is FIELDed?**: Icon grid explaining core capabilities
3. **How it Works**: Step-by-step process visualization
4. **One Platform, Two Sides**: Split cards — "For Customers" / "For Businesses"
5. **Powered by AI and the Business Brain**: Feature explanation
6. **Built for Trust**: Security/compliance information
7. **Start with an enquiry**: Final CTA
8. **Footer**: Navigation links, copyright "© 2026 FIELDed Platform"

### 3.2 Real Enquiry Interaction (Hero Field)

**Important**: The discovery API (`discovery.search()`) works for **both authenticated and anonymous users** (backend uses `get_optional_user()`). Auth is only required when creating an enquiry (which requires `require_customer` dependency).

**Full flow**:
1. Visitor enters a natural-language service request in the hero input
2. On submit, preserve the query in `sessionStorage`
3. **If authenticated** → Navigate to `/search` with the query auto-populated. The discovery API processes it and returns matched businesses/offers.
4. **If unauthenticated** → Navigate to `/search` with the query auto-populated (discovery works anonymously). When the user selects a business/offer and attempts to create an enquiry, they are redirected to `/signup` or `/login` with the enquiry context preserved. After auth, they return to complete the enquiry.
5. The enquiry text **must never disappear** across navigation or auth redirect.

**Enquiry creation path** (separate from discovery):
- Discovery returns matched businesses with service offers
- User selects a service offer → navigates to business profile or enquiry form
- Enquiry creation requires: `service_offer_id` (from discovery result), `subject`, `message`
- Uses `enquiries.create(businessId, data)` — requires authenticated customer (`require_customer`)
- If user is not authenticated at this point, redirect to auth with context preservation

**Implementation**:
- Use existing `isAuthenticated()` from `@/lib/auth`
- Use existing `discovery.search()` from `@/lib/api-client` (works anonymously)
- Preserve query via `sessionStorage` (more reliable than URL params for long text)
- After auth redirect, check for preserved query and auto-populate the search or enquiry form

### 3.3 Network Animation

- Real CSS/Canvas animation showing connected nodes (customer intent → FIELDed → business capability → governed execution)
- Must be an actual implementation, not a static placeholder pretending to be interactive
- Respect `prefers-reduced-motion` — reduce or disable animation
- Performance-conscious: use `requestAnimationFrame`, limit particle count
- If an external asset (e.g., Spline) would be needed but isn't provided, establish the integration boundary honestly rather than inventing a connection

---

## 4. Authentication Pages (`/login`, `/signup`)

**Classification**: REAL

### 4.1 Layout

Split-screen:
- **Left panel** (light background `#F8FAFC`): FIELDed logo, headline "Turn your need into a service.", feature bullets (Intelligent Matching, Governed Execution), copyright
- **Right panel** (dark background `#0B1120`): Form card

### 4.2 Sign Up Form

- Role selector: "I'm a Customer" / "I'm a Business" (toggle, affects post-auth redirect)
- Fields: First Name, Last Name, Email Address, Password (min 8 chars)
- Terms of Service + Privacy Policy checkbox
- Submit: "Create Account"
- Link to Sign In

### 4.3 Sign In Form

- Fields: Email, Password
- Submit: "Sign In"
- Link to Sign Up

### 4.4 Real Integration

- Uses existing `auth.login()` and `auth.register()` from `@/lib/api-client`
- **Register flow**: `auth.register()` returns `UserResponse` (no tokens). The existing `register()` helper in `@/lib/auth.ts` handles this by calling `auth.login()` immediately after registration to obtain tokens, then `storeTokens()`. The signup page should use the existing `register()` helper from `@/lib/auth.ts`, not call `auth.register()` directly.
- Uses existing `storeTokens()` for token persistence
- On success:
  - If enquiry context preserved → redirect to `/search` with query
  - If role = Customer → redirect to `/customer/dashboard`
  - If role = Business → redirect to `/business/dashboard`
- Proper loading state (button disabled + spinner), error state (inline error message), validation state

---

## 5. Business Layout

**Classification**: STATIC (structure) + REAL (navigation targets)

### 5.1 Structure

- Fixed left sidebar (w-64, dark background)
- Logo: "FIELDed" + "Business Brain" subtitle
- Navigation items with icons:
  - Dashboard → `/business/dashboard`
  - Enquiries → `/business/enquiries` (with real count badge from API)
  - Services → `/business/services`
  - Business Brain → `/business/brain`
  - Settings → `/business/settings`
- Active item: teal left border + teal text color
- Main content: full height, dark background, scrollable

### 5.2 Navigation Rules

- Only show nav items for routes that have real backend support
- Enquiry count badge: use real `enquiries.listForBusiness()` count
- Do not create dead links that appear functional

---

## 6. Business Dashboard (`/business/dashboard`)

**Classification**: REAL (available data) + NOT YET AVAILABLE (unavailable metrics)

### 6.1 Real Data (from existing APIs)

| Data Point | API Source | Display |
|---|---|---|
| User name, email | `auth.me()` | Greeting: "Good evening, [Name]" |
| Business list | `businesses.list()` | Business context, count |
| Enquiry count by status | `enquiries.listForBusiness()` | Active enquiries count (derived client-side by filtering the returned list on `status` — no dedicated metrics endpoint exists) |

### 6.2 Honest Unavailable States

For every metric or section without a backend data source:

| Section | Backend Status | Display |
|---|---|---|
| Conversion Rate | No endpoint | "Not configured — requires Business Brain rules" |
| Business Brain Uptime | No endpoint | "Business Brain not yet configured" |
| Avg. Response Time | No endpoint | "No data available" |
| Service Performance chart | No endpoint | "Connect your Business Brain to see performance data" |
| AI-Human Handover list | No endpoint | "No handover rules configured yet" |
| Workflow Automation toggles | No endpoint | Show structure, all toggles off, "Not yet configured" |
| Quick Actions | Partial | Only show actions with real routes (e.g., "View Enquiries"). Hide/disable actions without backend support. |

### 6.3 Hard Rule

**The dashboard must never show invented numbers.** No hardcoded percentages, no fake uptime, no simulated activity records, no fabricated chart data. If a metric has no data source, it shows an honest empty/unavailable state or is omitted entirely.

---

## 7. Enquiries

**Classification**: REAL (Phase 05 APIs)

### 7.1 Enquiry List (`/business/enquiries`)

**Real API integration**:
- `enquiries.listForBusiness(businessId)` → real enquiry list
- Filter tabs map to real `status` values from the API response
- Each enquiry card shows: reference, subject, message preview, status badge, created date
- Click navigates to enquiry detail

**Data limitation**: `EnquiryData` from the API contains `customer_id` and `business_id` (UUIDs) but **no customer name or business name**. The enquiry list cannot display customer names without additional API calls. Show reference, subject, status, and date only — do not fabricate names.

**States**:
- Loading: skeleton loaders
- Empty: "No enquiries received yet. Customer enquiries will appear here when submitted."
- Error: inline error message with retry option

### 7.2 Enquiry Detail (`/business/[businessId]/enquiries/[id]`)

**Real API integration**:
- `enquiries.getBusinessEnquiry(businessId, enquiryId)` → enquiry data
- `enquiries.getBusinessConversation(businessId, enquiryId)` → conversation with messages
- `enquiries.sendBusinessMessage(businessId, enquiryId, content)` → send reply
- `enquiries.transitionBusiness(businessId, enquiryId, targetStatus)` → state transitions

**Layout**: Two-panel — conversation detail + enquiry header (desktop), stacked (mobile):
- Enquiry header: subject, status badge, reference, transition buttons
- Conversation thread: message bubbles, timestamps, sender identification, message input

**Data limitation**: `EnquiryData` contains `customer_id` and `business_id` (UUIDs) but **no resolved names**. The detail view shows enquiry data and conversation messages only. Do not fabricate customer names, business names, or profile data.

**NOT YET AVAILABLE — Do Not Fabricate**:
- Lead scores, tiers, sentiment analysis → Not shown
- AI Context & Rules panel → Not rendered (no backend data)
- Audit Trail beyond message timestamps → Not fabricated
- Business Brain decision banners → Only shown if message metadata includes AI decision data from backend
- Customer profile enrichment beyond what the API returns → Not fabricated

### 7.3 Conversation UI Rules

- Messages show: sender type (business/customer), content, timestamp
- Business messages visually distinct from customer messages
- Message input: textarea with Enter-to-send, Shift+Enter for newline
- State transition buttons: only show valid transitions from current status (use existing `TRANSITION_OPTIONS` pattern)
- Auto-scroll to latest message on new message received
- Loading state for message send (button disabled + "Sending...")

---

## 8. Business Brain (`/business/brain`)

**Classification**: NOT YET AVAILABLE (UI boundary only)

### 8.1 What Exists

- Conceptual domain in FIELDed architecture docs (BusinessBrain, BrainVersion, BusinessRule, PricingRule, PolicyRule described in `docs/business-brain.md`)
- **No backend implementation**: no domain package, no models, no schemas, no repository, no service, no API endpoints
- Classification confirmed: **NOT YET AVAILABLE**

### 8.2 What the UI Shows

- Structural layout: Core Entities sidebar (Enquiry, Offer, Customer), workflow canvas area
- Real FIELDed domain terminology throughout
- Node types: Trigger, Analyzer, Action Block, Handover (from domain model)
- "Publish Changes" button → Shows: "Business Brain configuration is not yet available. This feature is under development." **Does NOT fake a success state.**
- All controls that would require backend persistence show "Not Yet Available" or "Not Configured" states

### 8.3 What the UI Does NOT Do

- No fabricated rules or rule data
- No fake AI decisions, rule evaluations, confidence scores, approvals, or operational states
- No frontend-only persistence pretending changes were saved
- No simulated validation, approval, or workflow execution flows
- No implication that the displayed workflow is currently governing real enquiries or business operations
- No "Save", "Publish", "Activate", or similar control shows a success state unless a real backend endpoint performs that operation

### 8.4 Architectural Authority (Preserved)

The FIELDed execution pattern remains authoritative regardless of Business Brain UI presence:

```
AI interprets/proposes → Business Brain rules/policies provide governed configuration → deterministic backend logic decides → authorized execution occurs → audit/provenance is recorded
```

Until the Business Brain backend exists, the frontend **must not claim that any of those Business Brain operations are actually occurring**. The UI is a structural placeholder for a future integration point, not a representation of active governance.

### 8.5 Future Integration Design

The UI is designed so that it can later connect to the real Business Brain API without requiring a fabricated interim architecture. No frontend-only state machines, rule engines, or decision logic are introduced as placeholders.

---

## 9. Responsive & Accessibility

### 9.1 Responsive Breakpoints

| Breakpoint | Layout Adaptation |
|---|---|
| Desktop (≥1024px) | Full multi-panel layouts, sidebar visible |
| Tablet (768–1023px) | Collapsed sidebar, stacked panels where needed |
| Mobile (<768px) | Single column, hamburger nav, full-width cards |

### 9.2 Accessibility Requirements

- Semantic HTML structure (proper heading hierarchy, landmarks)
- Keyboard navigation: all interactive elements reachable via Tab
- Focus states: visible focus rings on all interactive elements
- Color contrast: WCAG AA minimum (4.5:1 for text, 3:1 for large text)
- Form error states: associated with inputs via `aria-describedby`
- Loading states: `aria-busy`, `aria-live` regions for dynamic content
- Empty states: descriptive text, not just icons
- `prefers-reduced-motion`: reduce or disable all animations

---

## 10. Implementation Order

| Phase | Work | Classification |
|---|---|---|
| 1 | Inspect existing architecture, components, conventions | — |
| 2 | Establish visual tokens in `globals.css` | STATIC |
| 3 | Create minimal reusable UI components | REAL (infrastructure) |
| 4 | Implement public layout (dark theme base) | STATIC |
| 5 | Implement landing page (marketing + enquiry interaction) | STATIC + REAL |
| 6 | Implement auth pages with enquiry context preservation | REAL |
| 7 | Implement business layout (sidebar navigation) | STATIC + REAL |
| 8 | Implement dashboard with real data only | REAL + NOT YET AVAILABLE |
| 9 | Implement enquiries list + detail against real APIs | REAL |
| 10 | Establish Business Brain UI boundary | NOT YET AVAILABLE |
| 11 | Responsive / accessibility / performance pass | — |
| 12 | Final functional and visual review | — |

---

## 11. FIELDed Concept Clarity

The UI must reinforce the FIELDed concept throughout:

**Customer journey**: Find → Understand → Enquire → Decide → Book → Track → Complete → Review

**Business journey**: Configure → Receive → Qualify → Respond → Quote → Schedule → Execute → Complete

**AI role**: Interprets, proposes, assists. Never authoritative.

**Business Brain role**: Provides governed operational rules. Deterministic application logic remains authoritative.

---

## 12. Files to Modify/Create

### Modify
- `frontend/src/app/globals.css` — Add dark theme CSS custom properties
- `frontend/src/app/layout.tsx` — Update root layout for dark theme
- `frontend/src/app/page.tsx` — Complete landing page redesign
- `frontend/src/app/(public)/layout.tsx` — Update for dark theme
- `frontend/src/app/(public)/login/page.tsx` — Split-screen redesign
- `frontend/src/app/(public)/signup/page.tsx` — Split-screen redesign
- `frontend/src/app/(public)/search/page.tsx` — Dark theme + enquiry context preservation from landing page
- `frontend/src/app/(business)/layout.tsx` — Dark sidebar redesign
- `frontend/src/app/(business)/business/dashboard/page.tsx` — Real data dashboard
- `frontend/src/app/(business)/business/enquiries/page.tsx` — Enhanced list view
- `frontend/src/app/(business)/business/[businessId]/enquiries/[id]/page.tsx` — Enhanced detail view
- `frontend/src/app/(business)/business/brain/page.tsx` — UI boundary skeleton
- `frontend/src/app/(business)/business/services/page.tsx` — Dark theme
- `frontend/src/app/(business)/business/profile/page.tsx` — Dark theme
- `frontend/src/app/(business)/business/settings/page.tsx` — Dark theme
- `frontend/src/app/(customer)/layout.tsx` — Dark sidebar redesign
- `frontend/src/app/(customer)/customer/dashboard/page.tsx` — Dark theme
- `frontend/src/app/(customer)/customer/enquiries/page.tsx` — Dark theme
- `frontend/src/app/(customer)/customer/enquiries/[id]/page.tsx` — Dark theme
- `frontend/src/app/(customer)/customer/profile/page.tsx` — Dark theme
- `frontend/src/app/(customer)/customer/bookings/page.tsx` — Dark theme
- `frontend/src/app/(customer)/customer/settings/page.tsx` — Dark theme

### Create
- `frontend/src/components/ui/button.tsx`
- `frontend/src/components/ui/card.tsx`
- `frontend/src/components/ui/badge.tsx`
- `frontend/src/components/ui/input.tsx`
- `frontend/src/components/ui/avatar.tsx`
- `frontend/src/components/ui/empty-state.tsx`
- `frontend/src/components/ui/loading-skeleton.tsx`

### No Changes Required
- `frontend/src/lib/api-client.ts` — Already comprehensive
- `frontend/src/lib/auth.ts` — Already functional
- Backend files — No backend changes in this scope
