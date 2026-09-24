# FIELDed — Product-Wide UX / E2E Audit

**Date**: 2026-09-23
**Scope**: Live product audit at product/UX/information-architecture level
**Method**: Browser-based audit of all public, customer, and business pages against the production backend
**Constraint**: No code changes. No mockups. No backend audit. No Business Brain re-audit.

---

## 1. CURRENT PRODUCT EXPERIENCE

### What the product currently feels like

FIELDed feels like a **backend-first SaaS dashboard** that has been incrementally wrapped in a dark-theme frontend. The product is structurally organized around its database entities (Enquiries, Quotes, Bookings, Payments, Services, Operations) rather than around the workflows of the people who use it.

The public-facing side (landing, search, network) is the most coherent part of the product. It presents a clear value proposition and a functional discovery experience. But the moment a user signs up — as either customer or business — the experience fragments into a collection of CRUD screens connected by a sidebar.

The product does not yet feel like a **service network**. It feels like a **database browser with a green accent color**.

### What is structurally wrong

1. **The navigation mirrors the database schema, not the user's workflow.** The sidebar items (Dashboard, Enquiries, Quotes, Bookings, Operations, Services, Business Brain, Communications, Payments, Settings) are a direct map of the backend domain modules. A business owner does not think "I need to check my Operations module." They think "I need to see what jobs are happening today."

2. **There is no onboarding or first-run experience.** A new business user signs up and immediately sees a dashboard full of zeros, error banners ("No business found. Create one first."), and blank pages. There is no guidance, no setup wizard, no progressive disclosure. The product assumes the user already has a configured business.

3. **The customer and business experiences are completely siloed.** They share no design language beyond the dark theme. The customer side has 7 nav items; the business side has 10. There is no unified identity — just a "Switch to Customer/Business" link buried at the bottom of the sidebar.

4. **Critical workflows are invisible.** There is no visible path to: create an enquiry (customer), send a quote (business), accept a quote and book (customer), mark a booking complete (business), leave a review (customer), or record a payment (business). These workflows exist in the backend API but have no frontend entry points.

5. **The product is stuck between two mental models.** It wants to be a conversational, AI-assisted service network (the landing page promises "Describe what you need in plain language"). But the authenticated experience is a traditional table-and-form SaaS dashboard. The promise and the reality do not match.

---

## 2. CUSTOMER EXPERIENCE AUDIT

### The intended journey

Search → Discover business → Understand offer → Enquire → Communicate → Receive quote → Accept → Book → Pay → Complete service → Review

### What actually exists

| Step | Status | Observation |
|------|--------|-------------|
| Search | **Working** | Natural language search with category browsing. Clean UI. |
| Discover business | **Working** | Search results show business cards with service offers, match reasons, pricing labels. |
| Understand offer | **Partial** | Business profile page exists but service offer detail page is untested. |
| Enquire | **Missing** | No "Send Enquiry" button on business profile or search results. No enquiry creation UI. |
| Communicate | **Missing** | No messaging/conversation UI visible anywhere on the customer side. |
| Receive quote | **Broken** | Quotes page shows "Request validation failed" error. |
| Accept quote | **Missing** | No quote acceptance UI. |
| Book | **Broken** | Bookings page shows "Request validation failed" error. No booking creation flow. |
| Pay | **Broken** | Payments page shows loading skeletons indefinitely. |
| Complete service | **Missing** | No service completion UI. |
| Review | **Missing** | No review creation UI. |

### Major friction points

1. **The journey stops at discovery.** A customer can search and find businesses, but there is no action to take after finding one. The search result cards show "View full profile →" but the business profile page has no "Send Enquiry" or "Contact" button. The customer hits a dead end.

2. **The dashboard is a status board, not a workspace.** It shows four stat cards (all zero) and a "Recent Activity" section (empty). The "Quick Actions" section has three buttons but "Find a Service" just goes back to search. There is no sense of "here's what you should do next."

3. **Three of seven pages show API errors.** Quotes, Bookings, and Services all display "Request validation failed" banners. This is not an empty state — it's a broken API call. The user sees red error messages on pages they've never used.

4. **The Transactions page is orphaned.** It exists at `/customer/transactions` but has no link in the sidebar. A user can only reach it by typing the URL or clicking "Transaction History" from the dashboard. This suggests the information architecture was not planned holistically.

