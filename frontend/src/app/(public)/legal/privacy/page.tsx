export default function PrivacyPolicyPage() {
  return (
    <>
      <h1>Privacy Policy</h1>
      <p className="lead">
        FIELDed (&ldquo;we&rdquo;, &ldquo;us&rdquo;, &ldquo;our&rdquo;) is committed to protecting your privacy.
        This policy explains what data we collect, why, how we use it, and your rights.
      </p>
      <p className="text-xs text-[var(--text-muted)] mb-8">Last updated: 26 September 2026</p>

      <section>
        <h2>1. Data We Collect</h2>
        <h3>1.1 Account Data</h3>
        <p>
          When you create an account we collect your name, email address, and authentication credentials
          (hashed password). You may use FIELDed as a <strong>customer</strong> or as a <strong>business owner/member</strong>.
        </p>
        <h3>1.2 Profile Data</h3>
        <p>
          <strong>Customer profiles</strong> store your name, contact details, and service history.<br />
          <strong>Business profiles</strong> store business name, description, location, service offerings,
          pricing, availability, and operational configurations managed through the Business Brain.
        </p>
        <h3>1.3 Transaction Data</h3>
        <p>
          We process and store data related to enquiries, conversations, messages, quotes, bookings,
          service execution records, payments, invoices, ledger entries, and reviews.
        </p>
        <h3>1.4 Communication Data</h3>
        <p>
          Messages exchanged between customers and businesses, call recordings/summaries (where authorized),
          and notification preferences.
        </p>
        <h3>1.5 Payment Data</h3>
        <p>
          Payment processing is handled by <strong>Stripe</strong>. We store payment references, amounts,
          statuses, and reconciliation records. We do not store full card numbers or CVV data.
        </p>
        <h3>1.6 AI Processing Data</h3>
        <p>
          Our Business Brain and discovery features use AI to interpret natural language, match services,
          and generate proposals. AI processing data is described in our{" "}
          <a href="/legal/ai-disclosure">AI Disclosure</a>.
        </p>
      </section>

      <section>
        <h2>2. How We Use Your Data</h2>
        <ul>
          <li>To provide the FIELDed platform services (search, enquiry, booking, payment)</li>
          <li>To operate the Business Brain and Co-Brain features for business owners</li>
          <li>To process payments through Stripe and maintain financial records</li>
          <li>To send transactional notifications (enquiry updates, booking confirmations)</li>
          <li>To maintain audit trails for security and compliance</li>
          <li>To improve platform functionality and user experience</li>
        </ul>
      </section>

      <section>
        <h2>3. Data Sharing</h2>
        <p>
          We do not sell your data. Data is shared only as necessary to provide the service:
        </p>
        <ul>
          <li><strong>Between customers and businesses</strong> — when you submit an enquiry, the business receives your message</li>
          <li><strong>Stripe</strong> — for payment processing</li>
          <li><strong>Groq</strong> — for AI interpretation (natural language processing)</li>
          <li><strong>Neon</strong> — database hosting</li>
          <li><strong>Cloudflare</strong> — frontend hosting (Workers)</li>
          <li><strong>Google Cloud Run</strong> — backend hosting</li>
        </ul>
        <p>
          All third-party providers are bound by data processing agreements and are used solely
          to deliver the FIELDed service.
        </p>
      </section>

      <section>
        <h2>4. Tenant Isolation</h2>
        <p>
          FIELDed enforces strict tenant isolation. Businesses cannot access another business&rsquo;s data.
          Customers can only access their own data. Authorization is resolved server-side from
          authenticated identity and database relationships.
        </p>
      </section>

      <section>
        <h2>5. Data Retention</h2>
        <p>
          We retain your data for as long as your account is active or as needed to provide services.
          Financial records are retained in accordance with applicable legal requirements.
          You may request deletion of your account and associated data by contacting us.
        </p>
      </section>

      <section>
        <h2>6. Your Rights</h2>
        <p>You have the right to:</p>
        <ul>
          <li>Access your personal data</li>
          <li>Correct inaccurate data</li>
          <li>Request deletion of your data (subject to legal retention requirements)</li>
          <li>Object to processing</li>
          <li>Data portability</li>
        </ul>
        <p>To exercise these rights, contact us at the email below.</p>
      </section>

      <section>
        <h2>7. Security</h2>
        <p>
          We use industry-standard security measures including bcrypt password hashing,
          JWT authentication with token rotation, server-side authorization on every protected resource,
          encrypted database connections, and audit logging of all meaningful actions.
        </p>
      </section>

      <section>
        <h2>8. Contact</h2>
        <p>
          For privacy-related enquiries: <a href="mailto:hello@fielded.online">hello@fielded.online</a>
        </p>
      </section>
    </>
  );
}
