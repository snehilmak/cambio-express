function Hero() {
  return (
    <section style={heroStyle.bg}>
      {/* Background grid + radial glow */}
      <div style={heroStyle.gridBg}/>
      <div style={heroStyle.glow}/>
      <div style={heroStyle.inner}>
        <div style={heroStyle.left}>
          <div style={heroStyle.eyebrow}>
            <span style={heroStyle.dot}/> MSB TERMINAL · BUILT FOR SHOPS
          </div>
          <h1 style={heroStyle.h1}>
            The daily book<br/>
            for money-service<br/>
            <span style={heroStyle.neon}>businesses.</span>
          </h1>
          <p style={heroStyle.p}>
            Check cashing, money orders, wire transfers, bill pay — all your cash activity, tracked in one place. No more paper logs, no more mystery variances at the end of the month.
          </p>
          <div style={heroStyle.ctas}>
            <a href="#signup" style={heroStyle.primary}>Start free trial →</a>
            <a href="#features" style={heroStyle.ghost}>See how it works</a>
          </div>
          <div style={heroStyle.logos}>
            <div style={heroStyle.logosLabel}>WORKS WITH</div>
            <div style={heroStyle.logosRow}>
              <span style={{...heroStyle.chip, color: '#5ea9ff', borderColor: '#1c3355'}}>Intermex</span>
              <span style={{...heroStyle.chip, color: '#b48cff', borderColor: '#331c55'}}>Maxi</span>
              <span style={{...heroStyle.chip, color: '#4dd8e6', borderColor: '#134a55'}}>Barri</span>
              <span style={{...heroStyle.chip, color: '#e5e7eb', borderColor: '#363c4a'}}>Ria</span>
              <span style={{...heroStyle.chip, color: '#e5e7eb', borderColor: '#363c4a'}}>Western Union</span>
            </div>
          </div>
        </div>
        <div style={heroStyle.right}>
          <HeroIsometric/>
        </div>
      </div>
    </section>
  );
}

const heroStyle = {
  bg: { background: '#0b0d12', padding: '80px 48px 96px', position: 'relative', overflow: 'hidden', borderBottom: '1px solid #1c202a' },
  gridBg: { position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(#1c202a 1px, transparent 1px), linear-gradient(90deg, #1c202a 1px, transparent 1px)', backgroundSize: '48px 48px', maskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)', WebkitMaskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)', opacity: .5 },
  glow: { position: 'absolute', top: '40%', right: '15%', width: 400, height: 400, background: 'radial-gradient(circle, rgba(63,255,0,.2), transparent 60%)', pointerEvents: 'none' },
  inner: { maxWidth: 1200, margin: '0 auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 60, alignItems: 'center', position: 'relative' },
  left: {},
  right: {},
  eyebrow: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: '2px', color: '#3fff00', textTransform: 'uppercase', marginBottom: 28, fontWeight: 500, display: 'inline-flex', alignItems: 'center', gap: 10, padding: '5px 12px', border: '1px solid rgba(63,255,0,.3)', borderRadius: 999, background: 'rgba(63,255,0,.05)' },
  dot: { width: 6, height: 6, borderRadius: 999, background: '#3fff00', boxShadow: '0 0 8px #3fff00' },
  h1: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 64, lineHeight: 1.02, marginBottom: 24, fontWeight: 700, color: '#e5e7eb', letterSpacing: '-.035em' },
  neon: { color: '#3fff00' },
  p: { fontSize: 17, color: '#9199a8', lineHeight: 1.6, fontFamily: "'Inter', sans-serif", marginBottom: 32, maxWidth: 480 },
  ctas: { display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 40 },
  primary: { background: '#3fff00', color: '#0a1a00', padding: '14px 28px', borderRadius: 12, fontSize: 14.5, fontWeight: 600, textDecoration: 'none', fontFamily: "'Inter', sans-serif", letterSpacing: '-.01em', boxShadow: '0 0 0 1px #3fff00, 0 0 32px rgba(63,255,0,.4)' },
  ghost: { background: 'transparent', color: '#e5e7eb', border: '1px solid #363c4a', padding: '14px 24px', borderRadius: 12, fontSize: 14.5, fontWeight: 500, textDecoration: 'none', fontFamily: "'Inter', sans-serif" },
  logos: {},
  logosLabel: { fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#6b7280', letterSpacing: '1.5px', textTransform: 'uppercase', marginBottom: 12 },
  logosRow: { display: 'flex', gap: 8, flexWrap: 'wrap' },
  chip: { padding: '6px 12px', border: '1px solid #272c38', borderRadius: 999, fontSize: 12, fontWeight: 500, fontFamily: "'Inter', sans-serif", background: '#0e1117' },
};
window.Hero = Hero;