5. **No conversation layer.** The product's core differentiator is "dedicated conversations per enquiry." But there is no messaging UI. The customer cannot communicate with a business through the platform.

6. **Profile page shows loading skeleton, not a form.** The customer profile page renders as a loading skeleton that never resolves to an editable form. This is a rendering bug, not a design choice.

---

## 3. BUSINESS EXPERIENCE AUDIT

### The intended journey

New enquiry arrives → Understand customer need → Communicate → Quote → Schedule → Perform work → Complete → Review

### What actually exists

| Step | Status | Observation |
|------|--------|-------------|
| Business setup | **Missing** | No onboarding flow. User signs up and sees "No businesses registered yet." |
| Receive enquiry | **Working (empty)** | Enquiries page exists with filter tabs. Shows empty state correctly. |
| Understand customer need | **Partial** | Enquiry detail page exists with conversation thread and state transitions. |
| Communicate | **Partial** | Messaging UI exists in enquiry detail but is untested with real data. |
| Quote | **Working (empty)** | Quotes page exists with filter tabs. No quote creation UI visible from enquiries. |
| Schedule | **Missing** | No scheduling UI. Bookings page exists but no creation flow. |
| Perform work | **Partial** | Operations page exists with sub-tabs (Operations, Invoices, Ledger). |
| Complete | **Missing** | No service completion UI. |
| Review | **Missing** | No review management UI. |

### Major friction points

1. **The "No business found" error appears on 6 of 11 pages.** Bookings, Services, Communications, Profile, Settings, and the Brain page all show this error or render blank. The product does not guide the user to create a business first. There is no setup wizard, no "Get Started" prompt, no progressive onboarding.

2. **The dashboard contradicts itself.** It says "No businesses registered yet" but still renders the full dashboard layout with six stat cards, Quick Actions, and Recent Activity. This is confusing — the dashboard should either show an onboarding state or the user should not reach the dashboard without a business.

3. **The Business Brain page is blank.** When there's no business, the Brain page shows loading skeletons that never resolve. The Brain is the product's key differentiator but it's completely inaccessible to a new user.

4. **The Services page is stuck on infinite loading.** It never resolves from the loading state. This is a bug, but it also reveals a deeper problem: the page depends on a business existing, and there's no graceful handling of that case.

5. **The Settings page is blank.** It renders the heading and tabs but no content. The Settings page has 533 lines of code with 5 tabs (Identity, Members, Communications, Payments, Security) but none of it renders. This is a critical rendering bug.

6. **10 sidebar items is too many.** Dashboard, Enquiries, Quotes, Bookings, Operations, Services, Business Brain, Communications, Payments, Settings. This is a classic SaaS navigation bloat problem. No business owner needs 10 top-level destinations.

7. **Operations is a vague catch-all.** It contains service executions, invoices, and ledger. The name "Operations" doesn't communicate what's inside. A business owner looking for their invoices would not naturally navigate to "Operations."

8. **No notification or alert system.** There is no way for a business to see new enquiries, pending quotes, or upcoming bookings without manually navigating to each page. The enquiry badge counter in the sidebar is the only proactive notification.

---

## 4. CURRENT NAVIGATION / INFORMATION ARCHITECTURE

### What exists today

**Public:**
- Landing page (/)
- Search (/search)
- Network (/network)
- Login (/login)
- Signup (/signup)
- Business profile (/business/[slug])
- Service offer detail (/business/[slug]/services/[offerSlug])
- Member invitation accept (/members/accept-invitation)

**Customer (7 nav items):**
- Dashboard
- Profile
- Enquiries
- Quotes
- Bookings
- Payments
- Services
- Transactions (orphaned — not in nav)

**Business (10 nav items):**
- Dashboard
- Enquiries (with badge counter)
- Quotes
- Bookings
- Operations
- Services
- Business Brain
- Communications
- Payments
- Settings

### What appears unnecessary, duplicated, buried, or misplaced

