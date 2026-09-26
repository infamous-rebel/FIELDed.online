export default function BusinessTermsPage() {
  return (
    <>
      <h1>Business Terms</h1>
      <p className="lead">
        These terms apply specifically to businesses operating on the FIELDed platform.
        By creating or managing a business on FIELDed, you agree to these terms in addition
        to the general <a href="/legal/terms">Terms of Service</a>.
      </p>
      <p className="text-xs text-[var(--text-muted)] mb-8">Last updated: 26 September 2026</p>

      <section>
        <h2>1. Business Membership</h2>
        <p>
          A business account is managed by its owner. The owner may invite members with
          admin or staff roles. Each member role has defined permissions. The owner is
          responsible for all actions taken by members of their business.
        </p>
      </section>

      <section>
        <h2>2. Business Profile &amp; Services</h2>
        <p>
          Businesses must provide accurate information about their services, pricing,
          availability, and policies. The Business Brain stores operational knowledge
          that governs how the business interacts with customers through the platform.
        </p>
        <p>
          Businesses must not claim to provide services they are not qualified or
          authorized to deliver. Service descriptions must accurately represent what is offered.
        </p>
      </section>

      <section>
        <h2>3. Business Brain</h2>
        <p>
          The Business Brain is a versioned, governed knowledge system. Changes to the
          Business Brain flow through a structured approval process. AI may propose
          changes, but only deterministic validation and owner approval can activate them.
        </p>
        <p>
          The Business Brain determines how your business responds to enquiries,
          calculates pricing, manages availability, and handles policies. You are
          responsible for ensuring your Brain configuration accurately reflects
          your business operations.
        </p>
      </section>

      <section>
        <h2>4. Enquiry Handling</h2>
        <p>
          Businesses should respond to customer enquiries in a timely manner.
          Quotes issued through the platform are binding for the validity period stated.
          Bookings accepted through the platform create a service commitment.
        </p>
      </section>

      <section>
        <h2>5. Platform Fees</h2>
        <p>
          FIELDed charges a platform fee on transactions processed through the platform.
          The fee structure is defined in the applicable Commercial Policy and is
          calculated deterministically before payment confirmation. Fees are deducted
          from the transaction before proceeds are transferred to the business.
        </p>
      </section>

      <section>
        <h2>6. Payments &amp; Payouts</h2>
        <p>
          Payments are processed through Stripe Connect. Businesses receive proceeds
          via their connected Stripe account. Payout timing is governed by Stripe&rsquo;s
          settlement schedule. FIELDed does not hold business funds.
        </p>
      </section>

      <section>
        <h2>7. Disputes &amp; Refunds</h2>
        <p>
          Disputes between customers and businesses should first be addressed through
          the platform&rsquo;s messaging system. Refunds are processed through the platform
          and governed by the business&rsquo;s configured refund policies. Disputes raised
          through Stripe (chargebacks) are handled according to Stripe&rsquo;s dispute process.
        </p>
      </section>

      <section>
        <h2>8. Agent Delegations</h2>
        <p>
          Business owners may delegate certain capabilities to AI agents (Business Brain,
          Call Agent, Marketing Agent). Delegations are explicit, time-bounded, and
          revocable. The business owner remains responsible for actions taken by
          delegated agents within the scope of the delegation.
        </p>
      </section>

      <section>
        <h2>9. Suspension &amp; Termination</h2>
        <p>
          FIELDed may suspend a business account for violations of these terms,
          fraudulent activity, or to protect other users. Outstanding financial
          obligations survive termination.
        </p>
      </section>

      <section>
        <h2>10. Contact</h2>
        <p>
          For business-related enquiries: <a href="mailto:hello@fielded.online">hello@fielded.online</a>
        </p>
      </section>
    </>
  );
}
