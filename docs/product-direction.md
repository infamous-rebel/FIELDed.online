# FIELDed — Product Direction

**Consolidated Product Definition Document**  
**Date**: 2026-09-23  
**Status**: Pre-implementation — no code changes  
**Purpose**: Establish the actual product state and define the next product experience

---

## 1. Actual Current Deployment / Source Situation

### Source Code (Local)
- **Backend**: Python 3.12 + FastAPI, 18 phases complete, all committed to `main`
- **Frontend**: Next.js 15 + TypeScript, dark-theme redesign complete, all committed to `main`
- **Uncommitted changes**: ~40 files modified (frontend nav restructuring, backend refinements, audit screenshots, Phase 18 deployment fixes)
- **Latest commit**: `c6b89a7` — "fix(test): honor DATABASE_URL env in test conftest"

### Git / GitHub
- **Remote**: `https://github.com/infamous-rebel/Fielded.online.git`
- **Branch**: `main` is up to date with `origin/main`
- **CI**: GitHub Actions workflow configured (`.github/workflows/ci.yml`)

### Backend Deployment
- **Platform**: Google Cloud Run
- **API URL**: `https://fielded-api-23149731375.us-central1.run.app`
- **Database**: Neon PostgreSQL (production)
- **Status**: Deployed and verified (Phase 18 commit `065ddf5`)
- **Latest code**: Includes Phase 18 business activation state machine, category seed, brain conversation API
- **Health endpoint**: Returns 404 (no `/health` route — only `/api/v1/*` routes exist)

### Frontend Deployment
- **Platform**: Vercel
- **Project**: `fielded-frontend` (`prj_CnbAtzbQ8lIf7cVQR0hlAW52Jn7a`)
- **Status**: Deployed and verified (Phase 18 commit `13313db`)
- **Preview URL**: `https://fielded-37tj12ec1-infamous2s-projects.vercel.app` — **returns 404** (deployment expired or removed)
- **Production URL**: Not configured — no custom domain on Vercel project

### Domain: fielded.online
- **Current state**: **Parked domain page** on Hostinger DNS
- **NOT configured** for the current product
- Shows Hostinger's default "Parked Domain name" page with generic hosting ads
- DNS points to Hostinger, not Vercel or Cloud Run
- **This is the most critical deployment gap** — the product has no public-facing domain

### Frontend ↔ Backend Connection
- Frontend correctly configured: `NEXT_PUBLIC_API_URL="https://fielded-api-23149731375.us-central1.run.app"`
- API client (`api-client.ts`) is comprehensive (~2000+ lines)
- Auth helpers (`auth.ts`) functional
- CORS properly configured on backend for `fielded.online`, Vercel preview URLs, and `localhost:3000`
- **Connection works** but is only accessible via direct API URL or local dev server

### Business Brain in Deployed Application
- Backend Brain conversation API exists (`/api/v1/brain/conversation`)
- Frontend Brain page is conversation-first UI (committed)
- **Cannot verify** if deployed version matches latest code without working domain
- Uncommitted changes include Brain conversation API refinements

### Authoritative Configuration
- Backend: `.env.cloudrun` (Cloud Run environment)
- Frontend: `.env.local` (Vercel environment)
- Deploy: `deploy/cloudrun-env.yaml` (deployment variables)
- No secrets in code — all environment variables

### Summary
| Component | Status | Issue |
|-----------|--------|-------|
| Backend code | ✅ Complete | — |
| Frontend code | ✅ Complete | — |
| Git/GitHub | ✅ Synced | — |
| Backend deployed | ✅ Running | No health endpoint |
| Frontend deployed | ⚠️ Broken | Preview URL returns 404 |
| Domain | ❌ Not configured | Parked page on Hostinger |
| Business Brain | ⚠️ Unverifiable | Cannot access without domain |

---

## 2. Current Functional E2E State

### Customer Journey