| Item | Problem | Recommendation |
|------|---------|----------------|
| **Operations** (business) | Vague name. Contains executions, invoices, ledger. Not a natural destination. | Rename or restructure. "Invoices" and "Ledger" are financial concepts — they belong together. "Service Executions" is an operational concept. These are different concerns. |
| **Transactions** (customer) | Orphaned page. Not in sidebar. Duplicates the purpose of Payments + Services. | Either integrate into Payments/Services or remove. |
| **Services** (customer) | Confusing name. Shows completed services and invoices. Customers don't think of these as "my services." | Rename to "History" or "Completed Work." |
| **Services** (business) | Different meaning than customer "Services." Shows service offers. | Rename to "Service Offers" or "Catalog." |
| **Business Brain** | Separate page. Not integrated into operational workflow. Feels like a separate product. | Keep as a configuration area but surface Brain insights contextually in operational pages. |
| **Communications** (business) | Bare page. Just "No business found." No clear purpose. | Integrate into Settings or make it a channel configuration page with clear purpose. |
| **Settings** (business) | 5 tabs (Identity, Members, Communications, Payments, Security). Essentially a second dashboard. | This is too much for a Settings page. Members and Security are administrative. Communications is operational. Payments is financial. These belong in different places. |
| **Profile** (customer) | Simple form. Doesn't justify a top-level nav item. | Move into a user menu or account settings. |
| **Payments** (both sides) | Customer payments page shows loading skeletons. Business payments page has "Record Payment" button but no payment creation flow. | Clarify purpose. Is this for viewing payment history or recording payments? |

### Duplicated concepts

- **"Services"** means different things on customer vs business side.
- **"Payments"** exists on both sides but serves different purposes (customer = view history, business = record payments).
- **"Bookings"** exists on both sides but the creation flow is missing on both.
- **"Quotes"** exists on both sides but the creation/acceptance flow is missing.

---

## 5. GLOBAL SHELL ASSESSMENT

### Sidebar

**Current state:** Fixed left sidebar, 264px wide, dark background. Contains logo + role label at top, nav items in the middle, and "Switch to Customer/Business" + "Back to FIELDed" at the bottom.

**Problems:**
- 10 items for business is too many. The sidebar becomes a laundry list.
- No icons. Just text labels. This makes it harder to scan quickly.
- No visual grouping. All items are at the same level. There's no distinction between "operational" (Enquiries, Bookings) and "configuration" (Settings, Business Brain).
- The "Switch to Customer/Business" link is buried at the bottom. For users who operate both sides, this is a frequent action.
- No user avatar, name, or account menu. No way to sign out from the sidebar (sign out is only visible on the dashboard page as a button in the top-right).

**Assessment:** The sidebar should be **fundamentally rethought**, not polished. A 10-item sidebar is a symptom of organizing by database entity rather than by workflow. The new shell should have fewer top-level destinations, with secondary items accessible through contextual menus or a command palette.

### Header

**Current state:** No persistent header in the authenticated areas. The only header is on the public pages (logo + Search + Network + Sign In + Sign Up).

**Problems:**
- No search within the app.
- No notifications center.
- No user menu (avatar, name, sign out).
- No breadcrumbs.

**Assessment:** The authenticated areas need a minimal top bar with: user menu (avatar + name + sign out), notifications bell, and possibly a global search/command palette.

### Dashboard

**Current state:** Stat cards in a grid, Quick Actions buttons, Recent Activity section.

**Problems:**
- Stat cards show zeros for new users. This is demotivating.
- Quick Actions are generic buttons that navigate to other pages. They don't represent actual actions.
- Recent Activity is empty and doesn't show a timeline.

**Assessment:** The dashboard should be rethought as a **workspace** rather than a status board. For a business, the dashboard should show: today's schedule, pending actions (enquiries to respond to, quotes to send), recent conversations, and revenue at a glance. For a customer, it should show: active enquiries, upcoming bookings, and recommended actions.

### Mobile/Responsive

**Current state:** Mobile uses a horizontal scroll nav bar below a minimal header. The sidebar is hidden on mobile.

**Problems:**
- 10 items in a horizontal scroll is not usable on mobile.
- No bottom navigation or hamburger menu.
- The main content area has a 104px top margin to account for the mobile header, which wastes vertical space.

**Assessment:** Mobile needs a proper navigation solution — either a bottom tab bar for primary destinations or a hamburger menu with a slide-out nav.

---

## 6. KEY UX PROBLEMS

### Critical (blocks core workflows)

1. **No enquiry creation flow.** The customer cannot create an enquiry from anywhere in the UI. This is the primary customer action and it does not exist.

