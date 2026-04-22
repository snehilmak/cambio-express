// Left side — brand pane with animated isometric stack + testimonial
function LoginLeft() {
  return (
    <div style={L.pane}>
      <div style={L.grid}/>
      <div style={L.glow}/>

      <div style={L.brand}>
        <div style={L.mark}>
          <span style={L.markDollar}>$</span>
        </div>
        <span style={L.wordmark}>DineroBook</span>
      </div>

      <div style={L.middle}>
        <div style={L.eyebrow}><span style={L.dot}/> THE DAILY BOOK · FOR MSBs</div>
        <h1 style={L.h1}>
          Close your day in<br/>
          <span style={L.neon}>fifteen minutes.</span>
        </h1>
        <p style={L.p}>
          Check cashing, money orders, wire transfers — every dollar that moves through your store, logged and reconciled in one place.
        </p>

        {/* Mini isometric preview */}
        <div style={L.iso}>
          <svg viewBox="0 0 420 240" style={{width: '100%', height: 'auto'}}>
            <defs>
              <linearGradient id="paneL" x1="0" x2="1" y1="0" y2="1">
                <stop offset="0" stopColor="#161920"/>
                <stop offset="1" stopColor="#0e1117"/>
              </linearGradient>
              <filter id="glowL"><feGaussianBlur stdDeviation="2.5"/></filter>
            </defs>
            {/* back pane - P&L bars */}
            <g>
              <path d="M 90 30 L 320 0 L 410 30 L 180 60 Z" fill="url(#paneL)" stroke="#272c38"/>
              <path d="M 90 30 L 180 60 L 180 100 L 90 70 Z" fill="#0b0d12" stroke="#272c38"/>
              <path d="M 410 30 L 180 60 L 180 100 L 410 70 Z" fill="url(#paneL)" stroke="#272c38"/>
              <g transform="translate(200,30)">
                <rect x="0" y="0" width="14" height="20" fill="#3fff00" opacity=".45" transform="skewY(18)"/>
                <rect x="22" y="-6" width="14" height="26" fill="#3fff00" opacity=".7" transform="skewY(18)"/>
                <rect x="44" y="-12" width="14" height="32" fill="#3fff00" transform="skewY(18)"/>
                <rect x="66" y="-18" width="14" height="38" fill="#3fff00" transform="skewY(18)"/>
                <rect x="88" y="-10" width="14" height="30" fill="#3fff00" opacity=".75" transform="skewY(18)"/>
                <rect x="110" y="-22" width="14" height="42" fill="#3fff00" transform="skewY(18)"/>
              </g>
            </g>
            {/* front pane - daily book */}
            <g transform="translate(-30,100)">
              <path d="M 80 50 L 300 20 L 390 50 L 170 80 Z" fill="url(#paneL)" stroke="#3fff00" opacity=".95"/>
              <path d="M 80 50 L 170 80 L 170 130 L 80 100 Z" fill="#0b0d12" stroke="#3fff00"/>
              <path d="M 390 50 L 170 80 L 170 130 L 390 100 Z" fill="url(#paneL)" stroke="#3fff00"/>
              <g transform="translate(185,40)">
                <g transform="skewY(-9)">
                  <text x="0" y="8" fontFamily="JetBrains Mono" fontSize="8" fill="#9199a8">DAILY BOOK · MAR 14</text>
                  <rect x="0" y="14" width="95" height="11" fill="#0b0d12" stroke="#272c38"/>
                  <text x="4" y="22" fontFamily="JetBrains Mono" fontSize="8" fill="#e5e7eb">CASH IN $4,200</text>
                  <rect x="100" y="14" width="95" height="11" fill="#0b0d12" stroke="#272c38"/>
                  <text x="104" y="22" fontFamily="JetBrains Mono" fontSize="8" fill="#e5e7eb">OUT $3,850</text>
                  <rect x="0" y="29" width="195" height="11" fill="#0b0d12" stroke="#3fff00"/>
                  <text x="4" y="37" fontFamily="JetBrains Mono" fontSize="8" fill="#3fff00">NET +$350.00</text>
                </g>
              </g>
            </g>
            {/* dollar badge */}
            <g transform="translate(340,160)" filter="url(#glowL)">
              <rect x="0" y="0" width="44" height="44" rx="10" fill="#0b0d12" stroke="#3fff00" strokeWidth="1.5"/>
              <text x="22" y="31" textAnchor="middle" fontFamily="Space Grotesk" fontSize="26" fontWeight="700" fill="#3fff00">$</text>
            </g>
          </svg>
        </div>
      </div>

      <div style={L.bottom}>
        <div style={L.quote}>"Our monthly close went from three days of spreadsheet chaos to one afternoon."</div>
        <div style={L.attrib}>
          <div style={L.avatar}>M</div>
          <div>
            <div style={L.name}>Marcela R.</div>
            <div style={L.role}>Owner · 3 stores · Miami, FL</div>
          </div>
        </div>
      </div>
    </div>
  );
}

