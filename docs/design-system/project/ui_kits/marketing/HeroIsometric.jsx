// Isometric 3D-style hero illustration: a stack of floating product "panes"
// (daily book, transfers, P&L, bank sync) with neon edges and glow.
function HeroIsometric() {
  return (
    <div style={{position: 'relative', width: '100%', aspectRatio: '1.25 / 1', maxWidth: 560, margin: '0 auto'}}>
      <svg viewBox="0 0 560 450" style={{width: '100%', height: '100%', overflow: 'visible'}}>
        <defs>
          <linearGradient id="pane" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="#161920"/>
            <stop offset="1" stopColor="#0e1117"/>
          </linearGradient>
          <linearGradient id="paneHi" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="#1c202a"/>
            <stop offset="1" stopColor="#11141b"/>
          </linearGradient>
          <filter id="neonglow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>

        {/* Floor glow */}
        <ellipse cx="280" cy="410" rx="200" ry="22" fill="#3fff00" opacity=".15" filter="url(#neonglow)"/>

        {/* Pane 3 — BACK (Monthly P&L) */}
        <g transform="translate(0,0)">
          <path d="M 130 80 L 420 40 L 540 80 L 250 120 Z" fill="url(#paneHi)" stroke="#272c38"/>
          <path d="M 130 80 L 250 120 L 250 170 L 130 130 Z" fill="#0b0d12" stroke="#272c38"/>
          <path d="M 540 80 L 250 120 L 250 170 L 540 130 Z" fill="url(#pane)" stroke="#272c38"/>
          {/* bars on P&L */}
          <g transform="translate(270,70)">
            <rect x="0" y="10" width="18" height="26" fill="#3fff00" opacity=".35" transform="skewY(18)"/>
            <rect x="30" y="4" width="18" height="32" fill="#3fff00" opacity=".55" transform="skewY(18)"/>
            <rect x="60" y="-4" width="18" height="40" fill="#3fff00" opacity=".8" transform="skewY(18)"/>
            <rect x="90" y="-12" width="18" height="48" fill="#3fff00" transform="skewY(18)" filter="url(#neonglow)"/>
            <rect x="120" y="-8" width="18" height="44" fill="#3fff00" opacity=".9" transform="skewY(18)"/>
            <rect x="150" y="-14" width="18" height="50" fill="#3fff00" filter="url(#neonglow)" transform="skewY(18)"/>
            <rect x="180" y="-20" width="18" height="56" fill="#3fff00" transform="skewY(18)" filter="url(#neonglow)"/>
          </g>
          <text x="145" y="98" fill="#9199a8" fontSize="11" fontFamily="JetBrains Mono">MONTHLY P&amp;L</text>
        </g>

        {/* Pane 2 — MIDDLE (Transfers table) */}
        <g transform="translate(-20,80)">
          <path d="M 110 140 L 400 95 L 520 135 L 230 180 Z" fill="url(#paneHi)" stroke="#363c4a"/>
          <path d="M 110 140 L 230 180 L 230 240 L 110 200 Z" fill="#0b0d12" stroke="#272c38"/>
          <path d="M 520 135 L 230 180 L 230 240 L 520 195 Z" fill="url(#pane)" stroke="#363c4a"/>
          {/* rows */}
          <g transform="translate(245,130)" fontFamily="JetBrains Mono" fontSize="9" fill="#c4cad6">
            <g transform="skewY(-9)">
              <rect x="0" y="0" width="245" height="10" fill="#0b0d12"/>
              <text x="4" y="8" fill="#9199a8">DATE · SENDER · CO · AMT</text>
              <rect x="0" y="14" width="245" height="9" fill="#11141b"/>
              <text x="4" y="21">03/14 Gonzalez Inter $450</text>
              <rect x="0" y="25" width="245" height="9" fill="#0e1117"/>
              <text x="4" y="32">03/14 Vargas Maxi $1,200</text>
              <rect x="0" y="36" width="245" height="9" fill="#11141b"/>
              <text x="4" y="43">03/13 Ramirez Barri $85</text>
              <rect x="0" y="47" width="245" height="9" fill="#0e1117"/>
              <text x="4" y="54" fill="#3fff00">+ 142 more</text>
            </g>
          </g>
        </g>

        {/* Pane 1 — FRONT (Daily Book input) */}
        <g transform="translate(0,170)">
          <path d="M 80 200 L 380 155 L 500 195 L 200 240 Z" fill="url(#paneHi)" stroke="#3fff00" strokeWidth="1" opacity=".95"/>
          <path d="M 80 200 L 200 240 L 200 300 L 80 260 Z" fill="#0b0d12" stroke="#3fff00" strokeWidth="1"/>
          <path d="M 500 195 L 200 240 L 200 300 L 500 255 Z" fill="url(#pane)" stroke="#3fff00" strokeWidth="1"/>

          {/* Input fields */}
          <g transform="translate(215,190)">
            <g transform="skewY(-9)">
              <text x="0" y="8" fontFamily="JetBrains Mono" fontSize="9" fill="#9199a8">DAILY BOOK · MAR 14</text>
              <rect x="0" y="16" width="130" height="14" fill="#0b0d12" stroke="#272c38"/>
              <text x="6" y="26" fontFamily="JetBrains Mono" fontSize="10" fill="#e5e7eb">CASH IN  $4,200.00</text>
              <rect x="140" y="16" width="130" height="14" fill="#0b0d12" stroke="#272c38"/>
              <text x="146" y="26" fontFamily="JetBrains Mono" fontSize="10" fill="#e5e7eb">CASH OUT $3,850.00</text>
              <rect x="0" y="36" width="270" height="14" fill="#0b0d12" stroke="#3fff00"/>
              <text x="6" y="46" fontFamily="JetBrains Mono" fontSize="10" fill="#3fff00">NET      +$350.00</text>
            </g>
          </g>
        </g>

        {/* Floating neon dollar mark - top right */}
        <g transform="translate(440,20)" filter="url(#neonglow)">
          <rect x="0" y="0" width="60" height="60" rx="14" fill="#0b0d12" stroke="#3fff00" strokeWidth="1.5"/>
          <text x="30" y="44" textAnchor="middle" fontFamily="Space Grotesk" fontSize="38" fontWeight="700" fill="#3fff00">$</text>
        </g>

        {/* Floating check - bottom left */}
        <g transform="translate(20,300)" filter="url(#neonglow)">
          <circle cx="26" cy="26" r="22" fill="#0b0d12" stroke="#3fff00" strokeWidth="1.5"/>
          <path d="M 16 27 l 7 7 l 13 -15" stroke="#3fff00" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
        </g>
      </svg>
    </div>
  );
}
window.HeroIsometric = HeroIsometric;
