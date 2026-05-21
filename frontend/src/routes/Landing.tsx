import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useCountUp } from "../lib/useCountUp";
import { useReveal, type RevealVariant } from "../lib/useReveal";

// Marketing landing page. Translated 1:1 from templates/landing.html
// (the legacy Jinja version still served at `/`). Always renders —
// signed-in visitors see the same marketing copy and can click
// "Sign in" to drop into their dashboard. Auto-redirecting based on
// a localStorage token caused a bug: stale/expired tokens decoded
// fine and bounced visitors to /dashboard, which then 401'd and
// kicked them straight to /login.
export default function Landing() {
  const [navOpen, setNavOpen] = useState(false);
  const heroRef = useHeroParallax();

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  const closeNav = () => setNavOpen(false);

  return (
    <>
      <style>{LANDING_CSS}</style>

      <nav className="site">
        <a href="/app/" className="nav-brand">
          <img className="mark" src="/static/brand-mark.svg" alt="" />
          <span className="name">DineroBook</span>
        </a>
        <button
          type="button"
          className="nav-toggle"
          aria-label="Toggle menu"
          onClick={() => setNavOpen((v) => !v)}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <div className={`nav-links${navOpen ? " open" : ""}`} onClick={(e) => {
          if ((e.target as HTMLElement).tagName === "A") closeNav();
        }}>
          <a href="#features">Product</a>
          <a href="#how">How it works</a>
          <a href="#pricing">Pricing</a>
          <Link to="/login">Sign in</Link>
          <Link to="/signup" className="nav-cta">Get started →</Link>
        </div>
      </nav>

      <section className="hero" ref={heroRef}>
        <div className="hero-grid hero-parallax-bg" aria-hidden="true" />
        <div className="hero-glow hero-parallax-glow" aria-hidden="true" />
        <div className="hero-inner">
          <div>
            <div className="eyebrow-pill"><span className="dot" />MSB TERMINAL · BUILT FOR SHOPS</div>
            <h1>The daily book<br />for money-service<br /><span className="accent">businesses.</span></h1>
            <p className="hero-p">Check cashing, money orders, wire transfers, bill pay — all your cash activity, tracked in one place. No more paper logs, no more mystery variances at the end of the month.</p>
            <div className="hero-ctas">
              <Link to="/signup" className="btn-primary">Start free trial →</Link>
              <a href="#features" className="btn-ghost">See how it works</a>
            </div>
            <div className="works-label">Works with</div>
            <div className="works-row">
              <span className="works-chip" style={{ color: "var(--db-co-intermex)", borderColor: "#1c3355" }}>Intermex</span>
              <span className="works-chip" style={{ color: "var(--db-co-maxi)", borderColor: "#331c55" }}>Maxi</span>
              <span className="works-chip" style={{ color: "var(--db-co-barri)", borderColor: "#134a55" }}>Barri</span>
              <span className="works-chip">Ria</span>
              <span className="works-chip">Western Union</span>
            </div>
          </div>
          <div className="hero-visual">
            <HeroVisual />
          </div>
        </div>
      </section>

      <RevealSection variant="fade-up"><FeaturesSection /></RevealSection>

      <AnimatedStatStrip />

      {/* "How it works": sticky-pinned headline on the left,
          steps scroll past on the right (OnePlus signature).
          On narrow viewports the CSS collapses back to a single
          column with the steps in normal stacking order. */}
      <section className="how" id="how">
        <div className="how-sticky-wrap">
          <div className="how-sticky-heading">
            <div className="section-eye">// HOW IT WORKS</div>
            <h2 className="section-heading">From paper to profitable<br /><span className="accent">in three steps.</span></h2>
            <p className="how-sticky-hint">Scroll to see each step ↓</p>
          </div>
          <div className="how-sticky-steps">
            <RevealSection variant="from-right">
              <div className="how-step"><div className="n">01</div><div className="t">Sign up</div><div className="b">Create your store in 60 seconds. No credit card, no sales call.</div><div className="arrow">→</div></div>
            </RevealSection>
            <RevealSection variant="from-right">
              <div className="how-step"><div className="n">02</div><div className="t">Log your day</div><div className="b">Cash in/out, money orders, check cashing, transfers. One screen, auto-saves.</div><div className="arrow">→</div></div>
            </RevealSection>
            <RevealSection variant="from-right">
              <div className="how-step"><div className="n">03</div><div className="t">Close the month</div><div className="b">P&L auto-populates. Export for your accountant. Spot variances before they bite.</div></div>
            </RevealSection>
          </div>
        </div>
      </section>

      <RevealSection variant="scale-up"><PricingSection /></RevealSection>

      <RevealSection variant="from-left">
        <section className="faq">
          <div className="faq-inner">
            <div className="section-eye">// QUESTIONS</div>
            <h2 className="faq-title-plain">Answered.</h2>
            {FAQS.map(([q, a], idx) => (
              <details className="faq-item" key={idx} open={idx === 0}>
                <summary>{q} <span className="plus">+</span></summary>
                <p>{a}</p>
              </details>
            ))}
          </div>
        </section>
      </RevealSection>

      <RevealSection variant="scale-up">
        <section className="cta-band">
          <div className="cta-glow" aria-hidden="true" />
          <div className="cta-inner">
            <div className="section-eye">// READY?</div>
            <h2 className="cta-title">Your first daily book<br />takes <span className="accent">ten minutes.</span></h2>
            <p className="cta-p">No credit card. 7-day Pro trial. Cancel anytime, keep your data.</p>
            <div className="cta-ctas">
              <Link to="/signup" className="btn-primary">Start free trial →</Link>
              <Link to="/login" className="btn-ghost">Sign in</Link>
            </div>
          </div>
        </section>
      </RevealSection>

      <footer className="site">
        <div className="foot-inner">
          <a href="/app/" className="nav-brand">
            <img className="mark" src="/static/brand-mark.svg" alt="" />
            <span className="name">DineroBook</span>
          </a>
          <div className="foot-copy">© 2026 · MSB Terminal · Made for shops that move fast.</div>
          <div className="foot-links">
            <a href="/privacy">Privacy</a>
            <Link to="/login">Sign in →</Link>
          </div>
        </div>
      </footer>
    </>
  );
}


/** Wrapper that fades / slides / scales its children in once they
 *  enter the viewport.  `variant` picks the entrance animation;
 *  the actual transition lives in LANDING_CSS so reduced-motion
 *  users see the static content immediately.
 *
 *  Variants (all transition over 700ms with a smooth cubic-bezier):
 *    - `fade-up`    (default) — opacity + translateY(40px)
 *    - `from-left`  — opacity + translateX(-48px)
 *    - `from-right` — opacity + translateX(+48px)
 *    - `scale-up`   — opacity + scale(0.94)
 *    - `blur`       — opacity + filter:blur(8px)
 */
function RevealSection({
  children, variant = "fade-up",
}: {
  children: React.ReactNode;
  variant?: RevealVariant;
}) {
  const { ref, revealed } = useReveal<HTMLDivElement>();
  return (
    <div
      ref={ref}
      className={`reveal reveal--${variant}${revealed ? " is-revealed" : ""}`}
    >
      {children}
    </div>
  );
}