const L = {
  pane: { width: '50%', minWidth: 480, background: '#0b0d12', borderRight: '1px solid #1c202a', padding: '40px 56px', display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden', color: '#e5e7eb' },
  grid: { position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(#1c202a 1px, transparent 1px), linear-gradient(90deg, #1c202a 1px, transparent 1px)', backgroundSize: '48px 48px', maskImage: 'radial-gradient(ellipse at 60% 40%, black 20%, transparent 70%)', WebkitMaskImage: 'radial-gradient(ellipse at 60% 40%, black 20%, transparent 70%)', opacity: .5, pointerEvents: 'none' },
  glow: { position: 'absolute', top: '30%', right: '-10%', width: 420, height: 420, background: 'radial-gradient(circle, rgba(63,255,0,.22), transparent 60%)', pointerEvents: 'none' },
  brand: { display: 'flex', alignItems: 'center', gap: 12, position: 'relative', zIndex: 1 },
  mark: { width: 36, height: 36, borderRadius: 10, background: '#3fff00', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 24px rgba(63,255,0,.45)' },
  markDollar: { fontFamily: "'Space Grotesk', sans-serif", color: '#0a1a00', fontWeight: 700, fontSize: 22 },
  wordmark: { fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600, fontSize: 20, letterSpacing: '-.02em' },
  middle: { flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', position: 'relative', zIndex: 1, maxWidth: 480 },
  eyebrow: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 2, color: '#3fff00', textTransform: 'uppercase', marginBottom: 24, display: 'inline-flex', alignItems: 'center', gap: 10, padding: '5px 12px', border: '1px solid rgba(63,255,0,.3)', borderRadius: 999, background: 'rgba(63,255,0,.06)', alignSelf: 'flex-start' },
  dot: { width: 6, height: 6, borderRadius: 999, background: '#3fff00', boxShadow: '0 0 8px #3fff00' },
  h1: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 48, lineHeight: 1.05, fontWeight: 700, letterSpacing: '-.035em', marginBottom: 16 },
  neon: { color: '#3fff00' },
  p: { fontSize: 15, color: '#9199a8', lineHeight: 1.6, marginBottom: 32, fontFamily: "'Inter', sans-serif" },
  iso: { marginTop: 8, maxWidth: 420 },
  bottom: { position: 'relative', zIndex: 1, paddingTop: 24, borderTop: '1px solid #1c202a' },
  quote: { fontSize: 14, color: '#c4cad6', lineHeight: 1.55, fontFamily: "'Inter', sans-serif", marginBottom: 14, maxWidth: 440 },
  attrib: { display: 'flex', alignItems: 'center', gap: 10 },
  avatar: { width: 32, height: 32, borderRadius: 999, background: 'linear-gradient(135deg,#3fff00,#2ecc00)', color: '#0a1a00', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: 13 },
  name: { fontSize: 12.5, color: '#e5e7eb', fontWeight: 600, fontFamily: "'Inter', sans-serif" },
  role: { fontSize: 11, color: '#9199a8', fontFamily: "'Inter', sans-serif", marginTop: 1 },
};
window.LoginLeft = LoginLeft;
