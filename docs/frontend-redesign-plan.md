# FIELDed Frontend Redesign — Implementation Plan

**Date**: 2026-09-19
**Spec**: [`docs/frontend-redesign-spec.md`](./frontend-redesign-spec.md)
**Status**: Awaiting approval before implementation

---

## Invariants

### No External Changes

| Layer | Change Required | Reason |
|---|---|---|
| Backend files | **None** | All Phase 01–05 endpoints exist and are functional |
| `frontend/src/lib/api-client.ts` | **None** | Already comprehensive — covers all Phase 05 endpoints |
| `frontend/src/lib/auth.ts` | **None** | Already has `login()`, `register()`, `logout()`, `isAuthenticated()`, `getCurrentUser()` |
| `frontend/tailwind.config.ts` | **None** | Dark theme implemented via CSS custom properties, not Tailwind config |

**Blocker protocol**: If during implementation a genuine blocker is discovered in `api-client.ts` or `auth.ts` (e.g., a missing method, incorrect type, or broken flow), **stop and report it**. Do not silently modify scope. Do not fabricate a workaround.

### No Fabrication

- No mock data, fabricated metrics, fake operational states, placeholder success states, or simulated backend behavior anywhere in the frontend.
- No invented numbers on the dashboard. No hardcoded percentages, uptime, response times, or activity records.
- No fake AI decisions, confidence scores, rule evaluations, approvals, or audit trails.

### Business Brain: NOT YET AVAILABLE

The Business Brain has **no backend implementation** — no domain package, no models, no schemas, no repository, no service, no API endpoints. The frontend page is a **structural UI boundary only**.

The UI must not:
- Create frontend-only Business Brain rules or persistence
- Simulate workflow execution
- Fabricate AI decisions, rule evaluations, confidence scores, approvals, or operational states
- Show a successful "Save", "Publish", "Activate", or similar operation
- Imply the displayed workflow is governing real enquiries or business operations

Architectural authority preserved:
```
AI interprets/proposes → Business Brain rules/policies provide governed configuration → deterministic backend logic decides → authorized execution occurs → audit/provenance is recorded
```

### Real Enquiry Flow (Preserved Exactly)

1. Visitor enters NL service request on landing page
2. Query preserved in `sessionStorage`
3. Navigate to `/search` — discovery works anonymously (`get_optional_user()`)
4. User selects a business/service offer from real discovery results
5. Enquiry creation requires authentication (`require_customer` dependency)
6. If unauthenticated → redirect to `/login` or `/signup` with enquiry context preserved
7. After auth → return to complete enquiry creation with context intact

### FIELDed Branding

All UI text, labels, and navigation use "FIELDed" exclusively. No unrelated product or brand names.

---

## File Justification

Every modified file is classified into one of two categories:

### Category A: Primary Redesign Targets (12 files)

These files receive substantive redesign — new layout, new structure, new functionality, or new visual design. They are the core scope of this plan.

| # | File | Justification |
|---|---|---|
| 1 | `frontend/src/app/globals.css` | Foundation for entire redesign — defines all CSS custom properties (design tokens) that every other file depends on. Currently empty (2 lines). |
| 2 | `frontend/src/app/layout.tsx` | Root layout — must switch from light (`bg-white`) to dark theme. Every page inherits from this. |
| 3 | `frontend/src/app/page.tsx` | Landing page — primary redesign target. Currently a 29-line placeholder. Needs full marketing layout + real enquiry interaction. |
| 4 | `frontend/src/app/(public)/login/page.tsx` | Auth page — primary redesign target. Split-screen layout with real auth integration + enquiry context preservation. |
| 5 | `frontend/src/app/(public)/signup/page.tsx` | Auth page — primary redesign target. Split-screen layout with role selector + two-step register flow. |
| 6 | `frontend/src/app/(business)/layout.tsx` | Business sidebar — primary redesign target. Dark sidebar with nav items, active states, real enquiry count badge. |
| 7 | `frontend/src/app/(business)/business/dashboard/page.tsx` | Business dashboard — primary redesign target. Real data (user, businesses, enquiries) + honest NOT YET AVAILABLE states for Business Brain metrics. |
| 8 | `frontend/src/app/(business)/business/enquiries/page.tsx` | Enquiries list — primary redesign target. Enhanced list with filter tabs, loading/empty/error states, real API integration. |
| 9 | `frontend/src/app/(business)/business/[businessId]/enquiries/[id]/page.tsx` | Enquiry detail — primary redesign target. Two-panel conversation view with real messaging and state transitions. |
| 10 | `frontend/src/app/(business)/business/brain/page.tsx` | Business Brain — primary redesign target. NOT YET AVAILABLE UI boundary. Structural layout only, no fake functionality. |
| 11 | `frontend/src/app/(public)/layout.tsx` | Public header — dark theme treatment. Part of the root visual experience. |
| 12 | `frontend/src/app/(public)/search/page.tsx` | Search page — dark theme + enquiry context preservation from landing page. Functional addition (sessionStorage read). |

