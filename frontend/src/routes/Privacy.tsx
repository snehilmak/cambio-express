import { useEffect } from "react";
import { Link } from "react-router-dom";

// /app/privacy — public privacy policy. No auth, no API calls.
//
// This is the Stripe-required privacy URL (Financial Connections +
// Checkout both link to it from their hosted pages), so it must
// remain reachable to anyone with the URL. Kept under the unauthed
// SPA routes alongside /app/forgot-password etc.
//
// Visual chrome (sticky brand nav + dark backdrop + grid + glow)
// mirrors the rest of the auth family so the public-facing pages
// read as one experience. The legacy /privacy used a light
// "document on cream" treatment that predated the dark-only design
// system; we ported the body copy verbatim and re-skinned it in the
// neon palette. Body copy is the source of truth — never change it
// without product/legal sign-off (see the closing legal note).
export default function Privacy() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  return (
    <>
      <style>{PAGE_CSS}</style>

      <nav className="site">
        <Link to="/" className="nav-brand">
          <img className="mark" src="/static/brand-mark.svg" alt="" />
          <span className="name">DineroBook</span>
        </Link>
        <Link to="/" className="nav-login">← Back to home</Link>
      </nav>

      <div className="page">
        <div className="page-grid" aria-hidden="true" />
        <div className="page-glow" aria-hidden="true" />

        <article className="doc">
          <header className="doc-head">
            <div className="status-pill">
              <span className="dot" />
              <span className="label">PRIVACY POLICY</span>
            </div>
            <h1>Privacy Policy</h1>
            <div className="effective">Last updated: April 20, 2026</div>
          </header>

          <p>
            DineroBook (“<strong>DineroBook</strong>”, “we”, “us”, or “our”) provides
            bookkeeping software for money-service businesses (“MSBs”) such as
            remittance storefronts and small retailers. This Privacy Policy explains
            what information we collect when you or your business uses our service at{" "}
            <a href="https://dinerobook.com">dinerobook.com</a> (the
            “<strong>Service</strong>”), how we use it, and the choices you have.
          </p>

          <p>
            By using the Service you agree to the practices described here. If you
            do not agree, please do not use the Service.
          </p>

          <h2>1. Who this policy covers</h2>
          <p>This policy applies to:</p>
          <ul>
            <li><strong>Store owners and administrators</strong> — the account holders who subscribe to DineroBook;</li>
            <li><strong>Store employees</strong> — users invited by an administrator to log transfers and reports;</li>
            <li><strong>Multi-store owners</strong> — individuals who connect multiple stores under a single account;</li>
            <li><strong>Customers of participating stores</strong> — individuals whose money-transfer details are recorded by store staff in the Service.</li>
          </ul>

          <h2>2. Information we collect</h2>

          <h3>2.1 Account and business information</h3>
          <p>
            When you sign up or manage a store, we collect your full name, email
            address, password (stored hashed, never in plain text), phone number,
            store name, and store contact information.
          </p>

          <h3>2.2 Customer and transaction records</h3>
          <p>
            Store staff may enter information about their own customers into the
            Service, including:
          </p>
          <ul>
            <li>Sender name, phone number with country code, address, and date of birth;</li>
            <li>Recipient name, country, and phone number;</li>
            <li>Amounts sent, fees, commissions, federal tax, and confirmation numbers;</li>
            <li>Internal notes recorded by staff.</li>
          </ul>
          <p>
            This information is entered and controlled by the store. DineroBook
            stores it on behalf of the store so it can be retrieved, reconciled,
            and reported later.
          </p>

          <h3>2.3 Bank account information (Stripe Financial Connections)</h3>
          <p>
            If you connect a bank account to DineroBook, we use{" "}
            <strong>Stripe Financial Connections</strong> to authenticate with
            your bank and retrieve account information.{" "}
            <strong>
              We do not see, store, or ever have access to your online banking
              username or password.
            </strong>{" "}
            The bank login happens entirely on Stripe’s secure hosted screens.
          </p>
          <p>We receive and store only:</p>
          <ul>
            <li>The institution name and the last four digits of the account;</li>
            <li>A non-reversible account identifier issued by Stripe;</li>
            <li>Balance snapshots (refreshed when you click Refresh, or when you open the Bank page).</li>
          </ul>
          <p>
            We currently do not pull individual bank transactions; if we begin to,
            we will update this policy and notify affected accounts. You can
            disconnect a bank account at any time from the Bank page, which
            revokes our access via Stripe immediately.
          </p>

          <h3>2.4 Billing information</h3>
          <p>
            Paid subscriptions are processed by Stripe. DineroBook receives a
            subscription identifier and plan status from Stripe; we do not store
            full payment-card numbers. Stripe’s own privacy policy is available
            at <a href="https://stripe.com/privacy">stripe.com/privacy</a>.
          </p>

          <h3>2.5 Technical information</h3>
          <p>
            When you access the Service we automatically collect standard server
            logs: IP address, browser user agent, requested pages, response
            status, and timestamps. We use this data to operate, secure, and
            debug the Service.
          </p>

          <h2>3. How we use information</h2>
          <ul>
            <li>
              <strong>To provide the Service</strong> — authenticate users, display
              the right store’s data, generate daily books and monthly P&amp;L
              reports, reconcile ACH batches, and render bank balances.
            </li>
            <li>
              <strong>Billing</strong> — process subscription payments and send
              receipts via Stripe.
            </li>
            <li>
              <strong>Customer support</strong> — respond to questions, investigate
              issues, and restore access.
            </li>
            <li>
              <strong>Security and fraud prevention</strong> — detect abuse,
              protect against unauthorized access, and audit administrator actions.
            </li>
            <li>
              <strong>Service improvement</strong> — analyze aggregate,
              non-identifying usage data to improve features and performance.
            </li>
            <li>
              <strong>Legal compliance</strong> — comply with applicable laws and
              respond to valid legal requests.
            </li>
          </ul>

          <h2>4. How information is shared</h2>
          <p>
            DineroBook does <strong>not</strong> sell personal information. We
            share information only as follows:
          </p>
          <ul>
            <li>
              <strong>Within the owner umbrella</strong> — a sender logged at one
              of your stores is visible at sibling stores under the same owner.
              Unrelated stores cannot see each other’s customers.
            </li>
            <li>
              <strong>With service providers</strong> who help us run the Service:
              <ul>
                <li>
                  <strong>Stripe</strong> — billing, Stripe Financial Connections
                  for bank data, and email receipts;
                </li>
                <li>
                  <strong>Our cloud hosting and database provider</strong> — to
                  store and deliver the Service;
                </li>
                <li>
                  <strong>Email delivery</strong> — for transactional emails
                  such as password-reset links.
                </li>
              </ul>
              These providers are contractually limited to processing data on our
              behalf.
            </li>
            <li>
              <strong>To comply with the law</strong> — when required by subpoena,
              court order, or other legal process, or to protect the rights,
              property, or safety of DineroBook, our users, or others.
            </li>
            <li>
              <strong>In a business transfer</strong> — if DineroBook is involved
              in a merger, acquisition, or asset sale, user information may be
              transferred as part of that transaction; we will notify affected
              users beforehand.
            </li>
          </ul>

          <h2>5. Data retention</h2>
          <p>
            While your subscription is active we retain all information for as long
            as needed to provide the Service. If a store cancels its subscription,
            we keep the store’s data for <strong>six (6) months</strong> so the
            business can come back without losing history. At the end of that
            window all per-store records — transfers, daily reports, monthly P&amp;L,
            ACH batches, employees, and bank-connection metadata — are permanently
            deleted from our production database.
          </p>
          <p>
            Customer rows entered by stores (senders and recipients) are subject
            to the same retention window as the store they belong to. Limited
            records may be kept longer if required for legal, regulatory, tax,
            or fraud-prevention purposes.
          </p>

          <h2>6. Security</h2>
          <p>We use a layered approach to protect your data:</p>
          <ul>
            <li>
              Passwords are stored using industry-standard hashing (never in
              plain text).
            </li>
            <li>
              Password-reset tokens are stored as a hash, are single-use, and
              expire after one hour.
            </li>
            <li>All traffic is encrypted in transit with HTTPS.</li>
            <li>
              Administrative actions taken on the platform are written to an
              append-only audit log.
            </li>
            <li>
              Access to production systems is restricted to personnel who
              require it to operate the Service.
            </li>
          </ul>
          <p>
            No online service can guarantee absolute security. If we become aware
            of a breach affecting your account we will notify you in accordance
            with applicable law.
          </p>

          <h2>7. Your choices and rights</h2>
          <p>Depending on where you live, you may have the right to:</p>
          <ul>
            <li>access the personal information we hold about you;</li>
            <li>correct information that is inaccurate or incomplete;</li>
            <li>delete your personal information, subject to legitimate retention needs;</li>
            <li>export a copy of your information in a common format;</li>
            <li>object to or restrict certain processing;</li>
            <li>withdraw consent where processing is based on consent.</li>
          </ul>
          <p>
            To exercise these rights, contact us at the address in Section 11.
            Administrators can also manage most of their store’s information
            directly from the Settings page inside the Service.
          </p>

          <h2>8. Children’s privacy</h2>
          <p>
            The Service is not directed to individuals under 13 years of age, and
            we do not knowingly collect personal information from anyone under
            13. If you believe a child has provided us personal information,
            please contact us and we will delete it.
          </p>

          <h2>9. International users</h2>
          <p>
            DineroBook is operated from the United States. If you access the
            Service from outside the United States, your information will be
            transferred to, stored, and processed in the United States. Where
            required by applicable law, we use appropriate safeguards for
            international data transfers.
          </p>

          <h2>10. Changes to this policy</h2>
          <p>
            We may update this Privacy Policy from time to time. The “Last
            updated” date at the top reflects the most recent version. Material
            changes will be communicated in-app or by email before taking
            effect. Continued use of the Service after an update constitutes
            acceptance of the revised policy.
          </p>

          <h2>11. Contact us</h2>
          <p>If you have questions about this policy or our privacy practices, email us:</p>
          <p>
            <strong>DineroBook Privacy</strong>
            <br />
            Email:{" "}
            <a href="mailto:dinerobook26@gmail.com">dinerobook26@gmail.com</a>
          </p>

          <div className="note">
            This Privacy Policy is provided as a starting point. Before launching
            publicly, please have it reviewed by counsel familiar with U.S.
            money-services businesses (BSA/AML), state MSB regulation, and the
            privacy laws applicable to your customers (e.g. CCPA/CPRA, GDPR).
            Also update the contact email, mailing address, and the specific list
            of subprocessors to match your actual vendors.
          </div>
        </article>
      </div>
    </>
  );
}