| Step | Backend | Frontend | Notes |
|------|---------|----------|-------|
| Public Network Search | ✅ Working | ✅ Working | Natural language search with category browsing |
| Business discovery | ✅ Working | ✅ Working | Search results show business cards with match reasons |
| Business profile | ✅ Working | ⚠️ Partial | Page exists but untested with real data |
| Customer authentication | ✅ Working | ✅ Working | Login/signup functional with role selection |
| Start enquiry | ✅ Working | ❌ **Missing** | No "Send Enquiry" button on business profile or search results |
| Enquiry conversation | ✅ Working | ⚠️ Partial | Messaging UI exists in enquiry detail but untested |
| Business receives enquiry | ✅ Working | ✅ Working | Enquiries page with filter tabs and badge counter |
| Business responds | ✅ Working | ⚠️ Partial | Messaging UI exists but quote creation not connected |
| Quote | ✅ Working | ⚠️ Partial | Quotes page exists but no creation UI visible from enquiries |
| Customer receives quote | ✅ Working | ❌ **Broken** | Quotes page shows "Request validation failed" error |
| Customer accepts | ✅ Working | ❌ **Missing** | No quote acceptance UI |
| Booking | ✅ Working | ❌ **Broken** | Bookings page shows "Request validation failed" error |
| Customer payment | ✅ Working | ❌ **Broken** | Payments page shows loading skeletons indefinitely |
| Service | ✅ Working | ⚠️ Partial | Operations page exists with sub-tabs |
| Completion | ✅ Working | ❌ **Missing** | No service completion UI |
| Review | ✅ Working | ❌ **Missing** | No review creation UI |

### Critical Gaps
1. **No enquiry creation flow** — customer cannot initiate contact with business
2. **No quote acceptance flow** — customer cannot accept quote and create booking
3. **No payment flow** — customer cannot pay for booking
4. **No review flow** — customer cannot leave review after completion
5. **No business onboarding** — new business users see error messages on most pages
6. **Broken API calls** — Quotes, Bookings, Services pages show validation errors
7. **Blank pages** — Business Brain and Settings pages render blank

---

## 3. Call Agent / Communications Integration Status

### What Exists Technically
- Voice call agent implemented (Phase 14B/14C)
- Twilio TwiML integration for outbound calls
- OpenAI agent for conversational AI
- Call scheduling and campaign execution
- Call history and transcription storage
- Webhook security for Twilio callbacks

### Current Integration State
- Call Agent exists as a **backend capability** but is **not surfaced in the product UI**
- Communications page exists in business sidebar but shows only "No business found"
- No visible entry point to initiate calls from enquiry detail or customer profile
- Call history not visible in communications page
- No integration between Call Agent and enquiry/conversation workflow

### Relationship with Communications
- Communications page is intended for channel configuration (email, SMS, WhatsApp, voice)
- Call Agent is a specific channel capability (outbound voice calls)
- Currently **disconnected**: Call Agent runs as a separate technical capability, not as part of the Communications workflow

### Recommendation
- Call Agent should be surfaced as part of the Communications configuration in Settings
- Call initiation should be available from enquiry detail (contextual action)
- Call history should appear in the enquiry conversation thread
- **Do not create duplicate Call Agent functionality** — integrate existing capability into product workflow

---

## 4. Current Customer UX Problems

### Critical (Blocks Core Workflows)

1. **Journey stops at discovery** — Customer can search and find businesses but cannot take action. No "Send Enquiry" button on business profile or search results. The customer hits a dead end.

2. **No enquiry creation UI** — The primary customer action (describing what they need and sending it to a business) does not exist in the frontend. This is the core product value proposition and it's missing.

3. **No messaging UI** — The product's core differentiator is "dedicated conversations per enquiry" but there is no visible messaging interface for customers.

4. **Broken API calls on 3 of 7 pages** — Quotes, Bookings, and Services all display "Request validation failed" banners. This makes the product look broken to any new user.

5. **No quote acceptance flow** — Customer cannot accept a quote and proceed to booking. The workflow is incomplete.

6. **No payment flow** — Customer cannot pay for a booking. Payments page shows loading skeletons indefinitely.

7. **No review flow** — Customer cannot leave a review after service completion. This breaks the trust loop.

### High (Degrades Experience Significantly)

8. **Dashboard is a status board, not a workspace** — Shows four stat cards (all zero) and empty "Recent Activity." No sense of "here's what you should do next."

9. **Profile page shows loading skeleton** — Renders as a loading skeleton that never resolves to an editable form.

10. **Orphaned Transactions page** — Exists at `/customer/transactions` but has no link in the sidebar.