### Category B: Compatibility / Theme-Only Changes (10 files)

These files already function correctly. They are modified **only** to replace light-theme Tailwind classes (`text-gray-*`, `bg-gray-*`, `border-gray-*`) with CSS custom properties so they remain visually consistent after the root layout switches to dark theme. **No structural, functional, or behavioral changes.**

**Why each must be modified**: The root layout (`layout.tsx`) changes from `bg-white text-gray-900` to dark theme. Without updating these files, their hardcoded light-theme classes will produce broken contrast (e.g., dark text on dark background) or visual inconsistency.

| # | File | Justification (why theme update is needed) |
|---|---|---|
| 13 | `frontend/src/app/(business)/business/services/page.tsx` | 348-line functional page with `text-gray-*`, `bg-gray-*`, `border-gray-*` classes. Will have broken contrast on dark background. |
| 14 | `frontend/src/app/(business)/business/profile/page.tsx` | 272-line functional page with light-theme classes. Same contrast issue. |
| 15 | `frontend/src/app/(business)/business/settings/page.tsx` | 9-line placeholder with `text-gray-900`, `text-gray-600`. Minimal change. |
| 16 | `frontend/src/app/(customer)/layout.tsx` | Customer sidebar — identical structure to business sidebar. Must match dark theme. |
| 17 | `frontend/src/app/(customer)/customer/dashboard/page.tsx` | 93-line page with light-theme classes. Contrast fix only. |
| 18 | `frontend/src/app/(customer)/customer/enquiries/page.tsx` | 128-line page with light-theme classes. Contrast fix only. |
| 19 | `frontend/src/app/(customer)/customer/enquiries/[id]/page.tsx` | 243-line page with light-theme classes. Contrast fix only. |
| 20 | `frontend/src/app/(customer)/customer/profile/page.tsx` | 181-line page with light-theme classes. Contrast fix only. |
| 21 | `frontend/src/app/(customer)/customer/bookings/page.tsx` | 9-line placeholder with `text-gray-900`, `text-gray-600`. Minimal change. |
| 22 | `frontend/src/app/(customer)/customer/settings/page.tsx` | 9-line placeholder with `text-gray-900`, `text-gray-600`. Minimal change. |

**Scope boundary**: Category B files receive color class replacements only. No new functionality, no new layout, no new API calls, no behavioral changes. If a Category B file works today, it must continue working identically — just with correct dark-theme colors.

---

## Files to Create (7) — FOUNDATION / PRESENTATIONAL

These are reusable presentational components. They contain **no business logic, no API calls, no data fetching**. They are classified as **FOUNDATION / PRESENTATIONAL** — infrastructure that primary redesign targets compose from.

All go in `frontend/src/components/ui/`. Currently this directory contains only PNG reference images — no existing components to conflict with.

### `button.tsx` — CREATE

```typescript
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  children: React.ReactNode;
}
```

- Variants: primary (`--accent`), secondary (outline), ghost (transparent), danger (`--danger`)
- States: loading (spinner + disabled), disabled (opacity), focus ring
- **Classification**: FOUNDATION / PRESENTATIONAL

### `card.tsx` — CREATE

```typescript
interface CardProps {
  children: React.ReactNode;
  className?: string;
  padding?: "sm" | "md" | "lg";
  hover?: boolean;
}
```

- `--bg-surface` background, `--border-subtle` border, 8px radius
- **Classification**: FOUNDATION / PRESENTATIONAL

### `badge.tsx` — CREATE

