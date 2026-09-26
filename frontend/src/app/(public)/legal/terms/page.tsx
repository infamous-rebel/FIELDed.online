export default function TermsOfServicePage() {
  return (
    <>
      <h1>Terms of Service</h1>
      <p className="lead">
        These terms govern your use of the FIELDed platform. By creating an account or using FIELDed,
        you agree to these terms.
      </p>
      <p className="text-xs text-[var(--text-muted)] mb-8">Last updated: 26 September 2026</p>

      <section>
        <h2>1. The Platform</h2>
        <p>
          FIELDed is a customer-to-business service network. Customers describe what they need in
          plain language, discover businesses capable of fulfilling their needs, initiate enquiries,
          communicate with businesses, receive quotes, book services, and review completed work.
          Businesses operate through the FIELDed Business End, which includes profile management,
          service configuration, the Business Brain, enquiry handling, quoting, booking, and payment processing.
        </p>
      </section>

      <section>
        <h2>2. Accounts</h2>
        <p>
          You must provide accurate information when creating an account. You are responsible for
          maintaining the security of your credentials. You must notify us of any unauthorized access.
          One person may hold one customer account and/or be a member of one or more businesses.
        </p>
      </section>

      <section>
        <h2>3. Customer Obligations</h2>
        <ul>
          <li>Provide accurate information when submitting enquiries</li>
          <li>Communicate honestly and respectfully with businesses</li>
          <li> Honour accepted quotes and bookings</li>
          <li>Pay for services received through the platform</li>
          <li>Leave honest, factual reviews based on actual experience</li>
        </ul>
      </section>

      <section>
        <h2>4. Business Obligations</h2>
        <ul>
          <li>Provide accurate business profiles and service descriptions</li>
          <li>Respond to enquiries in a timely manner</li>
          <li>Honour quotes and bookings issued through the platform</li>
          <li>Deliver services as described and quoted</li>
          <li>Maintain accurate Business Brain configurations</li>
          <li>Comply with applicable laws and regulations</li>
        </ul>
      </section>

      <section>
        <h2>5. Payments &amp; Fees</h2>
        <p>
          Payments are processed through Stripe. FIELDed may charge a platform fee on transactions
          as defined in the applicable Commercial Policy. Fees are calculated deterministically
          and disclosed before payment confirmation. Businesses receive proceeds less the platform fee.
        </p>
      </section>

      <section>
        <h2>6. Reviews</h2>
        <p>
          Reviews must be based on actual completed services. Reviews must be honest and factual.
          FIELDed may remove reviews that are fraudulent, offensive, or violate these terms.
          AI does not determine review eligibility — only completed bookings with verified
          payment may become eligible for review.
        </p>
      </section>

      <section>
        <h2>7. AI Features</h2>
        <p>
          FIELDed uses AI to assist with interpretation, discovery, business knowledge management,
          and communication. AI output is never authoritative on its own. See our{" "}
          <a href="/legal/ai-disclosure">AI Disclosure</a> for details on how AI is used and its limitations.
        </p>
      </section>

      <section>
        <h2>8. Intellectual Property</h2>
        <p>
          You retain ownership of your content (business profiles, service descriptions, reviews).
          By posting content on FIELDed, you grant us a license to display and process it as
          necessary to operate the platform.
        </p>
      </section>

      <section>
        <h2>9. Limitation of Liability</h2>
        <p>
          FIELDed provides the platform for connecting customers and businesses. We are not a party
          to the service agreements between customers and businesses. We do not guarantee the quality,
          availability, or outcome of services provided by businesses on the platform.
        </p>
      </section>

      <section>
        <h2>10. Termination</h2>
        <p>
          Either party may terminate their account with notice. FIELDed may suspend accounts that
          violate these terms or pose a risk to other users. Financial obligations survive termination.
        </p>
      </section>

      <section>
        <h2>11. Changes to Terms</h2>
        <p>
          We may update these terms. Material changes will be communicated via the platform.
          Continued use after changes constitutes acceptance.
        </p>
      </section>

      <section>
        <h2>12. Contact</h2>
        <p>
          For questions about these terms: <a href="mailto:hello@fielded.online">hello@fielded.online</a>
        </p>
      </section>
    </>
  );
}