11. **Confusing "Services" naming** — Shows completed services and invoices. Customers don't think of these as "my services."

12. **7 sidebar items is too many** — No visual grouping. No hierarchy.

### Medium (Noticeable but Not Blocking)

13. **No notifications system** — Customer must manually check each page for updates.
14. **Inconsistent empty states** — Some pages have CTAs, some don't.
15. **No sign out in sidebar** — Sign out is only visible on the dashboard page.
16. **Mobile navigation is unusable** — 7 items in horizontal scroll.

---

## 5. Current Business UX Problems

### Critical (Blocks Core Workflows)

1. **No business onboarding** — New business user signs up and sees "No businesses registered yet" on most pages. No setup wizard, no "Get Started" prompt.

2. **"No business found" error on 6 of 11 pages** — Bookings, Services, Communications, Profile, Settings, and Brain page all show this error or render blank.

3. **Business Brain page is blank** — When there's no business, the Brain page shows loading skeletons that never resolve.

4. **Services page stuck on infinite loading** — Never resolves from the loading state.

5. **Settings page is blank** — Renders heading and tabs but no content.

6. **No quote creation UI visible from enquiries** — The enquiry detail page exists but there's no visible way to create a quote.

7. **No booking flow** — Neither side can create or manage bookings through the UI.

8. **No service completion UI** — Business cannot mark a service as complete.

### High (Degrades Experience Significantly)

9. **Dashboard contradicts itself** — Says "No businesses registered yet" but still renders the full dashboard layout.

10. **10 sidebar items is too many** — Classic SaaS navigation bloat problem.

11. **Operations is a vague catch-all** — Contains service executions, invoices, and ledger.

12. **No notification or alert system** — No way to see new enquiries, pending quotes, or upcoming bookings without manually navigating to each page.

13. **Business Brain feels like a separate product** — Not integrated into operational workflow.

14. **Communications page is bare** — Just "No business found." Not connected to Call Agent.

### Medium (Noticeable but Not Blocking)

15. **No icons in sidebar** — Text-only labels are harder to scan.
16. **No breadcrumbs** — Users can't see where they are in the hierarchy.
17. **Inconsistent terminology** — "Service Offers" vs "Services" vs "My Services."
18. **Mobile navigation is unusable** — 10 items in horizontal scroll.

---

## 6. Current Landing Page Problems

### Structural Issues

1. **Too long** — 7 sections before the CTA. Could be more concise (3-4 sections).

2. **Generic SaaS feel** — Feels like a template rather than a distinctive product identity.

3. **Industry bias** — Examples and imagery suggest electricians/plumbers/trades. The placeholder text "I need a plumber in Sydney..." reinforces this.

4. **Geographic bias** — "Sydney" as the example location. Product should not hardcode Australia as the default market.

5. **Weak value proposition** — "Tell us what you need. FIELDed finds where it can be done." This is functional but not compelling.

6. **No clear call to action** — "Get Started" button goes to signup, but there's no sense of what the user will get.

7. **Missing product demonstration** — No screenshots, no interactive demo, no video.

8. **Business Brain under-explained** — The "Powered by AI and the Business Brain" section is vague.

9. **No social proof** — No testimonials, no case studies, no trust signals.

10. **Footer is minimal** — Only has Search, Sign In, Sign Up links.

### What the Landing Page Should Communicate

1. This is a **global Business Network** where customers describe what they need in natural language.
2. Businesses receive **relevant enquiries** from customers who are ready to engage.
3. **Business Brain** turns business knowledge into governed operational capability.
4. The product is **service-agnostic** — it works for any legitimate service business.
5. The product is **global** — it works anywhere, not just Australia.

---

## 7. Current Navigation / Information Architecture Problems

### What Exists Today

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

### Problems

1. **Navigation mirrors the database schema, not the user's workflow.** Sidebar items are a direct map of backend domain modules.

2. **No visual grouping or hierarchy.** All items are at the same level.

3. **10 items for business is too many.** The sidebar becomes a laundry list.

4. **"Services" means different things on each side.** Customer "Services" shows completed work and invoices. Business "Services" shows service offers.

5. **"Payments" exists on both sides but serves different purposes.**

6. **"Bookings" exists on both sides but the creation flow is missing on both.**