```typescript
interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "success" | "warning" | "danger" | "info" | "muted";
  className?: string;
}
```

- Status color mapping for enquiry statuses (SUBMITTED→info, IN_REVIEW→warning, CANCELLED→danger, etc.)
- **Classification**: FOUNDATION / PRESENTATIONAL

### `input.tsx` — CREATE

```typescript
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}
```

- `--bg-surface` background, `--border-default` border, focus ring with `--accent`
- **Classification**: FOUNDATION / PRESENTATIONAL

### `avatar.tsx` — CREATE

```typescript
interface AvatarProps {
  src?: string;
  name: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}
```

- Fallback: first letter of `name` on `--bg-elevated` background
- **Classification**: FOUNDATION / PRESENTATIONAL

### `empty-state.tsx` — CREATE

```typescript
interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}
```

- **Classification**: FOUNDATION / PRESENTATIONAL

### `loading-skeleton.tsx` — CREATE

```typescript
interface LoadingSkeletonProps {
  className?: string;
  lines?: number;
  variant?: "card" | "list" | "text";
}
```

- Animated pulse using `--bg-elevated` on `--bg-surface` base
- **Classification**: FOUNDATION / PRESENTATIONAL

---

## Implementation Order

| Phase | Work | Files | Classification |
|---|---|---|---|
| 1 | Design tokens + root layout | `globals.css`, `layout.tsx` | STATIC |
| 2 | Presentational component library | 7 new components in `components/ui/` | FOUNDATION / PRESENTATIONAL |
| 3 | Public layout + landing page | `(public)/layout.tsx`, `page.tsx` | STATIC + REAL |
| 4 | Auth pages | `login/page.tsx`, `signup/page.tsx` | REAL |
| 5 | Business layout + sidebar | `(business)/layout.tsx` | STATIC + REAL |
| 6 | Business dashboard | `dashboard/page.tsx` | REAL + NOT YET AVAILABLE |
| 7 | Enquiries list + detail | `enquiries/page.tsx`, `[id]/page.tsx` | REAL |
| 8 | Business Brain boundary | `brain/page.tsx` | NOT YET AVAILABLE |
| 9 | Dark theme: business pages | `services/`, `profile/`, `settings/` | COMPATIBILITY (theme-only) |
| 10 | Dark theme: customer layout + pages | `(customer)/layout.tsx` + 6 pages | COMPATIBILITY (theme-only) |
| 11 | Search page dark theme + context | `(public)/search/page.tsx` | REAL |
| 12 | Responsive + accessibility pass | All files | — |
| 13 | Verification | Build, type, lint, routes, runtime, API, context | — |

---

## Phase 1: Design Tokens + Root Layout

### `frontend/src/app/globals.css` — MODIFY

**Justification**: Foundation for entire redesign. Currently 2 lines. All other files depend on these tokens.

**Changes**:
- Add `:root` block with all CSS custom properties from spec §1.1
- Add base body styles using `--bg-primary` and `--text-primary`

**Classification**: STATIC

---

### `frontend/src/app/layout.tsx` — MODIFY

**Justification**: Root layout inherited by every page. Must switch from light to dark.

**Changes**:
- Replace `bg-white text-gray-900` → `bg-[var(--bg-primary)] text-[var(--text-primary)]`
- Keep metadata unchanged

**Classification**: STATIC

---

## Phase 2: Presentational Component Library

See "Files to Create (7)" section above. All 7 components created in this phase.

---

## Phase 3: Public Layout + Landing Page

### `frontend/src/app/(public)/layout.tsx` — MODIFY

**Justification**: Public header visible on all public pages. Dark theme treatment.

**Changes**:
- Header background: `--bg-surface`
- Text: `--text-primary` for logo, `--text-secondary` for nav links
- Button: `--accent` background
- Border: `--border-subtle`

**Classification**: STATIC

---

### `frontend/src/app/page.tsx` — MODIFY

**Justification**: Primary redesign target. Currently 29-line placeholder. Full landing page.

**New structure**:
1. **Hero** (STATIC + REAL): Headline + NL input + submit → preserves query in `sessionStorage` → navigates to `/search`
2. **Marketing sections** (STATIC): What is FIELDed, How it Works, Two Sides, AI + Business Brain, Trust, CTA
3. **Footer** (STATIC): Links, "© 2026 FIELDed Platform"

