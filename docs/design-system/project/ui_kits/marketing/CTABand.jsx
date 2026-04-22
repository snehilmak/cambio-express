function CTABand() {
  return (
    <section style={c.bg}>
      <div style={c.glow}/>
      <div style={c.inner}>
        <div style={c.eye}>// READY?</div>
        <h2 style={c.title}>Your first daily book<br/>takes <span style={{color: '#3fff00'}}>ten minutes.</span></h2>
        <p style={c.p}>No credit card. 7-day Pro trial. Cancel anytime, keep your data.</p>
        <div style={c.ctas}>
          <a href="#signup" style={c.primary}>Start free trial →</a>
          <a href="#contact" style={c.ghost}>Talk to us</a>
        </div>
      </div>
    </section>
  );
}
const c = {
  bg: { padding: '120px 48px', background: '#0b0d12', position: 'relative', overflow: 'hidden', borderTop: '1px solid #1c202a' },
  glow: { position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', width: 600, height: 600, background: 'radial-gradient(circle, rgba(63,255,0,.2), transparent 60%)', pointerEvents: 'none' },
  inner: { maxWidth: 800, margin: '0 auto', textAlign: 'center', position: 'relative' },
  eye: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3fff00', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 18 },
  title: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 60, color: '#e5e7eb', fontWeight: 700, letterSpacing: '-.035em', lineHeight: 1.05, marginBottom: 22 },
  p: { fontSize: 17, color: '#9199a8', marginBottom: 36, fontFamily: "'Inter', sans-serif" },
  ctas: { display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' },
  primary: { background: '#3fff00', color: '#0a1a00', padding: '16px 32px', borderRadius: 12, fontSize: 15, fontWeight: 600, textDecoration: 'none', fontFamily: "'Inter', sans-serif", letterSpacing: '-.01em', boxShadow: '0 0 0 1px #3fff00, 0 0 40px rgba(63,255,0,.45)' },
  ghost: { background: 'transparent', color: '#e5e7eb', border: '1px solid #363c4a', padding: '16px 28px', borderRadius: 12, fontSize: 15, fontWeight: 500, textDecoration: 'none', fontFamily: "'Inter', sans-serif" },
};
window.CTABand = CTABand;
