function Pricing() {
  return (
    <section id="pricing" style={p.section}>
      <div style={p.inner}>
        <div style={p.eye}>// PRICING</div>
        <h2 style={p.heading}>One price. Per store.<br/><span style={{color: '#3fff00'}}>No surprises.</span></h2>
        <div style={p.grid}>
          <Plan name="TRIAL" price="$0" period="7 days · full Pro access" features={['All Pro features', 'No credit card required', 'Instant access']} cta="Start free" variant="ghost"/>
          <Plan name="BASIC" price="$20" priceSuffix="/mo" period="per store · monthly" features={['Daily books', 'Money transfer logging', 'ACH reconciliation', 'Monthly P&L', 'CSV / PDF export', 'Unlimited employees']} excluded={['Bank sync']} cta="Choose Basic" variant="outline"/>
          <Plan name="PRO" price="$30" priceSuffix="/mo" period="or $300 / yr · 2 months free" featured features={['Everything in Basic', 'Live bank sync', 'Drift alerts', 'Multi-store umbrella', 'Priority support', 'Early access to new features']} cta="Choose Pro →" variant="neon"/>
        </div>
        <div style={p.fine}>All plans include unlimited transactions, unlimited customers, and 180-day data retention after cancellation.</div>
      </div>
    </section>
  );
}
function Plan({ name, price, priceSuffix, period, features, excluded = [], cta, variant, featured }) {
  const card = { ...p.plan, ...(featured ? p.planFeatured : {}) };
  const btn = {
    ghost: { background: '#1c202a', color: '#e5e7eb' },
    outline: { background: 'transparent', color: '#e5e7eb', border: '1px solid #363c4a' },
    neon: { background: '#3fff00', color: '#0a1a00', boxShadow: '0 0 0 1px #3fff00, 0 0 24px rgba(63,255,0,.35)' },
  }[variant];
  return (
    <div style={card}>
      {featured && <div style={p.featuredBadge}>MOST POPULAR</div>}
      <div style={p.name}>{name}</div>
      <div style={p.price}>{price}{priceSuffix && <span style={p.priceSuffix}>{priceSuffix}</span>}</div>
      <div style={p.period}>{period}</div>
      <ul style={p.features}>
        {features.map((f, i) => (<li key={i} style={p.feat}><span style={p.check}>✓</span> {f}</li>))}
        {excluded.map((f, i) => (<li key={`x${i}`} style={{...p.feat, color: '#4a5162'}}><span style={p.xmark}>—</span> {f}</li>))}
      </ul>
      <a href="#" style={{...p.btn, ...btn}}>{cta}</a>
    </div>
  );
}
const p = {
  section: { padding: '96px 48px', background: '#0b0d12', borderTop: '1px solid #1c202a' },
  inner: { maxWidth: 1100, margin: '0 auto' },
  eye: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, fontWeight: 500, color: '#3fff00', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 18, textAlign: 'center' },
  heading: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 44, color: '#e5e7eb', marginBottom: 56, fontWeight: 600, letterSpacing: '-.03em', lineHeight: 1.1, textAlign: 'center' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, alignItems: 'stretch' },
  plan: { background: '#0e1117', border: '1px solid #272c38', borderRadius: 16, padding: '32px 28px', position: 'relative', display: 'flex', flexDirection: 'column' },
  planFeatured: { borderColor: '#3fff00', background: '#11141b', boxShadow: '0 0 0 1px #3fff00, 0 0 48px rgba(63,255,0,.15)' },
  featuredBadge: { position: 'absolute', top: -11, left: 24, background: '#3fff00', color: '#0a1a00', fontSize: 10, fontWeight: 700, letterSpacing: 1.5, padding: '3px 12px', borderRadius: 4, fontFamily: "'JetBrains Mono', monospace" },
  name: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, fontWeight: 500, color: '#9199a8', letterSpacing: 2, marginBottom: 14 },
  price: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 52, fontWeight: 700, lineHeight: 1, marginBottom: 4, color: '#e5e7eb', letterSpacing: '-.04em' },
  priceSuffix: { fontSize: 20, color: '#6b7280', fontWeight: 400 },
  period: { fontSize: 13, marginBottom: 24, color: '#9199a8', fontFamily: "'Inter', sans-serif" },
  features: { listStyle: 'none', marginBottom: 24, padding: 0, flex: 1 },
  feat: { fontSize: 13.5, padding: '8px 0', color: '#c4cad6', fontFamily: "'Inter', sans-serif", display: 'flex', alignItems: 'center', gap: 8, borderBottom: '1px solid #1c202a' },
  check: { color: '#3fff00', fontWeight: 600, fontSize: 14 },
  xmark: { color: '#363c4a' },
  btn: { display: 'block', textAlign: 'center', padding: '13px 18px', borderRadius: 10, fontSize: 14, fontWeight: 600, textDecoration: 'none', fontFamily: "'Inter', sans-serif", letterSpacing: '-.01em' },
  fine: { textAlign: 'center', marginTop: 32, fontSize: 13, color: '#6b7280', fontFamily: "'Inter', sans-serif" },
};
window.Pricing = Pricing;
