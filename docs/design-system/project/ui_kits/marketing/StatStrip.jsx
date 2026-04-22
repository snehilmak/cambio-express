// Numeric "stat strip" — the trust anchor under the hero
function StatStrip() {
  const stats = [
    { k: '2,400+', v: 'MSB shops using daily' },
    { k: '$4.2B', v: 'transactions logged' },
    { k: '12 min', v: 'avg daily close time' },
    { k: '99.9%', v: 'uptime · 12 months' },
  ];
  return (
    <section style={stripStyle.bg}>
      <div style={stripStyle.inner}>
        {stats.map((s, i) => (
          <div key={i} style={stripStyle.cell}>
            <div style={stripStyle.k}>{s.k}</div>
            <div style={stripStyle.v}>{s.v}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
const stripStyle = {
  bg: { background: '#0b0d12', padding: '48px 48px', borderTop: '1px solid #1c202a', borderBottom: '1px solid #1c202a' },
  inner: { maxWidth: 1200, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 0 },
  cell: { padding: '8px 20px', borderLeft: '1px solid #1c202a' },
  k: { fontFamily: "'JetBrains Mono', monospace", fontSize: 32, fontWeight: 500, color: '#e5e7eb', letterSpacing: '-.02em', fontVariantNumeric: 'tabular-nums', lineHeight: 1 },
  v: { fontFamily: "'Inter', sans-serif", fontSize: 13, color: '#9199a8', marginTop: 8 },
};
window.StatStrip = StatStrip;
