export default function AIDisclosurePage() {
  return (
    <>
      <h1>AI &amp; Business Brain Disclosure</h1>
      <p className="lead">
        FIELDed uses artificial intelligence to assist users across the platform.
        This disclosure explains where AI is used, what it can and cannot do,
        and how deterministic systems maintain authoritative control.
      </p>
      <p className="text-xs text-[var(--text-muted)] mb-8">Last updated: 26 September 2026</p>

      <section>
        <h2>1. Where AI Is Used</h2>

        <h3>1.1 Discovery AI</h3>
        <p>
          When customers describe what they need in natural language, AI interprets their
          request and extracts structured search parameters (service type, keywords, location,
          timing). The actual matching of businesses and service offers is performed by
          deterministic database queries — AI never invents businesses, services, prices,
          or availability.
        </p>

        <h3>1.2 Business Brain / Co-Brain</h3>
        <p>
          The Business Brain uses AI to converse with business owners, understand their
          operations, identify gaps, and propose improvements. AI observes, interprets,
          and drafts proposals — but all changes to business knowledge require deterministic
          validation and explicit owner approval before activation.
        </p>

        <h3>1.3 Call Agent</h3>
        <p>
          The Call Agent uses AI to handle telephone conversations with callers. It can
          understand caller intent, collect information, retrieve permitted business context,
          and create or continue enquiries where authorized. The Call Agent cannot independently
          set prices, commit to availability, or make financial decisions.
        </p>

        <h3>1.4 Marketing Agent</h3>
        <p>
          The Marketing Agent uses AI to draft content, identify campaign opportunities,
          and suggest marketing strategies. All content must be reviewed and approved by
          the business owner before publication. No channel is activated without explicit
          owner delegation.
        </p>
      </section>

      <section>
        <h2>2. What AI Cannot Do</h2>
        <p>AI in FIELDed is <strong>non-authoritative</strong>. Specifically, AI cannot:</p>
        <ul>
          <li>Set or change prices without business rule validation</li>
          <li>Determine availability without checking deterministic constraints</li>
          <li>Override business policies</li>
          <li>Authorize customers or grant permissions</li>
          <li>Change booking or transaction state directly</li>
          <li>Determine review eligibility</li>
          <li>Claim a business provides a service without a matching service offer</li>
          <li>Process payments or modify financial records</li>
          <li>Silently modify business knowledge (Brain)</li>
        </ul>
      </section>

      <section>
        <h2>3. Authority Model</h2>
        <p>
          Every AI action follows this pattern:
        </p>
        <ol>
          <li><strong>AI proposal</strong> — interpretation, classification, extraction, or draft</li>
          <li><strong>Structured schema</strong> — AI output is validated against explicit schemas</li>
          <li><strong>Deterministic validation</strong> — business rules, policies, and constraints are checked</li>
          <li><strong>Authorization</strong> — permissions and delegation are verified server-side</li>
          <li><strong>Owner approval or delegation</strong> — where required, explicit owner consent</li>
          <li><strong>Execution</strong> — only after all checks pass</li>
          <li><strong>Evidence &amp; audit</strong> — every action is recorded</li>
        </ol>
        <p>
          Deterministic systems (pricing engines, state machines, policy validators) remain
          the authoritative source of truth. AI assists but does not decide.
        </p>
      </section>

      <section>
        <h2>4. Agent Delegation</h2>
        <p>
          Business owners may explicitly delegate certain capabilities to AI agents.
          Delegations are:
        </p>
        <ul>
          <li><strong>Explicit</strong> — the owner must actively grant them</li>
          <li><strong>Time-bounded</strong> — delegations can expire</li>
          <li><strong>Revocable</strong> — the owner can withdraw them at any time</li>
          <li><strong>Policy-constrained</strong> — delegated actions must pass deterministic validation</li>
          <li><strong>Audited</strong> — every delegated action is logged with evidence</li>
        </ul>
        <p>
          Even with delegation, AI cannot bypass tenant isolation, financial controls,
          or business policy constraints.
        </p>
      </section>

      <section>
        <h2>5. AI Providers</h2>
        <p>
          FIELDed uses provider-agnostic AI adapters. Current providers include:
        </p>
        <ul>
          <li><strong>Groq</strong> — for conversational AI and structured output</li>
        </ul>
        <p>
          The architecture supports switching providers without changing business logic.
          AI credentials are stored server-side only and are never exposed to the frontend.
        </p>
      </section>

      <section>
        <h2>6. Data Processing</h2>
        <p>
          AI processing is limited to what is necessary for each workload. Prompt context
          is bounded to relevant information only. Sensitive data (payment details, full
          business databases) is never included in AI context unless explicitly required
          and authorized.
        </p>
      </section>

      <section>
        <h2>7. Contact</h2>
        <p>
          For questions about AI usage on FIELDed: <a href="mailto:hello@fielded.online">hello@fielded.online</a>
        </p>
      </section>
    </>
  );
}
