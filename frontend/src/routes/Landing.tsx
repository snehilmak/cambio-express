import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import styles from "./Landing.module.css";

// Marketing landing page. Redesigned 2026-06-04 to drop the
// marketing-page decorations (parallax, scroll reveals, fake-stat
// counters, decorative hero SVG, sticky "How it works", FAQ accordion,
// 4 detailed feature mocks) that didn't carry over from the
// pre-architecture-migration era. Reads as an extension of the
// post-login app now: dark surfaces, single neon accent, hover-only
// motion, simple structure.
export default function Landing() {
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }, []);

  return (
    <div className={styles.shell}>
      <nav className={styles.nav}>
        <a href="/" className={styles.navBrand}>
          <img className={styles.navBrandMark} src="/static/brand-mark.svg" alt="" />
          <span className={styles.navBrandName}>DineroBook</span>
        </a>
        <button
          type="button"
          className={styles.navToggle}
          aria-label="Toggle menu"
          onClick={() => setNavOpen((v) => !v)}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <div
          className={`${styles.navLinks}${navOpen ? ` ${styles.open}` : ""}`}
          onClick={(e) => {
            if ((e.target as HTMLElement).tagName === "A") setNavOpen(false);
          }}
        >
          <a href="#features">Product</a>
          <a href="#pricing">Pricing</a>
          <Link to="/login">Sign in</Link>
          <Link to="/signup" className={styles.navCta}>Get started</Link>
        </div>
      </nav>

      <section className={styles.hero}>
        <div className={styles.heroGlow} aria-hidden="true" />
        <div className={styles.heroInner}>
          <div className={styles.eyebrow}>
            <span className={styles.eyebrowDot} />
            BUILT FOR INDEPENDENT STORE OWNERS
          </div>
          <h1 className={styles.heroTitle}>
            The modern back office for<br />
            <span className={styles.accent}>your store.</span>
          </h1>
          <p className={styles.heroSub}>
            Convenience stores, gas stations, groceries — daily close-out,
            check cashing, money services, and your monthly P&amp;L, all in
            one place. No paper logs, no end-of-month mystery variances.
          </p>
          <div className={styles.ctas}>
            <Link to="/signup" className={styles.btnPrimary}>Start free trial</Link>
            <a href="#features" className={styles.btnGhost}>See how it works</a>
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionEye}>HOW IT WORKS</div>
        <h2 className={styles.sectionTitle}>
          From paper to profitable <span className={styles.accent}>in three steps.</span>
        </h2>
        <div className={styles.steps}>
          <div className={styles.step}>
            <div className={styles.stepNum}>01</div>
            <div className={styles.stepTitle}>Sign up</div>
            <div className={styles.stepBody}>
              Create your store in 60 seconds. No credit card, no sales call.
            </div>
          </div>
          <div className={styles.step}>
            <div className={styles.stepNum}>02</div>
            <div className={styles.stepTitle}>Log your day</div>
            <div className={styles.stepBody}>
              Cash in/out, money orders, check cashing, transfers. One screen,
              auto-saves.
            </div>
          </div>
          <div className={styles.step}>
            <div className={styles.stepNum}>03</div>
            <div className={styles.stepTitle}>Close the month</div>
            <div className={styles.stepBody}>
              P&amp;L auto-populates. Export for your accountant. Spot variances
              before they bite.
            </div>
          </div>
        </div>
      </section>

      <section className={styles.section} id="features">
        <div className={styles.sectionEye}>BUILT FOR STORE OWNERS</div>
        <h2 className={styles.sectionTitle}>
          Every part of the day, <span className={styles.accent}>finally in one place.</span>
        </h2>

        <div className={styles.features}>
          <div className={styles.feature}>
            <div className={styles.featureEye}>THE DAILY BOOK</div>
            <div className={styles.featureTitle}>Close your register in under 15 minutes.</div>
            <div className={styles.featureBody}>
              One screen captures everything that moved through your store today.
              Auto-totals, auto-saves, auto-rolls into your monthly P&amp;L.
            </div>
            <ul className={styles.featureList}>
              <li><span className={styles.tick}>✓</span>Cash in / cash out reconciliation</li>
              <li><span className={styles.tick}>✓</span>Money orders &amp; check cashing</li>
              <li><span className={styles.tick}>✓</span>Store sales &amp; other services</li>
            </ul>
          </div>

          <div className={styles.feature}>
            <div className={styles.featureEye}>MONEY TRANSFERS</div>
            <div className={styles.featureTitle}>Every wire, logged. Every customer, remembered.</div>
            <div className={styles.featureBody}>
              Intermex, Maxi, Barri, Ria, Western Union — one form, full sender
              and recipient detail, fee and federal tax broken out correctly.
            </div>
            <ul className={styles.featureList}>
              <li><span className={styles.tick}>✓</span>Sender autocomplete across sibling stores</li>
              <li><span className={styles.tick}>✓</span>Fee vs federal tax separated automatically</li>
              <li><span className={styles.tick}>✓</span>Full transfer history, searchable</li>
            </ul>
          </div>

          <div className={styles.feature}>
            <div className={styles.featureEye}>ACH RECONCILIATION</div>
            <div className={styles.featureTitle}>Spot variances before the month ends.</div>
            <div className={styles.featureBody}>
              Your ACH batch from Intermex doesn't match what you logged?
              DineroBook flags it the day it happens — not three weeks later.
            </div>
            <ul className={styles.featureList}>
              <li><span className={styles.tick}>✓</span>Auto-match batches to transfer totals</li>
              <li><span className={styles.tick}>✓</span>Variance alerts on day one</li>
              <li><span className={styles.tick}>✓</span>One-click drill-down to underlying transfers</li>
            </ul>
          </div>

          <div className={styles.feature}>
            <div className={styles.featureEye}>MONTHLY P&amp;L</div>
            <div className={styles.featureTitle}>Know exactly what you made last month.</div>
            <div className={styles.featureBody}>
              Auto-populated from your daily books and transfer ledger. Revenue
              by service line, fees collected, money-order margins.
            </div>
            <ul className={styles.featureList}>
              <li><span className={styles.tick}>✓</span>Revenue split by service</li>
              <li><span className={styles.tick}>✓</span>Year-over-year comparison</li>
              <li><span className={styles.tick}>✓</span>CSV / PDF export for your accountant</li>
            </ul>
          </div>
        </div>
      </section>

      <section className={styles.section} id="pricing">
        <div className={styles.sectionEye}>PRICING</div>
        <h2 className={styles.sectionTitle}>
          One price per store. <span className={styles.accent}>No surprises.</span>
        </h2>
        <div className={styles.pricing}>
          <div className={styles.plan}>
            <div className={styles.planName}>BASIC</div>
            <div className={styles.planPrice}>$35<span className={styles.priceSuffix}>/mo</span></div>
            <div className={styles.planPeriod}>per store · monthly · or $350 / yr</div>
            <ul className={styles.planFeats}>
              <li><span className={styles.ck}>✓</span>Daily books</li>
              <li><span className={styles.ck}>✓</span>Money transfer logging</li>
              <li><span className={styles.ck}>✓</span>ACH reconciliation</li>
              <li><span className={styles.ck}>✓</span>Monthly P&amp;L</li>
              <li><span className={styles.ck}>✓</span>CSV / PDF export</li>
              <li><span className={styles.ck}>✓</span>Unlimited employees</li>
            </ul>
            <Link to="/signup?plan=basic" className={`${styles.planBtn} ${styles.planBtnOutline}`}>
              Choose Basic
            </Link>
          </div>
          <div className={styles.plan}>
            <div className={styles.planName}>PRO</div>
            <div className={styles.planPrice}>$45<span className={styles.priceSuffix}>/mo</span></div>
            <div className={styles.planPeriod}>or $420 / yr · 2 months free</div>
            <ul className={styles.planFeats}>
              <li><span className={styles.ck}>✓</span>Everything in Basic</li>
              <li><span className={styles.ck}>✓</span>Live bank sync</li>
              <li><span className={styles.ck}>✓</span>Drift alerts</li>
              <li><span className={styles.ck}>✓</span>Multi-store umbrella</li>
              <li><span className={styles.ck}>✓</span>Priority support</li>
            </ul>
            <Link to="/signup?plan=pro" className={`${styles.planBtn} ${styles.planBtnNeon}`}>
              Choose Pro
            </Link>
          </div>
        </div>
        <div className={styles.pricingFine}>
          All plans include unlimited transactions, unlimited customers, and
          180-day data retention after cancellation.
        </div>
      </section>

      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <a href="/" className={styles.navBrand}>
            <img className={styles.navBrandMark} src="/static/brand-mark.svg" alt="" />
            <span className={styles.navBrandName}>DineroBook</span>
          </a>
          <div className={styles.footerCopy}>© 2026 DineroBook · Made for shops that move fast.</div>
          <div className={styles.footerLinks}>
            <a href="/privacy">Privacy</a>
            <Link to="/login">Sign in</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