2. **No business onboarding.** A new business user sees error messages on most pages. There is no setup flow to create a business profile, add service offers, or configure the Business Brain.

3. **Broken API calls on multiple pages.** Quotes, Bookings, and Services (customer) all show "Request validation failed." This makes the product look broken to any new user.

4. **Blank pages.** Business Brain and Settings pages render blank. This is worse than an error message — it looks like the product is unfinished.

### High (degrades experience significantly)

5. **No messaging UI.** The product's core differentiator is "dedicated conversations per enquiry" but there is no visible messaging interface.

6. **No quote creation/acceptance flow.** Businesses cannot create quotes from the enquiry detail page (the UI exists in code but is not connected). Customers cannot accept quotes.

7. **No booking flow.** Neither side can create or manage bookings through the UI.

8. **10-item business sidebar.** Too many top-level destinations. No visual grouping. No hierarchy.

9. **Inconsistent empty states.** Some pages have CTAs, some don't. Some are centered, some are left-aligned. Some show error banners, some don't.

10. **"No business found" on 6 pages.** The product does not handle the "no business" state gracefully. It shows error messages instead of guiding the user.

### Medium (noticeable but not blocking)

11. **Orphaned Transactions page.** Exists but not in navigation.

12. **Confusing "Services" naming.** Different meanings on customer vs business side.

13. **No notifications system.** Users must manually check each page for updates.

14. **Loading skeletons that never resolve.** Profile page (customer), Services page (business), Brain page (business).

15. **No sign out in sidebar.** Sign out is only on the dashboard page.

16. **Mobile navigation is unusable.** 10 items in horizontal scroll.

### Low (cosmetic or minor)

17. **No icons in sidebar.** Text-only labels are harder to scan.

18. **No breadcrumbs.** Users can't see where they are in the hierarchy.

19. **Inconsistent terminology.** "Service Offers" vs "Services" vs "My Services."

20. **Landing page is long.** 7 sections before the CTA. Could be more concise.

---

## 7. WHAT THE NEW PRODUCT EXPERIENCE SHOULD BECOME

### The proposed mental model

FIELDed should feel like a **service operations workspace**, not a database browser. The product should be organized around **what the user is trying to accomplish right now**, not around the backend entities that store the data.

For a **business owner**, the product should feel like:
- "Here's what needs my attention right now" (enquiries to respond to, quotes to send, bookings to confirm)
- "Here's what's happening today" (scheduled work, active conversations)
- "Here's how my business is performing" (revenue, completion rate, reviews)
- "Here's how to configure my business" (services, pricing, policies, team)

For a **customer**, the product should feel like:
- "Here's what I'm working on" (active enquiries, upcoming bookings)
- "Here's what I've done" (completed services, payment history, reviews)
- "Here's how to find what I need" (search, browse categories)

### The proposed navigation philosophy

**Fewer top-level destinations. More contextual actions.**

Instead of 10 sidebar items, the business side should have 4-5 primary destinations:
1. **Home** — today's overview, pending actions, recent activity
2. **Enquiries** — the inbox of customer requests (this is where the business owner spends most of their time)
3. **Schedule** — bookings and service executions (the operational calendar)
4. **Finance** — quotes, invoices, payments, ledger
5. **Settings** — business profile, services, team, Brain configuration

Secondary destinations (Brain, Communications, Members) should be accessible through Settings or contextual menus, not as top-level nav items.

### The proposed workspace model

The product should move toward a **conversation-centric workspace** rather than a page-centric dashboard. The enquiry detail page already has a conversation thread — this should be the primary interface, not a secondary feature.

When a business owner clicks on an enquiry, they should see:
- The conversation thread (primary)
- Customer details (sidebar)
- State transitions (inline actions)
- Quote creation (inline, not a separate page)
- Booking creation (inline, not a separate page)

This is how modern tools like Linear, Intercom, and Slack work — the conversation is the workspace, and actions happen within the conversation.

### The proposed customer/business relationship

The customer and business sides should feel like **two views of the same network**, not two separate products. They should share:
- The same design language (already done with dark theme)
- The same navigation philosophy (fewer destinations, more contextual actions)
- The same conversation interface (messaging should feel the same on both sides)