7. **"Quotes" exists on both sides but the creation/acceptance flow is missing.**

8. **Operations is a vague catch-all.** Contains executions, invoices, ledger.

9. **Transactions is orphaned.** Exists but not in navigation.

10. **Business Brain is separate.** Not integrated into operational workflow.

11. **Communications is bare.** No clear purpose. Not connected to Call Agent.

12. **Settings is too much.** 5 tabs (Identity, Members, Communications, Payments, Security).

13. **Profile doesn't justify a top-level nav item.** Simple form.

14. **No persistent header in authenticated areas.** No search, no notifications center, no user menu, no breadcrumbs.

15. **"Switch to Customer/Business" is buried.** At the bottom of the sidebar.

---

## 8. Global / Service-Agnostic Positioning Problems

### Current Positioning Issues

1. **Industry bias toward trades** — Examples, imagery, and language suggest electricians, plumbers, and trades.

2. **Geographic bias toward Australia** — "Sydney" as the example location. Currency, addresses, phone formats, terminology all suggest Australia.

3. **Narrow demonstration examples** — The product should demonstrate that it understands natural-language service needs across many categories:
   - Professional services (consulting, legal, accounting)
   - Creative services (photography, design, writing)
   - Home services (cleaning, gardening, repairs)
   - Business services (marketing, IT, HR)
   - Technical services (web development, engineering)
   - Events (wedding planning, catering, photography)
   - Education (tutoring, coaching, training)
   - Repair (electronics, appliances, vehicles)
   - Hospitality/service providers (catering, event spaces)
   - And other legitimate service businesses

4. **Hardcoded assumptions** — Currency, addresses, phone formats, terminology, business regulations.

5. **Product is not positioned as a global Business Network** — The landing page says "Find Services, Connect with Businesses" which is functional but not compelling.

6. **Business Brain is not positioned as industry-agnostic** — The Brain should work for any legitimate service business, not just trades.

### What the Product Should Communicate

- **Global**: Works anywhere, not just Australia. No hardcoded geographic assumptions.
- **Service-agnostic**: Works for any legitimate service business, not just trades.
- **Natural language**: Customers describe what they need in plain English (or other languages).
- **Intelligent matching**: FIELDed interprets intent and matches to businesses with verified capabilities.
- **Governed execution**: Every business operates through its Business Brain — governed rules for pricing, availability, policies, and qualification.
- **Transparent communication**: Dedicated conversations per enquiry. Every message, quote, and decision is tracked and auditable.

### Examples Should Feel Like

- "I need a photographer for a wedding next month."
- "I need help preparing my company accounts."
- "I need someone to clean our office every week."
- "I need a website for my new business."
- "I need an electrician tomorrow."
- "I need a consultant to review my marketing strategy."
- "I need a tutor for my daughter in mathematics."
- "I need a caterer for a corporate event."

The exact examples should be improved based on the product, but the point is to demonstrate **breadth** rather than one industry.

---

## 9. Proposed New Product Mental Model

### Current Mental Model
```
Dashboard → Sidebar → Database module → CRUD page
```

### Proposed Mental Model
```
Workspace → What needs attention → Actions within context → Conversations as the primary interface
```

### For Business Owners
- "Here's what needs my attention right now" (enquiries to respond to, quotes to send, bookings to confirm)
- "Here's what's happening today" (scheduled work, active conversations)
- "Here's how my business is performing" (revenue, completion rate, reviews)
- "Here's how to configure my business" (services, pricing, policies, team)

### For Customers
- "Here's what I'm working on" (active enquiries, upcoming bookings)
- "Here's what I've done" (completed services, payment history, reviews)
- "Here's how to find what I need" (search, browse categories)

### Key Shifts

1. **From entity-centric to workflow-centric** — Organize the UI around what the user is trying to accomplish, not around the database tables that store the data.

2. **From page-centric to conversation-centric** — The enquiry conversation thread should be the primary interface for both customer and business. Actions (quote, book, pay, complete) should happen within the conversation, not on separate pages.

3. **From status board to operational workspace** — The dashboard should show what needs attention, not just statistics.

4. **From 10 sidebar items to 4-5 primary destinations** — Fewer top-level destinations, more contextual actions.