// Page-local CSS. The chrome (sticky nav + page backdrop + grid +
// glow) is intentionally identical to the auth family so all
// public-facing pages read as one. The doc-specific styles below
// (.doc, headings, body copy) are tuned for long-form reading on a
// dark surface — generous line-height, muted body text, neon used
// only for the status pill and link hovers so the policy reads as
// content rather than UI.
const PAGE_CSS = `
nav.site{position:sticky;top:0;z-index:100;background:rgba(11,13,18,0.85);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);padding:0 40px;height:60px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--db-gray-2)}
.nav-brand{display:flex;align-items:center;gap:10px;text-decoration:none}
.nav-brand .mark{width:28px;height:28px;border-radius:8px;box-shadow:0 0 12px rgba(63,255,0,0.40);display:block}
.nav-brand .name{font-family:var(--db-font-display);color:var(--db-gray-9);font-size:17px;font-weight:600;letter-spacing:-.02em}
.nav-login{color:var(--db-gray-7);font-size:13px;text-decoration:none;font-weight:500}
.nav-login:hover{color:var(--db-gray-9)}

.page{min-height:calc(100vh - 60px);min-height:calc(100dvh - 60px);display:flex;justify-content:center;padding:48px 24px 96px;position:relative;overflow:hidden;background:var(--db-bg);color:var(--db-gray-9);font-family:var(--db-font-body);-webkit-font-smoothing:antialiased}
.page-glow{position:absolute;inset:0;background:radial-gradient(ellipse 50% 40% at 50% 10%,var(--db-neon-glow-15),transparent 70%);pointer-events:none}
.page-grid{position:absolute;inset:0;background-image:linear-gradient(var(--db-gray-2) 1px,transparent 1px),linear-gradient(90deg,var(--db-gray-2) 1px,transparent 1px);background-size:48px 48px;-webkit-mask-image:radial-gradient(ellipse at 50% 20%,black 20%,transparent 60%);mask-image:radial-gradient(ellipse at 50% 20%,black 20%,transparent 60%);opacity:.4;pointer-events:none}

.doc{position:relative;width:100%;max-width:780px;background:var(--db-bg-elevated);border:1px solid var(--db-gray-3);border-radius:16px;padding:48px 56px 56px;box-shadow:0 24px 80px rgba(0,0,0,0.5)}
.doc-head{margin-bottom:24px}
.status-pill{display:inline-flex;align-items:center;gap:8px;padding:4px 10px;border:1px solid var(--db-gray-2);border-radius:999px;background:var(--db-bg-input);margin-bottom:16px}
.status-pill .dot{width:6px;height:6px;border-radius:999px;background:var(--db-neon);box-shadow:0 0 8px var(--db-neon)}
.status-pill .label{font-family:var(--db-font-mono);font-size:10px;color:var(--db-neon);letter-spacing:1.5px}

.doc h1{font-family:var(--db-font-display);font-size:34px;color:var(--db-gray-9);font-weight:600;letter-spacing:-.025em;margin:0 0 6px}
.doc .effective{color:var(--db-gray-6);font-family:var(--db-font-mono);font-size:12px;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}
.doc h2{font-family:var(--db-font-display);font-size:22px;color:var(--db-gray-9);font-weight:600;letter-spacing:-.015em;margin:36px 0 12px}
.doc h3{font-family:var(--db-font-display);font-size:15px;color:var(--db-gray-9);font-weight:600;letter-spacing:.2px;margin:22px 0 8px}
.doc p,.doc li{font-size:14.5px;line-height:1.7;color:var(--db-gray-8);margin:0 0 12px}
.doc ul{padding-left:22px;margin:0 0 12px}
.doc ul ul{padding-left:20px;margin-top:8px}
.doc strong{color:var(--db-gray-9);font-weight:600}
.doc a{color:var(--db-neon);text-decoration:none;border-bottom:1px solid transparent;transition:border-color .12s}
.doc a:hover{border-bottom-color:var(--db-neon)}
.doc .note{background:var(--db-bg-input);border-left:3px solid var(--db-neon);border-radius:8px;padding:14px 18px;font-size:13.5px;color:var(--db-gray-7);line-height:1.65;margin:24px 0 0}

@media (max-width:600px){
  nav.site{padding:0 16px;height:56px}
  .nav-brand .name{font-size:16px}
  .nav-login{font-size:12px}
  .page{padding:24px 14px 64px;min-height:calc(100vh - 56px);min-height:calc(100dvh - 56px)}
  .doc{padding:32px 22px 36px;border-radius:14px}
  .doc h1{font-size:26px}
  .doc h2{font-size:19px;margin-top:28px}
  .doc h3{font-size:14px}
}
`;