The "Switch to Customer/Business" action should be more prominent — perhaps in a user menu at the top, not buried at the bottom of the sidebar.

---

## 8. PROPOSED INFORMATION ARCHITECTURE

### Public Network

```
/                          Landing page (hero + search + value prop)
/search                    Search (natural language + category browse)
/network                   Business directory (browse all businesses)
/business/[slug]           Business profile (public)
/business/[slug]/services/[offerSlug]  Service offer detail
/login                     Sign in
/signup                    Create account
```

**Changes:**
- Landing page should be more concise (3-4 sections, not 7)
- Search should be the primary entry point, not a secondary page
- Network page should be more visual (business cards with logos, ratings, service counts)

### Customer

```
/                          Landing (if not authenticated)
/dashboard                 Home (active enquiries, upcoming bookings, recommended actions)
/enquiries                 Enquiry list + conversation threads
/enquiries/[id]            Enquiry detail (conversation, quote, booking)
/bookings                  Booking list + schedule view
/bookings/[id]             Booking detail (status, execution, payment)
/history                   Completed services, invoices, reviews
/profile                   Account settings (name, email, password)
```

**Changes:**
- Remove "Quotes" as a top-level page — quotes are part of the enquiry flow
- Remove "Payments" as a top-level page — payments are part of the booking/history flow
- Remove "Services" — rename to "History" and combine completed services, invoices, and reviews
- Remove "Transactions" — orphaned page, integrate into History
- Add conversation/messaging UI to enquiry detail
- Add quote acceptance and booking creation to enquiry detail
- Add review creation to completed bookings

### Business

```
/                          Landing (if not authenticated)
/dashboard                 Home (pending actions, today's schedule, revenue snapshot)
/enquiries                 Enquiry inbox + conversation threads
/enquiries/[id]            Enquiry detail (conversation, quote creation, state transitions)
/schedule                  Bookings + service executions (calendar/list view)
/schedule/[id]             Booking/execution detail (status, completion, invoicing)
/finance                   Quotes, invoices, payments, ledger
/finance/quotes            Quote list + creation
/finance/invoices          Invoice list + creation
/finance/payments          Payment history + recording
/settings                  Business profile, service offers, team, Brain, communications
/settings/profile          Business profile
/settings/services         Service offers catalog
/settings/team             Members and invitations
/settings/brain            Business Brain configuration
/settings/communications   Channel configuration
```

**Changes:**
- Reduce from 10 to 5 top-level destinations (Home, Enquiries, Schedule, Finance, Settings)
- Move Operations → Schedule (more intuitive name)
- Move Quotes, Payments → Finance (grouped by concern)
- Move Business Brain, Communications, Members → Settings (configuration, not operational)
- Add onboarding flow for new businesses
- Add conversation-centric enquiry detail page
- Add inline quote creation from enquiry detail
- Add inline booking creation from quote acceptance
- Add service completion from schedule detail
- Add notification center

---

## 9. REDESIGN PRINCIPLES

1. **Workflow over entity.** Organize the UI around what the user is trying to accomplish, not around the database tables that store the data. "Enquiries" is a workflow. "Operations" is a database table.

2. **Conversation as workspace.** The enquiry conversation thread should be the primary interface for both customer and business. Actions (quote, book, pay, complete) should happen within the conversation, not on separate pages.

3. **Progressive disclosure.** Show the user only what they need right now. New businesses should see an onboarding flow, not a dashboard full of zeros. New customers should see a search interface, not a status board.

4. **Fewer destinations, more context.** Reduce top-level navigation to 4-5 items. Secondary destinations should be accessible through contextual menus, settings, or a command palette.

5. **Action-oriented empty states.** Every empty state should tell the user what to do next. "No enquiries yet" should have a "Create your first enquiry" button (customer) or "Your enquiries will appear here" (business).

6. **Consistent terminology.** "Services" means different things on each side. Use "Service Offers" for businesses and "History" or "Completed Work" for customers.

7. **Graceful degradation.** When a business doesn't exist yet, show an onboarding prompt, not an error message. When an API call fails, show a helpful message, not a raw error.

8. **Unified design language.** The customer and business sides should feel like two views of the same product, not two separate apps. Share components, patterns, and interaction models.

9. **Mobile-first navigation.** The mobile experience should not be an afterthought. Design the navigation for mobile first, then adapt for desktop.

