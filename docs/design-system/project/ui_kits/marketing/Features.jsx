// Each feature has a large title side + a pixel-perfect mini UI mockup side.
// Alternates text-left/right.

function FeatureDailyBook() {
  return (
    <FeatureRow
      number="01"
      eyebrow="THE DAILY BOOK"
      title="Close your register in under 15 minutes."
      body="One screen captures everything that moved through your store today — cash in, cash out, money orders, check cashing, sales. Auto-totals, auto-saves, auto-rolls-up into your monthly P&L."
      bullets={['Cash in / cash out reconciliation', 'Money orders & check cashing', 'Store sales & other services', 'Notes for the unusual days']}
      visual={<MockDailyBook/>}
    />
  );
}
function FeatureTransfers() {
  return (
    <FeatureRow
      reverse
      number="02"
      eyebrow="MONEY TRANSFERS"
      title="Every wire, logged. Every customer, remembered."
      body="Intermex, Maxi, Barri, Ria, Western Union — one form, full sender and recipient detail, fee and federal tax broken out correctly. Customers auto-complete across your entire store umbrella."
      bullets={['Sender phone autocomplete across sibling stores', 'Fee vs federal tax separated automatically', 'Full transfer history, searchable', 'Status tracking: Sent · Pending · Canceled']}
      visual={<MockTransfers/>}
    />
  );
}
function FeatureACH() {
  return (
    <FeatureRow
      number="03"
      eyebrow="ACH RECONCILIATION"
      title="Spot variances before the month ends."
      body="Your ACH batch from Intermex doesn't match what you logged? DineroBook flags it the day it happens — not three weeks later when you're already chasing ghosts."
      bullets={['Auto-match batches to transfer totals', 'Variance alerts on day-one', 'Clear / partial / disputed statuses', 'One-click drill-down to underlying transfers']}
      visual={<MockACH/>}
    />
  );
}
function FeaturePL() {
  return (
    <FeatureRow
      reverse
      number="04"
      eyebrow="MONTHLY P&amp;L"
      title="Know exactly what you made last month."
      body="Auto-populated from your daily books and transfer ledger. Revenue by service line, fees collected, money-order margins, store sales — no spreadsheets required."
      bullets={['Revenue split by service', 'Fee income vs federal tax pass-through', 'YoY comparison', 'CSV / PDF export for your accountant']}
      visual={<MockPL/>}
    />
  );
}
function FeatureBankSync() {
  return (
    <FeatureRow
      number="05"
      eyebrow="BANK SYNC · PRO"
      title="Live bank balances, alongside your books."
      body="Connect via Stripe Financial Connections. Your real bank balance sits next to your book balance — the moment they drift, you know."
      bullets={['Multi-bank support', 'Read-only · bank-grade security', 'Daily auto-refresh', 'Drift alerts when books ≠ bank']}
      visual={<MockBankSync/>}
    />
  );
}

function FeatureRow({ reverse, number, eyebrow, title, body, bullets, visual }) {
  return (
    <div style={{...rowStyle.row, flexDirection: reverse ? 'row-reverse' : 'row'}}>
      <div style={rowStyle.text}>
        <div style={rowStyle.num}>{number}</div>
        <div style={rowStyle.eyebrow}>{eyebrow}</div>
        <h3 style={rowStyle.title}>{title}</h3>
        <p style={rowStyle.body}>{body}</p>
        <ul style={rowStyle.ul}>
          {bullets.map((b, i) => (
            <li key={i} style={rowStyle.li}>
              <span style={rowStyle.tick}>✓</span> {b}
            </li>
          ))}
        </ul>
      </div>
      <div style={rowStyle.visual}>{visual}</div>
    </div>
  );
}

function Features() {
  return (
    <section id="features" style={rowStyle.section}>
      <div style={rowStyle.inner}>
        <div style={rowStyle.sectionHead}>
          <div style={rowStyle.sectionEye}>// BUILT FOR MSB OWNERS</div>
          <h2 style={rowStyle.sectionTitle}>Every part of the day,<br/><span style={{color: '#3fff00'}}>finally in one place.</span></h2>
        </div>
        <FeatureDailyBook/>
        <FeatureTransfers/>
        <FeatureACH/>
        <FeaturePL/>
        <FeatureBankSync/>
      </div>
    </section>
  );
}

const rowStyle = {
  section: { padding: '120px 48px', background: '#0b0d12' },
  inner: { maxWidth: 1200, margin: '0 auto' },
  sectionHead: { textAlign: 'center', marginBottom: 96 },
  sectionEye: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3fff00', letterSpacing: '2px', textTransform: 'uppercase', marginBottom: 18 },
  sectionTitle: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 48, color: '#e5e7eb', fontWeight: 600, letterSpacing: '-.03em', lineHeight: 1.1 },
  row: { display: 'flex', gap: 80, alignItems: 'center', marginBottom: 120, flexWrap: 'wrap' },
  text: { flex: '1 1 380px', minWidth: 0 },
  num: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 88, fontWeight: 700, color: '#1c202a', letterSpacing: '-.04em', lineHeight: 1, marginBottom: 6 },
  eyebrow: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3fff00', letterSpacing: '2px', textTransform: 'uppercase', marginBottom: 16 },
  title: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 38, color: '#e5e7eb', fontWeight: 600, letterSpacing: '-.025em', lineHeight: 1.1, marginBottom: 20 },
  body: { fontSize: 16, color: '#9199a8', lineHeight: 1.6, fontFamily: "'Inter', sans-serif", marginBottom: 22 },
  ul: { listStyle: 'none', padding: 0, margin: 0 },
  li: { fontSize: 14, color: '#c4cad6', padding: '7px 0', fontFamily: "'Inter', sans-serif", display: 'flex', alignItems: 'center', gap: 10, borderBottom: '1px solid #1c202a' },
  tick: { color: '#3fff00', fontWeight: 600 },
  visual: { flex: '1 1 420px', minWidth: 0 },
};

window.Features = Features;