/** Hero parallax: the hero-grid + hero-glow drift at a slower
 *  rate than the rest of the page as the user scrolls.  Creates
 *  a depth effect (OnePlus / Apple landing pattern) without
 *  needing a heavy library.
 *
 *  Implementation: single rAF-throttled scroll listener writes
 *  the current scroll-Y to a CSS variable on the hero section;
 *  the children read it via `translate3d(0, calc(var(--y) * Nx))`.
 *  Honors reduced-motion (no listener attached). */
function useHeroParallax(): React.RefObject<HTMLElement | null> {
  const ref = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (
      typeof window === "undefined"
      || (window.matchMedia
          && window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    ) {
      return;
    }
    let raf: number | null = null;
    const onScroll = () => {
      if (raf !== null) return;
      raf = requestAnimationFrame(() => {
        const el = ref.current;
        if (el) {
          el.style.setProperty("--scroll-y", `${window.scrollY}`);
        }
        raf = null;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (raf !== null) cancelAnimationFrame(raf);
    };
  }, []);
  return ref;
}


/** Stat strip with numbers that count up from zero as soon as the
 *  strip enters the viewport.  Each cell shares the `revealed`
 *  trigger from the same Intersection Observer so the four
 *  counters fire together in sync. */
function AnimatedStatStrip() {
  const { ref, revealed } = useReveal<HTMLElement>();
  const shops    = useCountUp(2400, { trigger: revealed });
  const dollars  = useCountUp(4.2,  { trigger: revealed });
  const closeMin = useCountUp(12,   { trigger: revealed });
  const uptime   = useCountUp(99.9, { trigger: revealed });
  return (
    <section ref={ref} className={`stat-strip reveal${revealed ? " is-revealed" : ""}`}>
      <div className="stat-strip-inner">
        <div className="stat-cell">
          <div className="stat-k">{Math.round(shops).toLocaleString()}+</div>
          <div className="stat-v">MSB shops using daily</div>
        </div>
        <div className="stat-cell">
          <div className="stat-k">${dollars.toFixed(1)}B</div>
          <div className="stat-v">transactions logged</div>
        </div>
        <div className="stat-cell">
          <div className="stat-k">{Math.round(closeMin)} min</div>
          <div className="stat-v">avg daily close time</div>
        </div>
        <div className="stat-cell">
          <div className="stat-k">{uptime.toFixed(1)}%</div>
          <div className="stat-v">uptime · 12 months</div>
        </div>
      </div>
    </section>
  );
}


const FAQS: Array<[string, string]> = [
  ["Do I need to switch from Intermex / Maxi / Barri?", "No. DineroBook sits on top of the companies you already use. You keep sending transfers through the same terminals — we just log and reconcile them for you."],
  ["Is my data safe?", "Yes. Bank-grade encryption at rest and in transit. Bank sync uses Stripe Financial Connections, which is read-only — we can never move money from your accounts."],
  ["What happens when my trial ends?", "You can choose Basic ($35/mo) or Pro ($45/mo). We keep your data for 180 days after cancellation so you can always come back and export."],
  ["Can my employees use it?", "Yes. Invite unlimited employees per store. They get a simplified view for logging daily activity without seeing financial summaries."],
  ["I run multiple stores. How does that work?", "One owner account, unlimited stores. Customers auto-sync across your store umbrella so a sender logged at store A autocompletes at store B."],
  ["Do you support QuickBooks / accountant export?", "Yes — CSV and PDF export on every report. Direct QuickBooks Online sync is on the roadmap."],
];


function PricingSection() {
  return (
    <section className="pricing" id="pricing">
      <div className="pricing-inner">
        <div className="section-eye">// PRICING</div>
        <h2 className="section-heading" style={{ marginBottom: 0 }}>One price. Per store.<br /><span className="accent">No surprises.</span></h2>
        <div className="pricing-grid">
          <div className="plan">
            <div className="plan-name">TRIAL</div>
            <div className="plan-price">$0</div>
            <div className="plan-period">7 days · full Pro access</div>
            <ul className="plan-feats">
              <li><span className="ck">✓</span> All Pro features</li>
              <li><span className="ck">✓</span> No credit card required</li>
              <li><span className="ck">✓</span> Instant access</li>
            </ul>
            <Link to="/signup" className="plan-btn ghost">Start free</Link>
          </div>
          <div className="plan">
            <div className="plan-name">BASIC</div>
            <div className="plan-price">$35<span className="suffix">/mo</span></div>
            <div className="plan-period">per store · monthly · or $350 / yr</div>
            <ul className="plan-feats">
              <li><span className="ck">✓</span> Daily books</li>
              <li><span className="ck">✓</span> Money transfer logging</li>
              <li><span className="ck">✓</span> ACH reconciliation</li>
              <li><span className="ck">✓</span> Monthly P&L</li>
              <li><span className="ck">✓</span> CSV / PDF export</li>
              <li><span className="ck">✓</span> Unlimited employees</li>
              <li className="x"><span className="xm">—</span> Bank sync</li>
            </ul>
            <Link to="/signup?plan=basic" className="plan-btn outline">Choose Basic</Link>
          </div>
          <div className="plan featured">
            <div className="plan-badge">MOST POPULAR</div>
            <div className="plan-name">PRO</div>
            <div className="plan-price">$45<span className="suffix">/mo</span></div>
            <div className="plan-period">or $420 / yr · 2 months free</div>
            <ul className="plan-feats">
              <li><span className="ck">✓</span> Everything in Basic</li>
              <li><span className="ck">✓</span> Live bank sync</li>
              <li><span className="ck">✓</span> Drift alerts</li>
              <li><span className="ck">✓</span> Multi-store umbrella</li>
              <li><span className="ck">✓</span> Priority support</li>
              <li><span className="ck">✓</span> Early access to new features</li>
            </ul>
            <Link to="/signup?plan=pro" className="plan-btn neon">Choose Pro →</Link>
          </div>
        </div>
        <div className="pricing-fine">All plans include unlimited transactions, unlimited customers, and 180-day data retention after cancellation.</div>
      </div>
    </section>
  );
}


function FeaturesSection() {
  return (
    <section className="features" id="features">
      <div className="features-inner">
        <div className="section-eye">// BUILT FOR MSB OWNERS</div>
        <h2 className="section-heading">Every part of the day,<br /><span className="accent">finally in one place.</span></h2>

        <div className="feat-row">
          <div>
            <div className="feat-num">01</div>
            <div className="feat-eye">THE DAILY BOOK</div>
            <h3 className="feat-title">Close your register in under 15 minutes.</h3>
            <p className="feat-body">One screen captures everything that moved through your store today — cash in, cash out, money orders, check cashing, sales. Auto-totals, auto-saves, auto-rolls-up into your monthly P&L.</p>
            <ul className="feat-ul">
              <li><span className="tick">✓</span> Cash in / cash out reconciliation</li>
              <li><span className="tick">✓</span> Money orders &amp; check cashing</li>
              <li><span className="tick">✓</span> Store sales &amp; other services</li>
              <li><span className="tick">✓</span> Notes for the unusual days</li>
            </ul>
          </div>
          <div className="mock">
            <div className="mock-head"><span className="mock-label">DAILY BOOK · MAR 14</span><span className="tag-ok">SAVED</span></div>
            <div className="mock-body">
              <div className="feat-eye" style={{ marginBottom: 10 }}>CASH FLOW</div>
              <div className="row-kv"><span className="k">Cash In</span><span className="v mono">$4,200.00</span></div>
              <div className="row-kv"><span className="k">Cash Out</span><span className="v mono">$3,850.00</span></div>
              <div className="row-kv"><span className="k">Net</span><span className="v mono pos">+$350.00</span></div>
              <div className="mock-label" style={{ margin: "20px 0 10px" }}>SALES &amp; SERVICES</div>
              <div className="row-kv"><span className="k">Store sales</span><span className="v mono">$620.00</span></div>
              <div className="row-kv"><span className="k">Money orders</span><span className="v mono">$1,100.00</span></div>
              <div className="row-kv"><span className="k">Check cashing</span><span className="v mono">$280.00</span></div>
            </div>
          </div>
        </div>

        <div className="feat-row reverse">
          <div>
            <div className="feat-num">02</div>
            <div className="feat-eye">MONEY TRANSFERS</div>
            <h3 className="feat-title">Every wire, logged. Every customer, remembered.</h3>
            <p className="feat-body">Intermex, Maxi, Barri, Ria, Western Union — one form, full sender and recipient detail, fee and federal tax broken out correctly. Customers auto-complete across your entire store umbrella.</p>
            <ul className="feat-ul">
              <li><span className="tick">✓</span> Sender phone autocomplete across sibling stores</li>
              <li><span className="tick">✓</span> Fee vs federal tax separated automatically</li>
              <li><span className="tick">✓</span> Full transfer history, searchable</li>
              <li><span className="tick">✓</span> Status tracking: Sent · Pending · Canceled</li>
            </ul>
          </div>
          <div className="mock">
            <div className="mock-head"><span className="mock-label">TRANSFERS · TODAY</span><span className="tag-neutral">5 logged</span></div>
            <div>
              <TransfersMockRow time="03/14 14:22" name="Maria Gonzalez" co="Inter" coVar="--db-co-intermex" amount="$450.00" status="ok" />
              <TransfersMockRow time="03/14 13:08" name="Luis Vargas" co="Maxi" coVar="--db-co-maxi" amount="$1,200.00" status="pending" />
              <TransfersMockRow time="03/14 11:45" name="Ana Ramirez" co="Barri" coVar="--db-co-barri" amount="$85.00" status="ok" />
              <TransfersMockRow time="03/14 10:12" name="Sofia Reyes" co="Maxi" coVar="--db-co-maxi" amount="$550.00" status="ok" />
              <TransfersMockRow time="03/14 09:30" name="Diego Flores" co="Inter" coVar="--db-co-intermex" amount="$180.00" status="ok" last />
            </div>
          </div>
        </div>

        <div className="feat-row">
          <div>
            <div className="feat-num">03</div>
            <div className="feat-eye">ACH RECONCILIATION</div>
            <h3 className="feat-title">Spot variances before the month ends.</h3>
            <p className="feat-body">Your ACH batch from Intermex doesn't match what you logged? DineroBook flags it the day it happens — not three weeks later when you're already chasing ghosts.</p>
            <ul className="feat-ul">
              <li><span className="tick">✓</span> Auto-match batches to transfer totals</li>
              <li><span className="tick">✓</span> Variance alerts on day-one</li>
              <li><span className="tick">✓</span> Clear / partial / disputed statuses</li>
              <li><span className="tick">✓</span> One-click drill-down to underlying transfers</li>
            </ul>
          </div>
          <div className="mock">
            <div className="mock-head"><span className="mock-label">ACH BATCH · MAR 12</span><span className="tag-bad">VARIANCE</span></div>
            <div className="mock-body">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
                <div>
                  <div className="mock-label" style={{ marginBottom: 6 }}>YOUR LOG</div>
                  <div className="mono" style={{ fontSize: 24, color: "var(--db-gray-9)", fontWeight: 500 }}>$6,420.00</div>
                  <div className="mono" style={{ fontSize: 11, color: "var(--db-gray-7)", marginTop: 4 }}>14 transfers</div>
                </div>
                <div>
                  <div className="mock-label" style={{ marginBottom: 6 }}>BATCH RECEIVED</div>
                  <div className="mono" style={{ fontSize: 24, color: "var(--db-gray-9)", fontWeight: 500 }}>$6,398.00</div>
                  <div className="mono" style={{ fontSize: 11, color: "var(--db-gray-7)", marginTop: 4 }}>Intermex</div>
                </div>
              </div>
              <div style={{ background: "rgba(255,77,109,.08)", border: "1px solid rgba(255,77,109,.3)", borderRadius: 10, padding: "12px 14px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontSize: 12, color: "var(--db-negative)", fontWeight: 600 }}>Variance detected</div>
                  <div style={{ fontSize: 11, color: "var(--db-gray-7)", marginTop: 2 }}>$22.00 short · 1 transfer missing</div>
                </div>
                <span className="mono" style={{ fontSize: 18, color: "var(--db-negative)" }}>−$22.00</span>
              </div>
            </div>
          </div>
        </div>

        <div className="feat-row reverse">
          <div>
            <div className="feat-num">04</div>
            <div className="feat-eye">MONTHLY P&amp;L</div>
            <h3 className="feat-title">Know exactly what you made last month.</h3>
            <p className="feat-body">Auto-populated from your daily books and transfer ledger. Revenue by service line, fees collected, money-order margins, store sales — no spreadsheets required.</p>
            <ul className="feat-ul">
              <li><span className="tick">✓</span> Revenue split by service</li>
              <li><span className="tick">✓</span> Fee income vs federal tax pass-through</li>
              <li><span className="tick">✓</span> YoY comparison</li>
              <li><span className="tick">✓</span> CSV / PDF export for your accountant</li>
            </ul>
          </div>
          <div className="mock">
            <div className="mock-head"><span className="mock-label">P&amp;L · MARCH 2026</span><span className="tag-neutral">AUTO-SYNCED</span></div>
            <div className="mock-body">
              <PLBars />
              <div style={{ display: "flex", justifyContent: "space-between", padding: "16px 0 0", marginTop: 10, borderTop: "1px solid var(--db-gray-3)" }}>
                <span style={{ color: "var(--db-gray-9)", fontWeight: 600, fontSize: 13 }}>Net income</span>
                <span className="mono" style={{ color: "var(--db-neon)", fontWeight: 600, fontSize: 18 }}>+$2,480</span>
              </div>
            </div>
          </div>
        </div>

        <div className="feat-row">
          <div>
            <div className="feat-num">05</div>
            <div className="feat-eye">BANK SYNC · PRO</div>
            <h3 className="feat-title">Live bank balances, alongside your books.</h3>
            <p className="feat-body">Connect via Stripe Financial Connections. Your real bank balance sits next to your book balance — the moment they drift, you know.</p>
            <ul className="feat-ul">
              <li><span className="tick">✓</span> Multi-bank support</li>
              <li><span className="tick">✓</span> Read-only · bank-grade security</li>
              <li><span className="tick">✓</span> Daily auto-refresh</li>
              <li><span className="tick">✓</span> Drift alerts when books ≠ bank</li>
            </ul>
          </div>
          <div className="mock">
            <div className="mock-head">
              <span className="mock-label">BANK SYNC · LIVE</span>
              <span className="mono" style={{ fontSize: 10, color: "var(--db-neon)", display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 6, height: 6, borderRadius: 999, background: "var(--db-neon)", boxShadow: "0 0 8px var(--db-neon)" }} />CONNECTED
              </span>
            </div>
            <div className="mock-body">
              <BankRow name="Chase · Operating" sub="book $28,410.00 · bank $28,432.00" amount="$28,432" status="matched" />
              <BankRow name="BofA · Deposits" sub="book $12,080.00 · bank $12,080.00" amount="$12,080" status="matched" />
              <BankRow name="Wells · Reserve" sub="book $5,200.00 · bank $5,180.00" amount="$5,180" status="drift" driftLabel="△ $20 drift" />
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}


function TransfersMockRow({
  time, name, co, coVar, amount, status, last,
}: {
  time: string; name: string; co: string; coVar: string; amount: string;
  status: "ok" | "pending"; last?: boolean;
}) {
  return (
    <div className={`tf-row${last ? " last" : ""}`}>
      <span className="mono" style={{ color: "var(--db-gray-6)", fontSize: 11 }}>{time}</span>
      <span>{name}</span>
      <span style={{ color: `var(${coVar})`, fontWeight: 600, fontSize: 12 }}>{co}</span>
      <span className="mono" style={{ textAlign: "right" }}>{amount}</span>
      <span className={status === "ok" ? "pill-ok" : "pill-pending"}>● {status === "ok" ? "sent" : "pending"}</span>
    </div>
  );
}


function PLBars() {
  const rows: Array<[string, number]> = [
    ["Transfer fees", 3420],
    ["Check cashing", 2180],
    ["Money order margin", 960],
    ["Store sales", 1840],
    ["— Rent", -2400],
    ["— Utilities", -320],
    ["— Payroll", -3200],
  ];
  return (
    <>
      {rows.map(([label, amt]) => {
        const neg = amt < 0;
        const pct = Math.floor((Math.abs(amt) * 100) / 3420);
        return (
          <div className="pl-row" key={label}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 4 }}>
              <span style={{ color: "var(--db-gray-8)" }}>{label}</span>
              <span className="mono" style={{ color: neg ? "var(--db-negative)" : "var(--db-neon)" }}>
                {neg ? "" : "+"}${Math.abs(amt).toLocaleString()}
              </span>
            </div>
            <div className={`pl-bar${neg ? " neg" : ""}`}><span style={{ width: `${pct}%` }} /></div>
          </div>
        );
      })}
    </>
  );
}


function BankRow({
  name, sub, amount, status, driftLabel,
}: {
  name: string; sub: string; amount: string;
  status: "matched" | "drift"; driftLabel?: string;
}) {
  const tone = status === "matched" ? "var(--db-neon)" : "var(--db-negative)";
  return (
    <div className="bank-row">
      <div>
        <div style={{ fontSize: 13, color: "var(--db-gray-9)", fontWeight: 500 }}>{name}</div>
        <div className="mono" style={{ fontSize: 11, color: "var(--db-gray-7)", marginTop: 3 }}>{sub}</div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="mono" style={{ fontSize: 18, color: "var(--db-gray-9)", fontWeight: 500 }}>{amount}</div>
        <div className="mono" style={{ fontSize: 10, color: tone, marginTop: 3 }}>
          {status === "matched" ? "● matched" : driftLabel || "● drift"}
        </div>
      </div>
    </div>
  );
}


function HeroVisual() {
  return (
    <svg viewBox="0 0 560 450" aria-hidden="true">
      <defs>
        <linearGradient id="pane" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#161920" /><stop offset="1" stopColor="#0e1117" /></linearGradient>
        <linearGradient id="paneHi" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#1c202a" /><stop offset="1" stopColor="#11141b" /></linearGradient>
        <filter id="neonglow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      <ellipse cx="280" cy="410" rx="200" ry="22" fill="#3fff00" opacity=".15" filter="url(#neonglow)" />
      <g>
        <path d="M 130 80 L 420 40 L 540 80 L 250 120 Z" fill="url(#paneHi)" stroke="#272c38" />
        <path d="M 130 80 L 250 120 L 250 170 L 130 130 Z" fill="#0b0d12" stroke="#272c38" />
        <path d="M 540 80 L 250 120 L 250 170 L 540 130 Z" fill="url(#pane)" stroke="#272c38" />
        <g transform="translate(270,70)">
          <rect x="0" y="10" width="18" height="26" fill="#3fff00" opacity=".35" transform="skewY(18)" />
          <rect x="30" y="4" width="18" height="32" fill="#3fff00" opacity=".55" transform="skewY(18)" />
          <rect x="60" y="-4" width="18" height="40" fill="#3fff00" opacity=".8" transform="skewY(18)" />
          <rect x="90" y="-12" width="18" height="48" fill="#3fff00" transform="skewY(18)" filter="url(#neonglow)" />
          <rect x="120" y="-8" width="18" height="44" fill="#3fff00" opacity=".9" transform="skewY(18)" />
          <rect x="150" y="-14" width="18" height="50" fill="#3fff00" filter="url(#neonglow)" transform="skewY(18)" />
          <rect x="180" y="-20" width="18" height="56" fill="#3fff00" transform="skewY(18)" filter="url(#neonglow)" />
        </g>
        <text x="145" y="98" fill="#9199a8" fontSize="11" fontFamily="JetBrains Mono">MONTHLY P&amp;L</text>
      </g>
      <g transform="translate(-20,80)">
        <path d="M 110 140 L 400 95 L 520 135 L 230 180 Z" fill="url(#paneHi)" stroke="#363c4a" />
        <path d="M 110 140 L 230 180 L 230 240 L 110 200 Z" fill="#0b0d12" stroke="#272c38" />
        <path d="M 520 135 L 230 180 L 230 240 L 520 195 Z" fill="url(#pane)" stroke="#363c4a" />
        <g transform="translate(245,130)" fontFamily="JetBrains Mono" fontSize="9" fill="#c4cad6">
          <g transform="skewY(-9)">
            <rect x="0" y="0" width="245" height="10" fill="#0b0d12" />
            <text x="4" y="8" fill="#9199a8">DATE · SENDER · CO · AMT</text>
            <rect x="0" y="14" width="245" height="9" fill="#11141b" />
            <text x="4" y="21">03/14 Gonzalez Inter $450</text>
            <rect x="0" y="25" width="245" height="9" fill="#0e1117" />
            <text x="4" y="32">03/14 Vargas Maxi $1,200</text>
            <rect x="0" y="36" width="245" height="9" fill="#11141b" />
            <text x="4" y="43">03/13 Ramirez Barri $85</text>
            <rect x="0" y="47" width="245" height="9" fill="#0e1117" />
            <text x="4" y="54" fill="#3fff00">+ 142 more</text>
          </g>
        </g>
      </g>
      <g transform="translate(0,170)">
        <path d="M 80 200 L 380 155 L 500 195 L 200 240 Z" fill="url(#paneHi)" stroke="#3fff00" strokeWidth="1" opacity=".95" />
        <path d="M 80 200 L 200 240 L 200 300 L 80 260 Z" fill="#0b0d12" stroke="#3fff00" strokeWidth="1" />
        <path d="M 500 195 L 200 240 L 200 300 L 500 255 Z" fill="url(#pane)" stroke="#3fff00" strokeWidth="1" />
        <g transform="translate(215,190)">
          <g transform="skewY(-9)">
            <text x="0" y="8" fontFamily="JetBrains Mono" fontSize="9" fill="#9199a8">DAILY BOOK · MAR 14</text>
            <rect x="0" y="16" width="130" height="14" fill="#0b0d12" stroke="#272c38" />
            <text x="6" y="26" fontFamily="JetBrains Mono" fontSize="10" fill="#e5e7eb">CASH IN  $4,200.00</text>
            <rect x="140" y="16" width="130" height="14" fill="#0b0d12" stroke="#272c38" />
            <text x="146" y="26" fontFamily="JetBrains Mono" fontSize="10" fill="#e5e7eb">CASH OUT $3,850.00</text>
            <rect x="0" y="36" width="270" height="14" fill="#0b0d12" stroke="#3fff00" />
            <text x="6" y="46" fontFamily="JetBrains Mono" fontSize="10" fill="#3fff00">NET      +$350.00</text>
          </g>
        </g>
      </g>
      <g transform="translate(440,20)" filter="url(#neonglow)">
        <rect x="0" y="0" width="60" height="60" rx="14" fill="#0b0d12" stroke="#3fff00" strokeWidth="1.5" />
        <text x="30" y="44" textAnchor="middle" fontFamily="Space Grotesk" fontSize="38" fontWeight="700" fill="#3fff00">$</text>
      </g>
      <g transform="translate(20,300)" filter="url(#neonglow)">
        <circle cx="26" cy="26" r="22" fill="#0b0d12" stroke="#3fff00" strokeWidth="1.5" />
        <path d="M 16 27 l 7 7 l 13 -15" stroke="#3fff00" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </svg>
  );
}


// All page-local CSS, lifted verbatim from templates/landing.html so
// the visual diff against the legacy page stays at zero. Tokens
// (`--db-*`) come from the global static/design-tokens.css already
// imported by frontend/index.html.
const LANDING_CSS = `
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{font-family:var(--db-font-body);background:var(--db-bg);color:var(--db-gray-9);-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
a{color:inherit}
::selection{background:var(--db-neon);color:var(--db-neon-ink)}

/* ── Scroll-reveal animation (OnePlus-style fade + slide up
   as sections enter viewport).  Driven by the useReveal hook
   in src/lib/useReveal.ts; this CSS only owns the transition
   between states.  Reduced-motion users get .is-revealed
   set immediately by the hook so they see the static content
   with no transition.

   Variants: fade-up (default), from-left, from-right,
   scale-up, blur.  Pick per-section via the variant prop on
   the RevealSection wrapper; mixing variants keeps a long
   scroll from feeling monotonous (every section moving
   identically reads as a slideshow, not a product page).
   ───────────────────────────────────────────────────────── */
.reveal{
  opacity:0;
  transition:opacity 700ms cubic-bezier(0.22, 1, 0.36, 1),
             transform 700ms cubic-bezier(0.22, 1, 0.36, 1),
             filter 700ms cubic-bezier(0.22, 1, 0.36, 1);
  will-change:opacity,transform;
}
.reveal--fade-up{transform:translateY(40px)}
.reveal--from-left{transform:translateX(-48px)}
.reveal--from-right{transform:translateX(48px)}
.reveal--scale-up{transform:scale(0.94)}
.reveal--blur{filter:blur(8px)}

.reveal.is-revealed{
  opacity:1;
  transform:translate(0) scale(1);
  filter:none;
}

/* ── Hero parallax ────────────────────────────────────────
   The hero section sets a --scroll-y CSS variable from a
   rAF-throttled scroll listener (useHeroParallax in
   Landing.tsx).  The grid
   pattern + the glow halo translate at fractional rates of
   the scroll so they drift behind the foreground content,
   creating a depth effect.  Multipliers are tiny (0.15 +
   0.25) — enough to feel alive, not enough to obscure the
   text.

   Reduced-motion users get no listener attached (the hook
   bails on mount); --scroll-y stays unset so the transforms
   collapse to 0px. */
.hero{--scroll-y:0}
.hero-parallax-bg{
  transform:translate3d(0, calc(var(--scroll-y) * 0.15px), 0);
  will-change:transform;
}
.hero-parallax-glow{
  transform:translate3d(0, calc(var(--scroll-y) * 0.25px), 0);
  will-change:transform;
}

/* ── Sticky-pinned "How it works" (OnePlus signature) ──────
   Two-column layout: the headline column sticks to a position
   below the nav while the steps column scrolls past.  Each
   step uses the from-right reveal variant so it slides in as
   it enters the viewport.

   On narrow viewports (<=900px) the grid collapses to single
   column + the heading goes back to normal flow — sticky is
   awkward on phones where the viewport is already short. */
.how{padding-top:60px;padding-bottom:60px}
.how-sticky-wrap{
  max-width:1200px;
  margin:0 auto;
  padding:0 48px;
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:80px;
  align-items:start;
}
.how-sticky-heading{
  position:sticky;
  /* Below the 64px sticky nav with a 32px breathing margin. */
  top:96px;
  align-self:start;
}
.how-sticky-heading .section-eye{margin-bottom:18px}
.how-sticky-heading .section-heading{margin-bottom:24px}
.how-sticky-hint{
  font-family:var(--db-font-mono);
  font-size:12px;
  color:var(--db-gray-6);
  letter-spacing:.06em;
  text-transform:uppercase;
  margin-top:24px;
}
.how-sticky-steps{
  display:flex;
  flex-direction:column;
  gap:32px;
}
.how-sticky-steps .how-step{margin-bottom:0}

@media (max-width:900px){
  .how-sticky-wrap{
    grid-template-columns:1fr;
    gap:32px;
    padding:0 24px;
  }
  .how-sticky-heading{
    position:static;
    top:auto;
  }
  .how-sticky-hint{display:none}
}

/* ── Scroll-snap (proximity, not mandatory) ────────────────
   proximity is the gentler flavor: the browser nudges scroll
   to the nearest snap point IF the user is near one, but
   doesn't fight them mid-scroll the way mandatory would.
   Result: sections gently align without the page feeling
   locked.

   Skip on touch devices (the hover: hover + pointer: fine
   media query) since iOS Safari snap interferes with momentum
   scrolling.  And of course strip entirely under reduced
   motion. */
@media (hover: hover) and (pointer: fine){
  html{scroll-snap-type:y proximity;scroll-padding-top:80px}
  .hero, .stat-strip, .how, .pricing, .faq, .cta-band{
    scroll-snap-align:start;
    scroll-snap-stop:normal;
  }
}

/* Stat strip's stat cells get a tiny stagger so the four
   numbers don't all fly in at the exact same instant.
   The .is-revealed nth-child rules below delay each cell
   without per-cell JS. */
.reveal.is-revealed .stat-strip-inner .stat-cell{
  transition:transform 600ms cubic-bezier(0.22, 1, 0.36, 1),
             opacity 600ms cubic-bezier(0.22, 1, 0.36, 1);
}

/* "How it works" steps stagger in too — gives a nice cascade
   effect as the section reveals. */
.reveal .how-step{
  opacity:0;transform:translateY(20px);
  transition:opacity 500ms cubic-bezier(0.22, 1, 0.36, 1),
             transform 500ms cubic-bezier(0.22, 1, 0.36, 1);
}
.reveal.is-revealed .how-step:nth-child(1){opacity:1;transform:translateY(0);transition-delay:80ms}
.reveal.is-revealed .how-step:nth-child(2){opacity:1;transform:translateY(0);transition-delay:200ms}
.reveal.is-revealed .how-step:nth-child(3){opacity:1;transform:translateY(0);transition-delay:320ms}

/* Hero glow: gentle breathing animation so the page feels
   alive even before the user scrolls.  ≤8s cycle keeps it
   from being distracting; 0.92→1.0 opacity range stays subtle. */
@keyframes db-hero-glow-pulse{
  0%,100%{opacity:.92;transform:scale(1)}
  50%{opacity:1;transform:scale(1.04)}
}
.hero-glow{
  animation:db-hero-glow-pulse 7s ease-in-out infinite;
  transform-origin:center;
  will-change:opacity,transform;
}

/* How-step + faq cards: lift on hover — same vocabulary as
   the kit's interactive cards.  Marketing pages can afford
   a more pronounced lift than the app chrome. */
.how-step{
  transition:transform 200ms cubic-bezier(0.22, 1, 0.36, 1),
             border-color 200ms ease,
             box-shadow 200ms ease;
}
.how-step:hover{
  transform:translateY(-4px);
  border-color:var(--db-neon-glow-40, rgba(63,255,0,0.4));
  box-shadow:0 12px 32px rgba(0,0,0,0.4);
}

/* Honor prefers-reduced-motion globally for this page so
   scroll-driven motion + the hero pulse + hover lifts + the
   parallax + the scroll-snap all collapse to instant /
   static behavior. */
@media (prefers-reduced-motion: reduce){
  .reveal,.reveal.is-revealed,.reveal .how-step,
  .reveal.is-revealed .how-step,
  .reveal--fade-up,.reveal--from-left,.reveal--from-right,
  .reveal--scale-up,.reveal--blur{
    opacity:1!important;
    transform:none!important;
    filter:none!important;
    transition:none!important;
    animation:none!important;
  }
  .hero-glow{animation:none!important}
  .hero-parallax-bg,.hero-parallax-glow{transform:none!important}
  .how-step{transition:none!important}
  .how-step:hover{transform:none!important}
  html{scroll-snap-type:none!important}
}

nav.site{position:sticky;top:0;z-index:100;background:rgba(11,13,18,0.82);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);padding:0 48px;height:64px;display:flex;align-items:center;gap:20px;border-bottom:1px solid var(--db-gray-2)}
.nav-brand{display:flex;align-items:center;gap:10px;text-decoration:none}
.nav-brand .mark{width:28px;height:28px;border-radius:8px;box-shadow:0 0 12px rgba(63,255,0,0.40);display:block}
.nav-brand .name{font-family:var(--db-font-display);color:var(--db-gray-9);font-size:17px;font-weight:600;letter-spacing:-.02em}
.nav-links{margin-left:auto;display:flex;align-items:center;gap:26px}
.nav-links a{color:var(--db-gray-7);text-decoration:none;font-size:13px;font-weight:500;transition:color .12s}
.nav-links a:hover{color:var(--db-gray-9)}
/* Specificity bumped to .nav-links a.nav-cta (0,2,1) so the dark
   neon-ink wins over the gray inherited from .nav-links a (0,1,1).
   Same fix is applied to :hover. */
.nav-links a.nav-cta{background:var(--db-neon);color:var(--db-neon-ink);padding:9px 18px;border-radius:10px;font-weight:600;font-size:13px;text-decoration:none;letter-spacing:-.01em}
.nav-links a.nav-cta:hover{background:var(--db-neon-bright);color:var(--db-neon-ink)}
.nav-toggle{display:none;background:transparent;border:1px solid var(--db-gray-3);border-radius:8px;width:34px;height:34px;color:var(--db-gray-7);cursor:pointer;align-items:center;justify-content:center;margin-left:auto}

.hero{position:relative;overflow:hidden;padding:80px 48px 96px;border-bottom:1px solid var(--db-gray-2)}
.hero-grid{position:absolute;inset:0;background-image:linear-gradient(var(--db-gray-2) 1px,transparent 1px),linear-gradient(90deg,var(--db-gray-2) 1px,transparent 1px);background-size:48px 48px;-webkit-mask-image:radial-gradient(ellipse at center,black 30%,transparent 75%);mask-image:radial-gradient(ellipse at center,black 30%,transparent 75%);opacity:.5;pointer-events:none}
.hero-glow{position:absolute;top:40%;right:12%;width:440px;height:440px;background:radial-gradient(circle,var(--db-neon-glow-25),transparent 60%);pointer-events:none}
.hero-inner{position:relative;max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1.05fr 1fr;gap:60px;align-items:center}
.eyebrow-pill{display:inline-flex;align-items:center;gap:10px;padding:5px 12px;border:1px solid rgba(63,255,0,.3);border-radius:999px;background:var(--db-neon-glow-8);font-family:var(--db-font-mono);font-size:11px;font-weight:500;color:var(--db-neon);letter-spacing:2px;text-transform:uppercase;margin-bottom:26px}
.eyebrow-pill .dot{width:6px;height:6px;border-radius:999px;background:var(--db-neon);box-shadow:0 0 8px var(--db-neon)}
.hero h1{font-family:var(--db-font-display);font-size:60px;line-height:1.02;letter-spacing:-.035em;font-weight:700;margin-bottom:22px;color:var(--db-gray-9)}
.hero h1 .accent{color:var(--db-neon)}
.hero-p{font-size:17px;color:var(--db-gray-7);line-height:1.6;max-width:500px;margin-bottom:32px}
.hero-ctas{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:40px}
.btn-primary{background:var(--db-neon);color:var(--db-neon-ink);padding:14px 28px;border-radius:12px;font-weight:600;font-size:14.5px;text-decoration:none;letter-spacing:-.01em;box-shadow:0 0 0 1px var(--db-neon),0 0 32px var(--db-neon-glow-40);transition:background .12s}
.btn-primary:hover{background:var(--db-neon-bright)}
.btn-ghost{background:transparent;color:var(--db-gray-9);border:1px solid var(--db-gray-4);padding:14px 24px;border-radius:12px;font-weight:500;font-size:14.5px;text-decoration:none;transition:border-color .12s,background .12s}
.btn-ghost:hover{border-color:var(--db-gray-6);background:rgba(255,255,255,0.03)}
.works-label{font-family:var(--db-font-mono);font-size:10px;color:var(--db-gray-6);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:12px}
.works-row{display:flex;gap:8px;flex-wrap:wrap}
.works-chip{padding:6px 12px;border:1px solid var(--db-gray-3);border-radius:999px;font-size:12px;font-weight:500;background:var(--db-bg-input)}

.hero-visual{position:relative;aspect-ratio:1.25/1;max-width:560px;margin:0 auto;width:100%}
.hero-visual svg{width:100%;height:100%;overflow:visible}

.how{padding:96px 48px;background:var(--db-bg);border-top:1px solid var(--db-gray-2)}
.how-inner{max-width:1100px;margin:0 auto}
.how-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;position:relative}
.how-step{padding:32px 28px;background:var(--db-bg-elevated);border:1px solid var(--db-gray-3);border-radius:16px;position:relative}
.how-step .n{font-family:var(--db-font-mono);font-size:13px;font-weight:600;color:var(--db-neon);letter-spacing:1.5px;margin-bottom:16px}
.how-step .t{font-family:var(--db-font-display);font-size:22px;color:var(--db-gray-9);font-weight:600;margin-bottom:8px;letter-spacing:-.02em}
.how-step .b{font-size:14px;color:var(--db-gray-7);line-height:1.55}
.how-step .arrow{position:absolute;right:-20px;top:50%;transform:translateY(-50%);color:var(--db-neon);font-size:24px;background:var(--db-bg);padding:0 8px;z-index:1}
@media(max-width:900px){.how{padding:72px 20px}.how-grid{grid-template-columns:1fr;gap:16px}.how-step .arrow{display:none}}

.pricing{padding:96px 48px;background:var(--db-bg);border-top:1px solid var(--db-gray-2)}
.pricing-inner{max-width:1100px;margin:0 auto}
.pricing-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;align-items:stretch;margin-top:56px}
.plan{background:var(--db-bg-elevated);border:1px solid var(--db-gray-3);border-radius:16px;padding:32px 28px;position:relative;display:flex;flex-direction:column}
.plan.featured{border-color:var(--db-neon);background:var(--db-bg-raised);box-shadow:0 0 0 1px var(--db-neon),0 0 48px var(--db-neon-glow-15)}
.plan-badge{position:absolute;top:-11px;left:24px;background:var(--db-neon);color:var(--db-neon-ink);font-size:10px;font-weight:700;letter-spacing:1.5px;padding:3px 12px;border-radius:4px;font-family:var(--db-font-mono)}
.plan-name{font-family:var(--db-font-mono);font-size:11px;font-weight:500;color:var(--db-gray-7);letter-spacing:2px;margin-bottom:14px}
.plan-price{font-family:var(--db-font-display);font-size:52px;font-weight:700;line-height:1;margin-bottom:4px;color:var(--db-gray-9);letter-spacing:-.04em}
.plan-price .suffix{font-size:20px;color:var(--db-gray-6);font-weight:400}
.plan-period{font-size:13px;margin-bottom:24px;color:var(--db-gray-7)}
.plan-feats{list-style:none;padding:0;margin-bottom:24px;flex:1}
.plan-feats li{font-size:13.5px;padding:8px 0;color:var(--db-gray-8);display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--db-gray-2)}
.plan-feats li.x{color:var(--db-gray-5)}
.plan-feats li .ck{color:var(--db-neon);font-weight:600;font-size:14px}
.plan-feats li .xm{color:var(--db-gray-4)}
.plan-btn{display:block;text-align:center;padding:13px 18px;border-radius:10px;font-size:14px;font-weight:600;text-decoration:none;letter-spacing:-.01em;border:none;cursor:pointer;width:100%;font-family:inherit}
.plan-btn.ghost{background:var(--db-bg-popover);color:var(--db-gray-9)}
.plan-btn.outline{background:transparent;color:var(--db-gray-9);border:1px solid var(--db-gray-4)}
.plan-btn.neon{background:var(--db-neon);color:var(--db-neon-ink);box-shadow:0 0 0 1px var(--db-neon),0 0 24px var(--db-neon-glow-25)}
.plan-btn.neon:hover{background:var(--db-neon-bright)}
.pricing-fine{text-align:center;margin-top:32px;font-size:13px;color:var(--db-gray-6)}
@media(max-width:900px){.pricing{padding:72px 20px}.pricing-grid{grid-template-columns:1fr}}

.faq{padding:96px 48px;background:var(--db-bg);border-top:1px solid var(--db-gray-2)}
.faq-inner{max-width:820px;margin:0 auto}
.faq-title-plain{font-family:var(--db-font-display);font-size:44px;color:var(--db-gray-9);font-weight:600;letter-spacing:-.03em;line-height:1.1;text-align:center;margin-bottom:48px}
.faq-item{border-bottom:1px solid var(--db-gray-2);padding:20px 0;cursor:pointer}
.faq-item summary{list-style:none;display:flex;justify-content:space-between;align-items:center;font-size:16px;color:var(--db-gray-9);font-weight:500;gap:20px}
.faq-item summary::-webkit-details-marker{display:none}
.faq-item .plus{font-size:22px;font-weight:300;color:var(--db-gray-7);transition:transform .2s,color .2s;flex-shrink:0}
.faq-item[open] .plus{transform:rotate(45deg);color:var(--db-neon)}
.faq-item p{margin-top:12px;font-size:14.5px;color:var(--db-gray-7);line-height:1.6;max-width:700px}
@media(max-width:900px){.faq{padding:72px 20px}.faq-title-plain{font-size:32px}}

.cta-band{padding:120px 48px;background:var(--db-bg);position:relative;overflow:hidden;border-top:1px solid var(--db-gray-2)}
.cta-glow{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:600px;height:600px;background:radial-gradient(circle,var(--db-neon-glow-25),transparent 60%);pointer-events:none}
.cta-inner{max-width:800px;margin:0 auto;text-align:center;position:relative}
.cta-title{font-family:var(--db-font-display);font-size:60px;color:var(--db-gray-9);font-weight:700;letter-spacing:-.035em;line-height:1.05;margin-bottom:22px}
.cta-title .accent{color:var(--db-neon)}
.cta-p{font-size:17px;color:var(--db-gray-7);margin-bottom:36px}
.cta-ctas{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
@media(max-width:900px){.cta-band{padding:72px 20px}.cta-title{font-size:38px}}

.features{padding:120px 48px;background:var(--db-bg)}
.features-inner{max-width:1200px;margin:0 auto}
.section-eye{font-family:var(--db-font-mono);font-size:11px;color:var(--db-neon);letter-spacing:2px;text-transform:uppercase;margin-bottom:18px;font-weight:500;text-align:center}
.section-heading{font-family:var(--db-font-display);font-size:48px;color:var(--db-gray-9);font-weight:600;letter-spacing:-.03em;line-height:1.1;text-align:center;margin-bottom:96px}
.section-heading .accent{color:var(--db-neon)}
.feat-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:80px;align-items:center;margin-bottom:120px}
.feat-row.reverse{direction:rtl}
.feat-row.reverse > *{direction:ltr}
.feat-num{font-family:var(--db-font-display);font-size:88px;font-weight:700;color:var(--db-gray-2);letter-spacing:-.04em;line-height:1;margin-bottom:6px}
.feat-eye{font-family:var(--db-font-mono);font-size:11px;color:var(--db-neon);letter-spacing:2px;text-transform:uppercase;margin-bottom:16px;font-weight:500}
.feat-title{font-family:var(--db-font-display);font-size:38px;color:var(--db-gray-9);font-weight:600;letter-spacing:-.025em;line-height:1.1;margin-bottom:20px}
.feat-body{font-size:16px;color:var(--db-gray-7);line-height:1.6;margin-bottom:22px}
.feat-ul{list-style:none;padding:0;margin:0}
.feat-ul li{font-size:14px;color:var(--db-gray-8);padding:7px 0;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--db-gray-2)}
.feat-ul li .tick{color:var(--db-neon);font-weight:600}
.mock{background:var(--db-bg-input);border:1px solid var(--db-gray-3);border-radius:16px;overflow:hidden}
.mock-head{padding:14px 18px;border-bottom:1px solid var(--db-gray-2);display:flex;align-items:center;justify-content:space-between}
.mock-label{font-family:var(--db-font-mono);font-size:10px;color:var(--db-gray-7);letter-spacing:1.5px;text-transform:uppercase}
.mock-body{padding:20px}
.mono{font-family:var(--db-font-mono);font-variant-numeric:tabular-nums}
.tag-ok{font-family:var(--db-font-mono);font-size:10px;color:var(--db-neon);padding:2px 8px;border:1px solid rgba(63,255,0,.4);border-radius:4px;background:var(--db-neon-glow-8)}
.tag-bad{font-family:var(--db-font-mono);font-size:10px;color:var(--db-negative);padding:2px 8px;border:1px solid rgba(255,77,109,.4);border-radius:4px;background:rgba(255,77,109,.08)}
.tag-neutral{font-family:var(--db-font-mono);font-size:10px;color:var(--db-gray-7)}
.row-kv{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid var(--db-gray-2);font-size:13px}
.row-kv:last-child{border-bottom:none}
.row-kv .k{color:var(--db-gray-7)}
.row-kv .v{color:var(--db-gray-9)}
.row-kv .v.pos{color:var(--db-neon);font-weight:600}
.tf-row{display:grid;grid-template-columns:80px 1fr 50px 80px 70px;gap:10px;padding:11px 18px;font-size:12px;align-items:center;border-bottom:1px solid var(--db-gray-2);color:var(--db-gray-9)}
.tf-row.last{border-bottom:none}
.pill-ok{justify-self:end;padding:2px 7px;border-radius:999px;font-size:9.5px;font-weight:600;background:rgba(63,255,0,.12);color:var(--db-neon);border:1px solid rgba(63,255,0,.3);font-family:var(--db-font-mono)}
.pill-pending{justify-self:end;padding:2px 7px;border-radius:999px;font-size:9.5px;font-weight:600;background:rgba(255,176,32,.12);color:var(--db-warning);border:1px solid rgba(255,176,32,.3);font-family:var(--db-font-mono)}
.pl-row{padding:6px 0}
.pl-bar{height:4px;background:var(--db-gray-2);border-radius:2px;overflow:hidden;margin-top:4px}
.pl-bar > span{display:block;height:100%;background:var(--db-neon);box-shadow:0 0 8px var(--db-neon-glow-40)}
.pl-bar.neg > span{background:var(--db-negative);opacity:.5;box-shadow:none}
.bank-row{display:flex;align-items:center;justify-content:space-between;padding:14px 0;border-bottom:1px solid var(--db-gray-2)}
.bank-row:last-child{border-bottom:none}
@media(max-width:900px){
  .features{padding:72px 20px}
  .section-heading{font-size:34px;margin-bottom:56px}
  .feat-row{grid-template-columns:1fr;gap:40px;margin-bottom:72px}
  .feat-row.reverse{direction:ltr}
  .feat-num{font-size:56px}
  .feat-title{font-size:28px}
}

.stat-strip{background:var(--db-bg);padding:48px}
.stat-strip-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr);gap:0}
.stat-cell{padding:8px 20px;border-left:1px solid var(--db-gray-2)}
.stat-cell:first-child{border-left:none}
.stat-k{font-family:var(--db-font-mono);font-size:32px;font-weight:500;color:var(--db-gray-9);letter-spacing:-.02em;line-height:1}
.stat-v{font-size:13px;color:var(--db-gray-7);margin-top:8px}

footer.site{background:var(--db-bg);padding:40px 48px;border-top:1px solid var(--db-gray-2)}
.foot-inner{max-width:1100px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:24px;flex-wrap:wrap}
.foot-copy{color:var(--db-gray-6);font-size:12.5px}
.foot-links{display:flex;gap:20px}
.foot-links a{color:var(--db-gray-7);text-decoration:none;font-size:13px}

@media(max-width:900px){
  nav.site{padding:0 20px;height:60px;gap:12px}
  .nav-links{display:none;position:absolute;top:60px;left:0;right:0;margin:0;flex-direction:column;align-items:stretch;background:var(--db-bg);border-bottom:1px solid var(--db-gray-2);padding:10px 0;gap:0}
  .nav-links.open{display:flex}
  .nav-links a{padding:14px 20px;font-size:14.5px;border-top:1px solid var(--db-gray-2)}
  .nav-links .nav-cta{margin:10px 20px;text-align:center}
  .nav-toggle{display:inline-flex}
  .hero{padding:56px 20px 72px}
  .hero-inner{grid-template-columns:1fr;gap:40px}
  .hero h1{font-size:40px}
  .hero-p{font-size:16px}
  .hero-ctas{flex-direction:column;align-items:stretch}
  .btn-primary,.btn-ghost{text-align:center}
  footer.site{padding:28px 20px}
  .foot-inner{flex-direction:column;text-align:center}
}
@media(max-width:900px){
  .stat-strip{padding:32px 20px}
  .stat-strip-inner{grid-template-columns:repeat(2,1fr);gap:24px 0}
  .stat-cell{border-left:none;padding:0 16px;border-left:1px solid var(--db-gray-2)}
  .stat-cell:nth-child(2n+1){border-left:none}
  .stat-k{font-size:26px}
}
@media(max-width:480px){
  .hero h1{font-size:34px}
  .stat-strip-inner{grid-template-columns:1fr}
  .stat-cell{border-left:none!important;padding:0}
}
`;