10. **Real-time awareness.** The product should proactively surface what needs attention. New enquiries, pending quotes, upcoming bookings — these should be visible without navigating to each page.

---

## 10. IMPLEMENTATION PHASING

The frontend should be redesigned in a logical order that avoids visual inconsistency. Do not change random pages independently.

### Phase 1: Foundation
- Redesign the global shell (sidebar, header, mobile navigation)
- Establish the new navigation structure (5 top-level destinations for business, 5 for customer)
- Create shared components (conversation thread, action buttons, status badges, empty states)
- Implement the user menu (avatar, name, sign out, switch role)

### Phase 2: Business Onboarding
- Create a business setup wizard (profile → services → Brain → go)
- Handle the "no business" state gracefully on all pages
- Redirect new business users to onboarding, not the dashboard

### Phase 3: Enquiry-Centric Workspace
- Redesign the enquiry detail page as a conversation-centric workspace
- Add inline quote creation from enquiry detail
- Add inline booking creation from quote acceptance
- Add state transition buttons within the conversation

### Phase 4: Customer Journey
- Add enquiry creation from business profile/search results
- Add messaging UI to customer enquiry detail
- Add quote acceptance and booking creation
- Add review creation for completed bookings

### Phase 5: Operational Pages
- Redesign the business dashboard as a workspace (pending actions, today's schedule, revenue)
- Redesign the customer dashboard as a workspace (active enquiries, upcoming bookings)
- Redesign Schedule page (bookings + executions, calendar view)
- Redesign Finance page (quotes, invoices, payments, ledger)

### Phase 6: Settings and Configuration
- Consolidate Settings page (profile, services, team, Brain, communications)
- Improve Business Brain integration (surface insights contextually)
- Add notification center

### Phase 7: Polish
- Add icons to sidebar navigation
- Add breadcrumbs
- Add command palette / global search
- Improve mobile navigation (bottom tab bar or hamburger menu)
- Add loading states and error handling consistency
- Add accessibility improvements

---

## APPENDIX: OBSERVATIONS BY PAGE

### Public Pages

| Page | Status | Notes |
|------|--------|-------|
| Landing (/) | Good | Clean, clear value prop. Too long (7 sections). Search input works. |
| Search (/search) | Good | Natural language + category browse. Results display well. API errors on empty backend. |
| Network (/network) | Partial | Location filter exists. "Failed to load businesses" error on empty backend. |
| Login (/login) | Good | Simple, clean form. Works. |
| Signup (/signup) | Good | Role selection, form validation. Works. |
| Business Profile (/business/[slug]) | Untested | Exists but not audited with real data. |
| Service Offer Detail (/business/[slug]/services/[offerSlug]) | Untested | Exists but not audited with real data. |

### Customer Pages

| Page | Status | Notes |
|------|--------|-------|
| Dashboard | Partial | Shows stats (all zero), Quick Actions, Recent Activity (empty). |
| Profile | Broken | Shows loading skeleton, never resolves to form. |
| Enquiries | Good (empty) | Clean empty state with CTA. |
| Quotes | Broken | "Request validation failed" error. |
| Bookings | Broken | "Request validation failed" error. |
| Payments | Broken | Shows loading skeletons indefinitely. |
| Services | Broken | "Request validation failed" error. |
| Transactions | Orphaned | Not in sidebar. Clean empty state. |

### Business Pages

| Page | Status | Notes |
|------|--------|-------|
| Dashboard | Partial | Shows "No businesses registered yet" but renders full layout. |
| Enquiries | Good (empty) | Filter tabs with counts. Clean empty state. |
| Quotes | Good (empty) | Filter tabs. Clean empty state. |
| Bookings | Broken | "No business found" error + empty state. |
| Operations | Good (empty) | Sub-tabs (Operations, Invoices, Ledger). Clean empty state. |
| Services | Broken | Stuck on infinite loading. |
| Business Brain | Broken | Shows loading skeletons, never resolves. |
| Communications | Partial | "No business found" with guidance message. |
| Payments | Good (empty) | Filter tabs, "Record Payment" button. Clean empty state. |
| Profile | Partial | "No business found" error + form fields. Confusing. |
| Settings | Broken | Renders heading and tabs but no content. |