**Enquiry interaction (REAL)**:
- Uses `isAuthenticated()` from `@/lib/auth` — check auth state
- Query preserved via `sessionStorage` — survives navigation and auth redirect
- On submit → navigate to `/search` with query auto-populated
- Discovery works anonymously — auth only required when creating enquiry

**Classification**: STATIC (marketing) + REAL (enquiry interaction)

---

## Phase 4: Auth Pages

### `frontend/src/app/(public)/login/page.tsx` — MODIFY

**Justification**: Primary redesign target. Split-screen layout + enquiry context preservation.

**Changes**:
- Split-screen: left panel (`--auth-light-bg`) with branding, right panel (`--bg-primary`) with form
- Form: Email, Password
- Uses `login()` from `@/lib/auth.ts`

**Post-login redirect**:
1. Check `sessionStorage` for preserved enquiry context → `/search`
2. Otherwise → role-based redirect (`/customer/dashboard` or `/business/dashboard`)

**Classification**: REAL

---

### `frontend/src/app/(public)/signup/page.tsx` — MODIFY

**Justification**: Primary redesign target. Split-screen layout + role selector + two-step register.

**Changes**:
- Split-screen (same as login)
- Form: First Name, Last Name, Email, Password (min 8), Terms checkbox, Role selector
- Uses `register()` from `@/lib/auth.ts` — two-step: `auth.register()` → `auth.login()` → `storeTokens()`

**Classification**: REAL

---

## Phase 5: Business Layout

### `frontend/src/app/(business)/layout.tsx` — MODIFY

**Justification**: Primary redesign target. Dark sidebar with real enquiry count badge.

**Changes**:
- Sidebar: `--bg-surface`, logo "FIELDed" + "Business Brain" subtitle
- Nav items: Dashboard, Enquiries (count badge), Services, Business Brain, Settings
- Active state: `--accent` left border + text color
- Main content: `--bg-primary` background

**API methods used**:
- `businesses.list()` — REAL (get businessId for current user)
- `enquiries.listForBusiness(businessId)` — REAL (count badge)

**Classification**: STATIC (structure) + REAL (navigation, count badge)

---

## Phase 6: Business Dashboard

### `frontend/src/app/(business)/business/dashboard/page.tsx` — MODIFY

**Justification**: Primary redesign target. Real data + honest NOT YET AVAILABLE states.

**REAL data**:
| Data | API | Display |
|---|---|---|
| User name | `auth.me()` | Greeting |
| Business list | `businesses.list()` | Business cards |
| Enquiry count | `enquiries.listForBusiness()` | Active enquiries (derived client-side) |

**NOT YET AVAILABLE**:
| Section | Display |
|---|---|
| Conversion Rate | "Not configured — requires Business Brain rules" |
| Business Brain Uptime | "Business Brain not yet configured" |
| Avg. Response Time | "No data available" |
| Service Performance | "Connect your Business Brain to see performance data" |
| AI-Human Handover | "No handover rules configured yet" |
| Workflow Automation | Structure shown, toggles disabled, "Not yet configured" |

**Hard rule**: No invented numbers. No hardcoded percentages. No fake uptime.

**Classification**: REAL + NOT YET AVAILABLE

---

## Phase 7: Enquiries List + Detail

### `frontend/src/app/(business)/business/enquiries/page.tsx` — MODIFY

**Justification**: Primary redesign target. Enhanced list with filter tabs, proper states.

**Changes**:
- Filter tabs: All, Submitted, In Review, Needs Information, Declined, Cancelled
- Cards: reference, subject, message preview, status badge, created date
- **Data limitation**: `EnquiryData` has `customer_id` (UUID) but **no customer name**. Show reference, subject, status, date only.

**States**: LoadingSkeleton, EmptyState, error with retry

**API methods used**:
- `enquiries.listForBusiness(businessId)` — REAL
- `businesses.list()` — REAL (get businessId)

**Classification**: REAL

---

### `frontend/src/app/(business)/business/[businessId]/enquiries/[id]/page.tsx` — MODIFY

**Justification**: Primary redesign target. Two-panel conversation + state transitions.