5. **From two separate products to two views of the same network** — Customer and business sides should feel like part of the same product, not separate apps.

---

## 10. Proposed Customer Experience Structure

### Customer Journey
```
Discover → Understand → Enquire → Communicate → Quote → Accept → Book → Pay → Complete → Review
```

### Proposed Customer Navigation (5 Primary Destinations)

1. **Home** (`/dashboard`)
   - Active enquiries (with status)
   - Upcoming bookings (with date/time)
   - Recommended actions (respond to quote, leave review, etc.)
   - Recent activity timeline

2. **Enquiries** (`/enquiries`)
   - List of all enquiries (active, pending, completed)
   - Conversation threads (primary interface)
   - Quote acceptance (inline)
   - Booking creation (inline from quote)

3. **Bookings** (`/bookings`)
   - List of all bookings (upcoming, completed, cancelled)
   - Booking detail (status, execution, payment)
   - Payment initiation (for upcoming bookings)
   - Review creation (for completed bookings)

4. **History** (`/history`)
   - Completed services
   - Invoices
   - Payment history
   - Reviews left

5. **Account** (`/account`)
   - Profile (name, email, password)
   - Notifications settings
   - Payment methods

### Key Changes

- **Remove "Quotes" as a top-level page** — Quotes are part of the enquiry flow. Customer sees quote in the enquiry conversation and accepts it there.

- **Remove "Payments" as a top-level page** — Payments are part of the booking/history flow. Customer pays from the booking detail or views payment history in History.

- **Remove "Services" (rename to "History")** — Customers don't think of these as "my services." They think of them as "what I've had done." Combine completed services, invoices, and reviews into one History page.

- **Remove "Transactions"** — Orphaned page. Integrate into History.

- **Add conversation/messaging UI to enquiry detail** — This is the primary interface. Customer can communicate with business, receive quotes, accept quotes, and create bookings all within the conversation.

- **Add quote acceptance and booking creation to enquiry detail** — Inline actions, not separate pages.

- **Add review creation to completed bookings** — After service completion, customer can leave a review from the booking detail or History page.

- **Move "Profile" to "Account"** — Profile doesn't justify a top-level nav item. Move into Account settings.

---

## 11. Proposed Business Workspace Structure

### Business Journey
```
New enquiry arrives → Understand customer need → Communicate → Quote → Schedule → Perform work → Complete → Review
```

### Proposed Business Navigation (5 Primary Destinations)

1. **Home** (`/dashboard`)
   - Pending actions (enquiries to respond to, quotes to send, bookings to confirm)
   - Today's schedule (bookings, service executions)
   - Revenue snapshot (this month, pending payments)
   - Recent activity timeline

2. **Enquiries** (`/enquiries`)
   - Enquiry inbox (new, active, completed)
   - Conversation threads (primary interface)
   - Quote creation (inline)
   - State transitions (inline)

3. **Schedule** (`/schedule`)
   - Bookings (upcoming, completed, cancelled)
   - Service executions (in progress, completed)
   - Calendar view (optional)
   - Service completion (inline)

4. **Finance** (`/finance`)
   - Quotes (draft, sent, accepted, rejected)
   - Invoices (draft, sent, paid, overdue)
   - Payments (received, pending, refunded)
   - Ledger (income, expenses, profit)

5. **Settings** (`/settings`)
   - Business profile
   - Service offers catalog
   - Team (members and invitations)
   - Business Brain configuration
   - Communications (channel configuration)
   - Payment settings

### Key Changes

- **Reduce from 10 to 5 top-level destinations** — Home, Enquiries, Schedule, Finance, Settings.

- **Move Operations → Schedule** — More intuitive name. A business owner looking for "what's happening today" would naturally navigate to "Schedule."

- **Move Quotes, Payments → Finance** — Grouped by concern. A business owner looking for financial information would naturally navigate to "Finance."

- **Move Business Brain, Communications, Members → Settings** — These are configuration, not operational. A business owner sets these up once and doesn't touch them daily.

- **Add onboarding flow for new businesses** — When a new business user signs up, guide them through:
  1. Create business profile (name, description, location, contact)
  2. Add service offers (what services do you provide?)
  3. Configure Business Brain (pricing, availability, policies)
  4. Go live (start receiving enquiries)

