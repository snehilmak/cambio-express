function Footer() {
  return (
    <footer style={footStyle.bar}>
      <div style={footStyle.inner}>
        <div style={footStyle.brand}>
          <div style={footStyle.mark}>$</div>
          <span style={footStyle.name}>DineroBook</span>
        </div>
        <div style={footStyle.copy}>© 2026 · MSB Terminal · Made for shops that move fast.</div>
        <div style={{display: 'flex', gap: 20}}>
          <a href="#" style={footStyle.link}>Privacy</a>
          <a href="#" style={footStyle.link}>Terms</a>
          <a href="#login" style={footStyle.link}>Sign in →</a>
        </div>
      </div>
    </footer>
  );
}
const footStyle = {
  bar: { background: '#0b0d12', padding: '40px 48px', borderTop: '1px solid #1c202a' },
  inner: { maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 24, flexWrap: 'wrap' },
  brand: { display: 'flex', alignItems: 'center', gap: 10 },
  mark: { width: 24, height: 24, borderRadius: 6, background: '#3fff00', color: '#001a0f', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: 14 },
  name: { fontFamily: "'Space Grotesk', sans-serif", color: '#e5e7eb', fontSize: 15, fontWeight: 600, letterSpacing: '-.02em' },
  copy: { color: '#6b7280', fontSize: 12.5, fontFamily: "'Inter', sans-serif" },
  link: { color: '#9199a8', textDecoration: 'none', fontSize: 13, fontFamily: "'Inter', sans-serif" },
};
window.Footer = Footer;
