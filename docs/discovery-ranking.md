# FIELDed — Discovery & Ranking Architecture

> **Status**: SPECIFIED BUT NOT IMPLEMENTED (ranking is future)  
> **Phase**: Architecture + Specification Only  
> **Last Updated**: 2026-09-19

---

## Overview

This document defines how FIELDed matches customer intent to businesses and Service Offers. The discovery system has two phases: AI interpretation of customer intent, followed by deterministic matching against actual business data.

**Core principle**: AI may interpret customer intent. It must not bypass deterministic eligibility constraints.

---

## Architecture

```
Customer Input (natural language)
    │
    ▼
┌──────────────────────────────┐
│  1. INTENT INTERPRETATION    │
│  (AI — L1 INFORMATIONAL)    │
│                              │
│  "I need an electrician in   │
│   Manchester for a fuse box" │
│          │                   │
│          ▼                   │
│  DiscoveryIntent:            │
│  {                           │
│    category: "electrical",   │
│    location: "Manchester",   │
│    service: "fuse_box",      │
│    urgency: "normal"         │
│  }                           │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│  2. CANDIDATE FILTERING      │
│  (Deterministic)             │
│                              │
│  Find all businesses that:   │
│  - Have ACTIVE status        │
│  - Have ACTIVE ServiceOffers │
│  - In matching categories    │
│  - In matching locations     │
│  - Are not suspended         │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│  3. ELIGIBILITY CHECK        │
│  (Deterministic)             │
│                              │
│  For each candidate:         │
│  - Service Offer is ACTIVE   │
│  - Business profile is public│
│  - Service area matches      │
│  - Qualification can be met  │
│  - Availability exists       │
│    (future, Brain-dependent) │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│  4. RANKING                  │
│  (Deterministic signals)     │
│                              │
│  Score eligible candidates   │
│  using defined signals       │
│  (see Ranking section below) │
└──────────────────────────────┘
    │
    ▼
┌──────────────────────────────┐
│  5. RESULT PRESENTATION      │
│                              │
│  Return ranked results with  │
│  business + offer details    │
└──────────────────────────────┘
```

---

## 1. Intent Interpretation

### Current Implementation

The `DiscoveryInterpreter` wraps the `AIProvider` and produces a `DiscoveryIntent`:

```python
DiscoveryIntent
├── intent: str (service_search | business_lookup | general_enquiry)
├── service_category: str | null (category slug)
├── specific_service: str | null (more specific service description)
├── location: str | null (city, area, or address)
├── urgency: str (low | normal | high | emergency)
├── keywords: list[str]
└── raw_query: str (original customer text)
```

### Current AI Provider

`StubAIProvider` performs keyword-based extraction:
- Maps common terms to category slugs (electrician → electrical, plumber → plumbing)
- Extracts location via "in <CityName>" pattern
- Falls back to keyword matching on failure

### Future AI Provider

A real AI provider will:
- Understand semantic intent beyond keyword matching
- Handle ambiguous queries ("my sink is leaking" → plumbing)
- Extract multiple possible interpretations with confidence
- Handle typos and colloquial language
- Identify urgency from context

### Schema Validation

All AI output is validated against the `DiscoveryIntent` Pydantic schema. Invalid output → fallback to keyword extraction.

---

## 2. Candidate Filtering

Candidate filtering is **purely deterministic**. No AI involvement.

### Filter Criteria

| Filter | Source | Logic |
|---|---|---|
| Business status | `Business.status` | Must be `ACTIVE` |
| Business profile status | `BusinessProfile.public_status` | Must be `ACTIVE` |
| Service Offer status | `ServiceOffer.status` | Must be `ACTIVE` |
| Category match | `ServiceOffer.category_id` | Must match interpreted category or parent category |
| Location match | `BusinessProfile.service_area` | Must overlap with interpreted location |
| Delivery mode match | `ServiceOffer.delivery_mode` | Must match customer's implied delivery preference |

### Category Matching

Category matching uses the hierarchical `ServiceCategory` structure:
- Exact match: customer wants "electrical" → match ServiceOffers in "electrical"
- Parent match: customer wants "home services" → match all subcategories
- Child match: customer wants "fuse box repair" → match "electrical" if "fuse box repair" is a subcategory

### Location Matching

Location matching compares the interpreted location against `BusinessProfile.service_area` (JSONB):

```json
{
    "type": "radius",
    "center": {"lat": 53.48, "lng": -2.24},
    "radius_km": 25
}
```

Or:
```json
{
    "type": "areas",
    "names": ["Manchester", "Salford", "Trafford"]
}
```

**Current status**: `_filter_by_service_area()` is a pass-through (returns all matches). Location filtering is not yet implemented.

---

## 3. Eligibility Check

After candidate filtering, each candidate is checked for eligibility:

| Check | Deterministic? | Brain-Dependent? | Status |
|---|---|---|---|
| Service Offer is ACTIVE | Yes | No | ✅ IMPLEMENTED |
| Business profile is public | Yes | No | ✅ IMPLEMENTED |
| Service area overlap | Yes | No | 🔶 PARTIAL (pass-through) |
| Qualification requirements can be met | Yes | Yes (Brain D) | 🔮 FUTURE |
| Availability exists for request | Yes | Yes (Brain C) | 🔮 FUTURE |
| Pricing is compatible | Yes | Yes (Brain B) | 🔮 FUTURE |
| Compliance restrictions satisfied | Yes | Yes (Brain M) | 🔮 FUTURE |