- **Add conversation-centric enquiry detail page** — When a business owner clicks on an enquiry, they see:
  - The conversation thread (primary)
  - Customer details (sidebar)
  - State transitions (inline actions)
  - Quote creation (inline, not a separate page)
  - Booking creation (inline, from quote acceptance)

- **Add inline quote creation from enquiry detail** — Business owner can create a quote without leaving the conversation.

- **Add inline booking creation from quote acceptance** — When customer accepts a quote, a booking is automatically created.

- **Add service completion from schedule detail** — Business owner can mark a service as complete from the schedule page.

- **Add notification center** — Proactive alerts for new enquiries, pending quotes, upcoming bookings, etc.

---

## 12. Proposed Global Navigation Philosophy

### Principles

1. **Fewer top-level destinations, more contextual actions** — 4-5 primary destinations, not 10. Secondary destinations accessible through contextual menus, settings, or a command palette.

2. **Workflow over entity** — Organize by what the user is trying to accomplish, not by database tables. "Enquiries" is a workflow. "Operations" is a database table.

3. **Conversation as workspace** — The enquiry conversation thread should be the primary interface. Actions happen within the conversation, not on separate pages.

4. **Progressive disclosure** — Show the user only what they need right now. New businesses see an onboarding flow, not a dashboard full of zeros. New customers see a search interface, not a status board.

5. **Unified design language** — Customer and business sides should feel like two views of the same product, not separate apps. Share components, patterns, and interaction models.

6. **Mobile-first navigation** — Design the navigation for mobile first, then adapt for desktop. Mobile should have a bottom tab bar or hamburger menu, not a horizontal scroll of 10 items.

7. **Persistent header with user menu** — All authenticated pages should have a minimal top bar with: user menu (avatar + name + sign out), notifications bell, and possibly a global search/command palette.

### Proposed Navigation Structure

**Public:**
- Logo + "Search" + "Network" + "Sign In" + "Sign Up"
- Minimal, clean, focused on getting the user into the product

**Customer (5 destinations):**
- Home
- Enquiries
- Bookings
- History
- Account

**Business (5 destinations):**
- Home
- Enquiries
- Schedule
- Finance
- Settings

**Shared elements:**
- User menu (avatar + name + sign out) in top-right
- Notifications bell in top-right
- "Switch to Customer/Business" in user menu (not buried in sidebar)
- Breadcrumbs for hierarchical pages
- Command palette (Cmd+K) for power users

---

## 13. Proposed Landing Page / Product Identity Direction

### Landing Page Goals

1. Immediately communicate: "This is a **global Business Network** where customers describe what they need in natural language."
2. Demonstrate: "Businesses receive **relevant enquiries** from customers who are ready to engage."
3. Explain: "**Business Brain** turns business knowledge into governed operational capability."
4. Show: "The product is **service-agnostic** — it works for any legitimate service business."
5. Prove: "The product is **global** — it works anywhere, not just Australia."

### Proposed Landing Page Structure (4 Sections, Not 7)

**Section 1: Hero**
- Headline: "The Business Network for Service Professionals"
- Subheadline: "Customers describe what they need. Businesses receive relevant enquiries. Business Brain governs how you operate."
- Primary CTA: "Describe what you need" (search input)
- Secondary CTA: "Add your business" (for business owners)
- Background: Abstract network visualization or diverse service professional imagery (not just trades)

**Section 2: How it works**
- Three-column layout:
  - **For Customers**: "Describe what you need in plain language. FIELDed matches your intent to qualified businesses. Communicate, receive quotes, and book — all in one conversation."
  - **For Businesses**: "Receive relevant enquiries from customers who are ready to engage. Communicate, quote, and book through a governed workflow. Business Brain handles the rules."
  - **For Everyone**: "Every message, quote, and decision is tracked and auditable. Transparent communication. No surprises. Full trust."
- Icons or illustrations for each column

**Section 3: Business Brain**
- Headline: "Your business knowledge, governed by rules you control"
- Subheadline: "Business Brain turns your pricing, availability, policies, and qualification rules into governed operational capability. AI assists, but deterministic logic remains authoritative."
- Three examples:
  - **Pricing**: "Set your rates by service, by hour, or by project. Business Brain applies your rules consistently."
  - **Availability**: "Define your working hours, holidays, and booking windows. Business Brain prevents double-booking."
  - **Policies**: "Set your cancellation, rescheduling, and payment policies. Business Brain enforces them fairly."
