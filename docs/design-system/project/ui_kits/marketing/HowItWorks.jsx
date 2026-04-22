function HowItWorks() {
  const steps = [
    { n: '01', t: 'Sign up', b: 'Create your store in 60 seconds. No credit card, no sales call.' },
    { n: '02', t: 'Log your day', b: 'Enter cash in/out, money orders, check cashing, transfers. One screen, auto-saves.' },
    { n: '03', t: 'Close the month', b: 'P&L auto-populates. Export for your accountant. Spot variances before they bite.' },
  ];
  return (
    <section style={s.bg}>
      <div style={s.inner}>
        <div style={s.eye}>// HOW IT WORKS</div>
        <h2 style={s.title}>From paper to profitable<br/><span style={{color: '#3fff00'}}>in three steps.</span></h2>
        <div style={s.grid}>
          {steps.map((x, i) => (
            <div key={i} style={s.step}>
              <div style={s.sn}>{x.n}</div>
              <div style={s.st}>{x.t}</div>
              <div style={s.sb}>{x.b}</div>
              {i < 2 && <div style={s.arrow}>→</div>}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
const s = {
  bg: { padding: '96px 48px', background: '#0b0d12', borderTop: '1px solid #1c202a' },
  inner: { maxWidth: 1100, margin: '0 auto' },
  eye: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3fff00', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 18, textAlign: 'center' },
  title: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 44, color: '#e5e7eb', fontWeight: 600, letterSpacing: '-.03em', lineHeight: 1.1, textAlign: 'center', marginBottom: 64 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24, position: 'relative' },
  step: { padding: '32px 28px', background: '#0e1117', border: '1px solid #272c38', borderRadius: 16, position: 'relative' },
  sn: { fontFamily: "'JetBrains Mono', monospace", fontSize: 13, fontWeight: 600, color: '#3fff00', letterSpacing: 1.5, marginBottom: 16 },
  st: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 22, color: '#e5e7eb', fontWeight: 600, marginBottom: 8, letterSpacing: '-.02em' },
  sb: { fontSize: 14, color: '#9199a8', lineHeight: 1.55, fontFamily: "'Inter', sans-serif" },
  arrow: { position: 'absolute', right: -20, top: '50%', transform: 'translateY(-50%)', color: '#3fff00', fontSize: 24, background: '#0b0d12', padding: '0 8px' },
};
window.HowItWorks = HowItWorks;