### Eligibility Is Binary

A candidate is either eligible or not. There is no partial eligibility. If any eligibility check fails, the candidate is excluded from results.

---

## 4. Ranking Architecture

### Design Principles

1. **No arbitrary numeric weighting without evidence** — ranking signals must be justified
2. **Deterministic constraints first** — eligibility before ranking
3. **Transparency** — ranking logic must be explainable
4. **No AI authority over ranking** — AI interprets intent; ranking is deterministic

### Ranking Signals

| Signal | Type | Description | Weight Category |
|---|---|---|---|
| **Service match quality** | Deterministic | How closely the ServiceOffer matches the interpreted intent | Primary |
| **Business status** | Deterministic | ACTIVE businesses rank higher than PENDING | Primary |
| **Profile completeness** | Deterministic | More complete profiles indicate active businesses | Secondary |
| **Response capability** | Deterministic | Historical response time (future) | Secondary |
| **Rating** | Deterministic | Average customer rating (future, when reviews exist) | Secondary |
| **Availability match** | Deterministic | Whether business can actually serve the request (future, Brain-dependent) | Primary |
| **Pricing compatibility** | Deterministic | Whether pricing fits customer's implied budget (future) | Secondary |
| **Location proximity** | Deterministic | Distance between customer and business (future) | Secondary |
| **Recency** | Deterministic | How recently the business was active on the platform | Tertiary |

### Ranking Tiers (Proposed)

Rather than arbitrary numeric weights, use a tiered approach:

**Tier 1 — Exact Match**: ServiceOffer exactly matches interpreted category + specific service + location
**Tier 2 — Category Match**: ServiceOffer matches category + location but not specific service
**Tier 3 — Broad Match**: ServiceOffer matches category but location is approximate
**Tier 4 — Adjacent Match**: ServiceOffer in related category + location match

Within each tier, sort by secondary signals (rating, response time, profile completeness).

### Future Ranking Extensions

The architecture supports future extensions without core changes:

| Extension | How It Adds |
|---|---|
| Machine learning ranking | Add ML model as additional signal within tier sorting |
| Personalization | Add customer preference matching as signal |
| Seasonal adjustment | Add time-based signal modifiers |
| Promotion/featured | Add business-paid promotion as tier modifier (clearly labeled) |

---

## 5. Result Structure

```python
DiscoveryResult
├── intent: DiscoveryIntent (the interpreted query)
├── total_count: int
├── results: list[MatchedBusiness]
└── suggestions: list[str] (if no results, suggest alternatives)

MatchedBusiness
├── business_id: UUID
├── business_name: str
├── slug: str
├── description: str
├── public_status: str
├── average_rating: float | null
├── review_count: int
├── location: dict | null
├── matched_offers: list[MatchedServiceOffer]
└── match_quality: str (exact | category | broad | adjacent)

MatchedServiceOffer
├── offer_id: UUID
├── name: str
├── slug: str
├── description: str
├── category_name: str
├── delivery_mode: str
├── pricing_model: str
├── pricing_summary: str | null (human-readable pricing)
└── match_reason: str (why this offer matched)
```

---

## 6. Edge Cases

| Scenario | Handling |
|---|---|
| Ambiguous query ("I need help with my house") | Return top businesses across common categories; ask for clarification |
| No matching businesses | Return empty results with suggestions (broader category, nearby areas) |
| AI interpretation fails | Fall back to keyword matching; if still nothing, show category browser |
| Multiple possible interpretations | Return results for best interpretation; show alternatives |
| Location not recognized | Skip location filter; rank by category match only |
| Customer provides budget | Filter by pricing compatibility (future, Brain-dependent) |
| Very broad query ("services") | Return popular/highly-rated businesses; prompt for specificity |

---

## 7. Current vs. Future Status

| Component | Status | Notes |
|---|---|---|
| DiscoveryInterpreter | ✅ IMPLEMENTED | Wraps AI provider |
| StubAIProvider | ✅ IMPLEMENTED | Keyword-based |
| DiscoveryIntent schema | ✅ IMPLEMENTED | Pydantic validation |
| DiscoveryMatchingService | ✅ IMPLEMENTED | Queries actual DB |
| Category matching | ✅ IMPLEMENTED | Via ServiceOffer.category_id |
| Location/service area filtering | 🔶 PARTIAL | Pass-through (not filtering) |
| Ranking algorithm | 🔮 FUTURE | Currently simple match order |
| Availability-aware matching | 🔮 FUTURE | Brain-dependent |
| Pricing-aware matching | 🔮 FUTURE | Brain-dependent |
| Response capability ranking | 🔮 FUTURE | Needs historical data |
| Rating-based ranking | 🔮 FUTURE | Needs review system |
| Personalization | 🔮 FUTURE | Not yet specified |
| ML ranking model | 🔮 FUTURE | Not yet specified |