- Screenshot or diagram of Business Brain conversation interface

**Section 4: Social proof / CTA**
- Headline: "Join the network"
- Two CTAs:
  - "Find a business" (for customers)
  - "Add your business" (for business owners)
- Trust signals: "Private by design. Secure access. Full transparency."
- (Future: testimonials, case studies, usage statistics)

### Product Identity

- **Name**: FIELDed (keep the name, but broaden the positioning)
- **Tagline**: "The Business Network for Service Professionals" (or similar)
- **Visual identity**: Modern, clean, professional. Not generic SaaS. Not trades-specific.
- **Color palette**: Keep the dark theme with green accent, but ensure it feels professional, not "hacker."
- **Typography**: Clean, readable, modern. Not playful, not corporate.
- **Imagery**: Diverse service professionals (not just trades). Global, not Australia-specific.

### Examples Should Demonstrate Breadth

- "I need a photographer for a wedding next month."
- "I need help preparing my company accounts."
- "I need someone to clean our office every week."
- "I need a website for my new business."
- "I need an electrician tomorrow."
- "I need a consultant to review my marketing strategy."
- "I need a tutor for my daughter in mathematics."
- "I need a caterer for a corporate event."

---

## 14. How Business Brain Should Fit into the Overall Product

### Business Brain's Role

Business Brain should remain a **distinct intelligence experience** while relevant intelligence appears **contextually** in operational workflows.

### Where Brain Intelligence Should Surface

1. **Enquiry creation** — Brain identifies information missing from an enquiry and prompts the customer to provide it. (e.g., "What's the approximate size of the area you need cleaned?")

2. **Enquiry detail** — Brain helps interpret a business rule. (e.g., "This customer is asking for a refund, but your policy says refunds are only available within 7 days of service completion.")

3. **Quote creation** — Brain suggests pricing based on business rules. (e.g., "Based on your hourly rate of $80 and the estimated 3 hours, the quote should be $240.")

4. **Booking creation** — Brain checks availability and prevents conflicts. (e.g., "This booking conflicts with an existing booking on Thursday at 2pm.")

5. **Dashboard** — Brain surfaces decisions requiring approval. (e.g., "3 enquiries need your response. 2 quotes are pending acceptance. 1 booking is scheduled for today.")

6. **Settings** — Brain configuration remains here, but the configuration is more conversational and less form-based. (e.g., "Tell me about your pricing rules" rather than a form with 20 fields.)

### Where Brain Intelligence Should NOT Surface

- **Deterministic authority remains where it currently belongs** — Brain does not override pricing, availability, authorization, or transaction state. Brain assists, but deterministic logic decides.

- **Brain does not become a chatbot** — Brain is not a general-purpose chatbot. Brain is a governed intelligence layer that assists with specific operational decisions.

- **Brain does not replace the UI** — Brain insights should appear contextually, not as a separate chat interface that the user must navigate to.

### Business Brain Page

The Business Brain page should remain as a **configuration and insight center**, but it should not be a top-level navigation item. It should be accessible through Settings.

The page should show:
- Brain status (active, learning, needs attention)
- Conversation interface (for configuring rules)
- Proposals (changes the Brain wants to make)
- Needs attention (items requiring owner approval)
- Knowledge (what the Brain knows about the business)

The page should NOT show:
- Raw JSON editors
- Technical implementation details
- Governance/version control (unless explicitly requested)

---

## 15. Recommended Implementation Sequence

### Phase 1: Foundation (Week 1-2)
- Redesign the global shell (sidebar, header, mobile navigation)
- Establish the new navigation structure (5 top-level destinations for business, 5 for customer)
- Create shared components (conversation thread, action buttons, status badges, empty states)
- Implement the user menu (avatar, name, sign out, switch role)
- Add persistent header with notifications bell
- Add breadcrumbs for hierarchical pages

