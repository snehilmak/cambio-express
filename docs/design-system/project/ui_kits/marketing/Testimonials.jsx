function Testimonials() {
  const items = [
    { q: 'Our monthly close went from three days of spreadsheet chaos to one afternoon. The ACH variance alerts alone have paid for the whole year.', n: 'Marcela R.', r: 'Owner · 3 stores · Miami, FL' },
    { q: 'I stopped losing sleep over whether my books matched the bank. They match. Every day. DineroBook caught $400 in missing deposits in the first month.', n: 'Hector D.', r: 'Owner · El Paso, TX' },
    { q: 'My employees actually use it. That\'s the real test. The daily book takes ten minutes at close instead of forty-five on paper.', n: 'Patricia G.', r: 'Operator · Newark, NJ' },
  ];
  return (
    <section style={t.bg}>
      <div style={t.inner}>
        <div style={t.eye}>// FROM SHOPS LIKE YOURS</div>
        <h2 style={t.title}>MSB owners who retired<br/>their paper ledgers.</h2>
        <div style={t.grid}>
          {items.map((x, i) => (
            <div key={i} style={t.card}>
              <div style={t.quote}>"{x.q}"</div>
              <div style={t.who}>
                <div style={t.avatar}>{x.n[0]}</div>
                <div>
                  <div style={t.name}>{x.n}</div>
                  <div style={t.role}>{x.r}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
const t = {
  bg: { padding: '96px 48px', background: '#0b0d12', borderTop: '1px solid #1c202a' },
  inner: { maxWidth: 1200, margin: '0 auto' },
  eye: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3fff00', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 18, textAlign: 'center' },
  title: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 44, color: '#e5e7eb', fontWeight: 600, letterSpacing: '-.03em', lineHeight: 1.1, textAlign: 'center', marginBottom: 56 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 },
  card: { background: '#0e1117', border: '1px solid #272c38', borderRadius: 16, padding: 28 },
  quote: { fontSize: 15, color: '#c4cad6', lineHeight: 1.6, fontFamily: "'Inter', sans-serif", marginBottom: 24 },
  who: { display: 'flex', alignItems: 'center', gap: 12 },
  avatar: { width: 40, height: 40, borderRadius: 999, background: 'linear-gradient(135deg,#3fff00,#2ecc00)', color: '#0a1a00', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: 16 },
  name: { fontSize: 13, color: '#e5e7eb', fontWeight: 600, fontFamily: "'Inter', sans-serif" },
  role: { fontSize: 11.5, color: '#9199a8', fontFamily: "'Inter', sans-serif", marginTop: 2 },
};
window.Testimonials = Testimonials;