**Changes**:
- Two-panel: conversation thread (left) + enquiry header with transitions (right)
- Messages: sender type visually distinct, timestamps, auto-scroll
- Transitions: only valid transitions from current status (business: received, in_review, needs_information, declined, expired)

**NOT YET AVAILABLE — Do Not Fabricate**:
- Lead scores, tiers, sentiment → Not shown
- AI Context & Rules panel → Not rendered
- Audit trail beyond timestamps → Not fabricated
- Business Brain decision banners → Not shown

**API methods used**:
- `enquiries.getBusinessEnquiry()` — REAL
- `enquiries.getBusinessConversation()` — REAL
- `enquiries.sendBusinessMessage()` — REAL
- `enquiries.transitionBusiness()` — REAL

**Classification**: REAL

---

## Phase 8: Business Brain Boundary

### `frontend/src/app/(business)/business/brain/page.tsx` — MODIFY

**Justification**: Primary redesign target. NOT YET AVAILABLE UI boundary.

**Classification**: **NOT YET AVAILABLE**

**What the UI shows**:
- Structural layout: Core Entities sidebar (Enquiry, Offer, Customer), workflow canvas area
- Real FIELDed domain terminology
- Node type labels: Trigger, Analyzer, Action Block, Handover
- "Publish Changes" button → "Business Brain configuration is not yet available. This feature is under development." **Does NOT fake a success state.**
- All controls show "Not Yet Available" or "Not Configured"

**What the UI does NOT do**:
- No frontend-only rules or rule data
- No fake AI decisions, rule evaluations, confidence scores, approvals, or operational states
- No frontend-only persistence
- No simulated validation, approval, or workflow execution
- No implication the workflow is governing real enquiries
- No "Save"/"Publish"/"Activate" success state

**No API calls. No state changes. No persistence.**

---

## Phase 9: Dark Theme — Business Pages (Compatibility Only)

These pages already function correctly. **Color class replacement only. No structural, functional, or behavioral changes.**

### `frontend/src/app/(business)/business/services/page.tsx` — MODIFY

**Justification**: 348-line functional page with hardcoded light-theme classes. Will have broken contrast on dark background after root layout change.

**Changes**: Replace `text-gray-*`, `bg-gray-*`, `border-gray-*` with CSS custom properties.

---

### `frontend/src/app/(business)/business/profile/page.tsx` — MODIFY

**Justification**: 272-line functional page with light-theme classes. Same contrast issue.

**Changes**: Color class replacement only.

---

### `frontend/src/app/(business)/business/settings/page.tsx` — MODIFY

**Justification**: 9-line placeholder with `text-gray-900`, `text-gray-600`. Minimal change.

**Changes**: Replace 2 color classes.

---

## Phase 10: Dark Theme — Customer Layout + Pages (Compatibility Only)

Same rationale as Phase 9: contrast fix after root layout dark theme change. **No functional changes.**

### `frontend/src/app/(customer)/layout.tsx` — MODIFY

**Justification**: Customer sidebar — must match dark theme. Same structure as business sidebar.

**Changes**: Dark sidebar colors, nav items: Dashboard, Profile, Enquiries, Bookings, Settings.

---

### `frontend/src/app/(customer)/customer/dashboard/page.tsx` — MODIFY

**Justification**: 93-line page with light-theme classes. Contrast fix only.

---

### `frontend/src/app/(customer)/customer/enquiries/page.tsx` — MODIFY

**Justification**: 128-line page with light-theme classes. Contrast fix only.

---

### `frontend/src/app/(customer)/customer/enquiries/[id]/page.tsx` — MODIFY

**Justification**: 243-line page with light-theme classes. Contrast fix only.

---

### `frontend/src/app/(customer)/customer/profile/page.tsx` — MODIFY

**Justification**: 181-line page with light-theme classes. Contrast fix only.

---

### `frontend/src/app/(customer)/customer/bookings/page.tsx` — MODIFY

**Justification**: 9-line placeholder with `text-gray-900`, `text-gray-600`. Minimal change.

---

### `frontend/src/app/(customer)/customer/settings/page.tsx` — MODIFY

**Justification**: 9-line placeholder with `text-gray-900`, `text-gray-600`. Minimal change.

---

## Phase 11: Search Page Dark Theme + Context Preservation

### `frontend/src/app/(public)/search/page.tsx` — MODIFY

