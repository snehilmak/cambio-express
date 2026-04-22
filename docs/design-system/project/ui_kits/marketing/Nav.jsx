function Nav() {
  return (
    <nav style={navStyle.bar}>
      <a href="#" style={navStyle.brand}>
        <div style={navStyle.mark}>$</div>
        <span style={navStyle.brandName}>DineroBook</span>
      </a>
      <div style={navStyle.links}>
        <a href="#features" style={navStyle.link}>Product</a>
        <a href="#pricing" style={navStyle.link}>Pricing</a>
        <a href="#features" style={navStyle.link}>Docs</a>
        <a href="#login" style={navStyle.link}>Sign in</a>
        <a href="#signup" style={navStyle.cta}>Get started →</a>
      </div>
    </nav>
  );
}
const navStyle = {
  bar: { position: 'sticky', top: 0, zIndex: 100, background: 'rgba(11,13,18,0.85)', backdropFilter: 'blur(12px)', padding: '0 48px', height: 64, display: 'flex', alignItems: 'center', gap: 20, borderBottom: '1px solid #1c202a' },
  brand: { textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 10 },
  mark: { width: 28, height: 28, borderRadius: 8, background: '#3fff00', color: '#001a0f', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: 16, boxShadow: '0 0 12px rgba(63,255,0,.4)' },
  brandName: { fontFamily: "'Space Grotesk', sans-serif", color: '#e5e7eb', fontSize: 17, fontWeight: 600, letterSpacing: '-.02em' },
  links: { marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 28 },
  link: { color: '#9199a8', textDecoration: 'none', fontSize: 13, fontFamily: "'Inter', sans-serif", fontWeight: 500 },
  cta: { background: '#3fff00', color: '#001a0f', padding: '9px 18px', borderRadius: 10, fontWeight: 600, fontSize: 13, textDecoration: 'none', fontFamily: "'Inter', sans-serif", letterSpacing: '-.01em' },
};
window.Nav = Nav;