### Phase 2: Business Onboarding (Week 2-3)
- Create a business setup wizard (profile → services → Brain → go)
- Handle the "no business" state gracefully on all pages
- Redirect new business users to onboarding, not the dashboard
- Add progressive disclosure (don't show everything at once)

### Phase 3: Landing Page (Week 3)
- Redesign landing page (4 sections, not 7)
- Update examples to be service-agnostic and global
- Update imagery to be diverse (not just trades)
- Add clear CTAs for customers and businesses
- Add Business Brain explanation

### Phase 4: Enquiry-Centric Workspace (Week 4-5)
- Redesign the enquiry detail page as a conversation-centric workspace
- Add inline quote creation from enquiry detail
- Add inline booking creation from quote acceptance
- Add state transition buttons within the conversation
- Add messaging UI to customer enquiry detail

### Phase 5: Customer Journey (Week 5-6)
- Add enquiry creation from business profile/search results
- Add quote acceptance and booking creation to enquiry detail
- Add payment initiation from booking detail
- Add review creation for completed bookings
- Fix broken API calls on Quotes, Bookings, Services pages

### Phase 6: Operational Pages (Week 6-7)
- Redesign the business dashboard as a workspace (pending actions, today's schedule, revenue)
- Redesign the customer dashboard as a workspace (active enquiries, upcoming bookings)
- Redesign Schedule page (bookings + executions, calendar view)
- Redesign Finance page (quotes, invoices, payments, ledger)

### Phase 7: Settings and Configuration (Week 7-8)
- Consolidate Settings page (profile, services, team, Brain, communications)
- Improve Business Brain integration (surface insights contextually)
- Add notification center
- Integrate Call Agent into Communications workflow

### Phase 8: Polish (Week 8)
- Add icons to sidebar navigation
- Add command palette / global search
- Improve mobile navigation (bottom tab bar or hamburger menu)
- Add loading states and error handling consistency
- Add accessibility improvements
- Update all examples to be service-agnostic and global

### Phase 9: Deployment (Week 8-9)
- Configure fielded.online domain to point to Vercel frontend
- Verify all pages work in production
- Test all workflows end-to-end
- Monitor for errors and performance issues

---

## Appendix: Key Observations

### What the Product Currently Feels Like
FIELDed feels like a **backend-first SaaS dashboard** that has been incrementally wrapped in a dark-theme frontend. The product is structurally organized around its database entities (Enquiries, Quotes, Bookings, Payments, Services, Operations) rather than around the workflows of the people who use it.

The public-facing side (landing, search, network) is the most coherent part of the product. It presents a clear value proposition and a functional discovery experience. But the moment a user signs up — as either customer or business — the experience fragments into a collection of CRUD screens connected by a sidebar.

The product does not yet feel like a **service network**. It feels like a **database browser with a green accent color**.

### What is Structurally Wrong

1. **The navigation mirrors the database schema, not the user's workflow.** The sidebar items (Dashboard, Enquiries, Quotes, Bookings, Operations, Services, Business Brain, Communications, Payments, Settings) are a direct map of the backend domain modules. A business owner does not think "I need to check my Operations module." They think "I need to see what jobs are happening today."

2. **There is no onboarding or first-run experience.** A new business user signs up and immediately sees a dashboard full of zeros, error banners ("No business found. Create one first."), and blank pages. There is no guidance, no setup wizard, no progressive disclosure. The product assumes the user already has a configured business.

3. **The customer and business experiences are completely siloed.** They share no design language beyond the dark theme. The customer side has 7 nav items; the business side has 10. There is no unified identity — just a "Switch to Customer/Business" link buried at the bottom of the sidebar.

4. **Critical workflows are invisible.** There is no visible path to: create an enquiry (customer), send a quote (business), accept a quote and book (customer), mark a booking complete (business), leave a review (customer), or record a payment (business). These workflows exist in the backend API but have no frontend entry points.

5. **The product is stuck between two mental models.** It wants to be a conversational, AI-assisted service network (the landing page promises "Describe what you need in plain language"). But the authenticated experience is a traditional table-and-form SaaS dashboard. The promise and the reality do not match.

### What the Product Should Become

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

### Redesign Principles

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

**End of Document**

This document defines the product direction for FIELDed's next major phase. No code changes should be made until this direction is reviewed and approved. Once approved, implementation should follow the recommended sequence to avoid visual inconsistency and ensure a coherent product experience.