**Justification**: Dark theme + functional addition (read preserved query from landing page).

**Changes**:
- Dark theme color replacement
- On mount: check `sessionStorage.getItem("fielded_query")` → auto-populate search input
- Existing discovery API integration preserved

**API methods used**:
- `discovery.search()` — REAL
- `categories.listRoots()` — REAL

**Classification**: REAL

---

## Phase 12: Responsive + Accessibility Pass

**Files**: All modified files

**Checks**:
- [ ] Desktop (≥1024px): full multi-panel layouts, sidebar visible
- [ ] Tablet (768–1023px): collapsed sidebar, stacked panels
- [ ] Mobile (<768px): single column, hamburger nav, full-width cards
- [ ] Keyboard navigation: all interactive elements reachable via Tab
- [ ] Focus states: visible focus rings on all interactive elements
- [ ] Color contrast: WCAG AA (4.5:1 text, 3:1 large text)
- [ ] Form errors: `aria-describedby` association
- [ ] Loading states: `aria-busy`, `aria-live` regions
- [ ] Empty states: descriptive text, not just icons
- [ ] `prefers-reduced-motion`: reduce or disable all animations

---

## Phase 13: Verification

### 13.1 Build + Type + Lint

```bash
cd frontend && npx next build
```

- [ ] Build succeeds with zero errors
- [ ] All expected routes present in build output (19+ routes)
- [ ] No TypeScript errors (`tsc --noEmit` if available)
- [ ] No missing imports or unresolved modules

### 13.2 Route + Navigation Verification

- [ ] `/` — Landing page renders with marketing sections
- [ ] `/login` — Split-screen login form renders
- [ ] `/signup` — Split-screen signup form renders
- [ ] `/search` — Discovery page renders, reads preserved query from sessionStorage
- [ ] `/business/dashboard` — Shows real user data + honest NOT YET AVAILABLE states
- [ ] `/business/enquiries` — List renders with filter tabs
- [ ] `/business/[id]/enquiries/[id]` — Conversation view renders
- [ ] `/business/brain` — Shows "Not Yet Available" — no fake success states
- [ ] `/business/services` — Dark theme, existing functionality intact
- [ ] `/business/profile` — Dark theme, existing functionality intact
- [ ] `/business/settings` — Dark theme
- [ ] `/customer/dashboard` — Dark theme
- [ ] `/customer/enquiries` — Dark theme
- [ ] `/customer/enquiries/[id]` — Dark theme
- [ ] `/customer/profile` — Dark theme
- [ ] `/customer/bookings` — Dark theme
- [ ] `/customer/settings` — Dark theme

### 13.3 Runtime Error Review

- [ ] No console errors on any page load
- [ ] No hydration mismatches
- [ ] No missing CSS custom property references
- [ ] No broken contrast (dark text on dark background)

### 13.4 API Integration Verification

- [ ] Dashboard calls `auth.me()`, `businesses.list()`, `enquiries.listForBusiness()` — no other API calls
- [ ] Enquiries list calls `enquiries.listForBusiness()` — shows real data or honest empty state
- [ ] Enquiry detail calls `getBusinessEnquiry()` + `getBusinessConversation()` — shows real conversation
- [ ] Business sidebar badge calls `enquiries.listForBusiness()` — shows real count or 0
- [ ] Discovery search calls `discovery.search()` — works anonymously
- [ ] No page makes API calls to non-existent endpoints

### 13.5 Context Preservation Verification

- [ ] Landing page query → `sessionStorage` → `/search` auto-populates input
- [ ] Auth redirect preserves query in `sessionStorage`
- [ ] After login/signup → query restored and search auto-populated
- [ ] Query survives full page reload

### 13.6 No Fake Functionality Confirmation

- [ ] Dashboard: no hardcoded percentages, uptime, response times, or chart data
- [ ] Business Brain: no rules, no AI decisions, no confidence scores, no approvals, no audit trail, no operational states
- [ ] Enquiry detail: no lead scores, no sentiment, no AI context, no decision banners
- [ ] All "Not Yet Available" sections show honest empty states — not simulated data
- [ ] No `api-client.ts` modifications
- [ ] No `auth.ts` modifications
- [ ] No backend file modifications

---

## Summary

### Files to Create (7) — FOUNDATION / PRESENTATIONAL

| File | Purpose |
|---|---|
| `frontend/src/components/ui/button.tsx` | Reusable button with variants |
| `frontend/src/components/ui/card.tsx` | Surface container |
| `frontend/src/components/ui/badge.tsx` | Status pills |
| `frontend/src/components/ui/input.tsx` | Form field |
| `frontend/src/components/ui/avatar.tsx` | User image with fallback |
| `frontend/src/components/ui/empty-state.tsx` | Empty content area |
| `frontend/src/components/ui/loading-skeleton.tsx` | Skeleton loader |

### Files to Modify (22)

**Category A: Primary Redesign Targets (12)**

| # | File | Classification |
|---|---|---|
| 1 | `frontend/src/app/globals.css` | STATIC |
| 2 | `frontend/src/app/layout.tsx` | STATIC |
| 3 | `frontend/src/app/page.tsx` | STATIC + REAL |
| 4 | `frontend/src/app/(public)/layout.tsx` | STATIC |
| 5 | `frontend/src/app/(public)/login/page.tsx` | REAL |
| 6 | `frontend/src/app/(public)/signup/page.tsx` | REAL |
| 7 | `frontend/src/app/(public)/search/page.tsx` | REAL |
| 8 | `frontend/src/app/(business)/layout.tsx` | STATIC + REAL |
| 9 | `frontend/src/app/(business)/business/dashboard/page.tsx` | REAL + NOT YET AVAILABLE |
| 10 | `frontend/src/app/(business)/business/enquiries/page.tsx` | REAL |
| 11 | `frontend/src/app/(business)/business/[businessId]/enquiries/[id]/page.tsx` | REAL |
| 12 | `frontend/src/app/(business)/business/brain/page.tsx` | NOT YET AVAILABLE |

**Category B: Compatibility / Theme-Only (10)**

| # | File | Justification |
|---|---|---|
| 13 | `frontend/src/app/(business)/business/services/page.tsx` | Contrast fix (348 lines) |
| 14 | `frontend/src/app/(business)/business/profile/page.tsx` | Contrast fix (272 lines) |
| 15 | `frontend/src/app/(business)/business/settings/page.tsx` | Contrast fix (9 lines) |
| 16 | `frontend/src/app/(customer)/layout.tsx` | Contrast fix (22 lines) |
| 17 | `frontend/src/app/(customer)/customer/dashboard/page.tsx` | Contrast fix (93 lines) |
| 18 | `frontend/src/app/(customer)/customer/enquiries/page.tsx` | Contrast fix (128 lines) |
| 19 | `frontend/src/app/(customer)/customer/enquiries/[id]/page.tsx` | Contrast fix (243 lines) |
| 20 | `frontend/src/app/(customer)/customer/profile/page.tsx` | Contrast fix (181 lines) |
| 21 | `frontend/src/app/(customer)/customer/bookings/page.tsx` | Contrast fix (9 lines) |
| 22 | `frontend/src/app/(customer)/customer/settings/page.tsx` | Contrast fix (9 lines) |

### Files NOT Modified

| File | Reason |
|---|---|
| `frontend/src/lib/api-client.ts` | Already comprehensive |
| `frontend/src/lib/auth.ts` | Already functional |
| `frontend/tailwind.config.ts` | Dark theme via CSS custom properties |
| All backend files | No backend changes in this scope |

---

## API Methods Reference

| API Method | Used In | Classification |
|---|---|---|
| `auth.me()` | Dashboard | REAL |
| `login()` | Login page | REAL |
| `register()` | Signup page | REAL |
| `isAuthenticated()` | Landing page, auth pages | REAL |
| `businesses.list()` | Dashboard, layouts, enquiries | REAL |
| `enquiries.listForBusiness()` | Dashboard, enquiries list, sidebar badge | REAL |
| `enquiries.getBusinessEnquiry()` | Enquiry detail | REAL |
| `enquiries.getBusinessConversation()` | Enquiry detail | REAL |
| `enquiries.sendBusinessMessage()` | Enquiry detail | REAL |
| `enquiries.transitionBusiness()` | Enquiry detail | REAL |
| `discovery.search()` | Landing page, search page | REAL |
| `categories.listRoots()` | Search page | REAL |
