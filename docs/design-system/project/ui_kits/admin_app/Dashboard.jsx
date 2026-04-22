function Dashboard() {
  return (
    <div>
      <TrialBanner daysLeft={3}/>
      <StatCards/>

      <div style={dbStyle.grid2}>
        <VolumeChart/>
        <CoBreakdown/>
      </div>

      <div style={dbStyle.bottomGrid}>
        <TransfersTable compact/>
        <AchCard/>
      </div>
    </div>
  );
}

function VolumeChart() {
  // 14 days of volume
  const data = [6.2, 7.8, 5.4, 9.1, 8.3, 10.2, 7.6, 11.4, 9.8, 12.1, 10.6, 13.2, 11.8, 12.48];
  const labels = ['Mar 1','','3','','5','','7','','9','','11','','13','14'];
  const max = Math.max(...data);
  const w = 680, h = 180, pad = 32;
  const innerW = w - pad * 2, innerH = h - pad;

  const points = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * innerW;
    const y = pad + innerH - (v / max) * innerH;
    return [x, y];
  });
  const line = points.map((p, i) => (i === 0 ? `M ${p[0]} ${p[1]}` : `L ${p[0]} ${p[1]}`)).join(' ');
  const area = `${line} L ${points[points.length-1][0]} ${pad + innerH} L ${points[0][0]} ${pad + innerH} Z`;

  return (
    <div style={dbStyle.card}>
      <div style={dbStyle.cardHead}>
        <div>
          <div style={dbStyle.eyebrow}>// VOLUME · LAST 14 DAYS</div>
          <div style={dbStyle.cardTitle}>Money-transfer volume</div>
        </div>
        <div style={dbStyle.headStats}>
          <div><div style={dbStyle.hsLabel}>TOTAL</div><div style={dbStyle.hsVal}>$135,920</div></div>
          <div><div style={dbStyle.hsLabel}>AVG/DAY</div><div style={dbStyle.hsVal}>$9,708</div></div>
          <div><div style={dbStyle.hsLabel}>PEAK</div><div style={{...dbStyle.hsVal, color: '#3fff00'}}>$13,200</div></div>
        </div>
      </div>
      <div style={{padding: '16px 22px 22px'}}>
        <svg viewBox={`0 0 ${w} ${h}`} style={{width: '100%', height: 'auto'}}>
          <defs>
            <linearGradient id="vcArea" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#3fff00" stopOpacity=".35"/>
              <stop offset="1" stopColor="#3fff00" stopOpacity="0"/>
            </linearGradient>
          </defs>
          {[0, 0.25, 0.5, 0.75, 1].map((t, i) => (
            <line key={i} x1={pad} x2={w - pad} y1={pad + t * innerH} y2={pad + t * innerH} stroke="#1c202a" strokeDasharray="2 4"/>
          ))}
          <path d={area} fill="url(#vcArea)"/>
          <path d={line} fill="none" stroke="#3fff00" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{filter: 'drop-shadow(0 0 6px #3fff00)'}}/>
          {points.map((p, i) => (i % 2 === 0 || i === points.length - 1) && (
            <circle key={i} cx={p[0]} cy={p[1]} r={i === points.length - 1 ? 4 : 2.5} fill="#0b0d12" stroke="#3fff00" strokeWidth="1.5"/>
          ))}
          {labels.map((l, i) => l && (
            <text key={i} x={pad + (i / (data.length - 1)) * innerW} y={h - 4} fill="#6b7280" fontSize="10" fontFamily="JetBrains Mono" textAnchor="middle">{l}</text>
          ))}
        </svg>
      </div>
    </div>
  );
}

function CoBreakdown() {
  const cos = [
    { name: 'Intermex', color: '#5ea9ff', count: 142, total: 38420, pct: 38 },
    { name: 'Maxi', color: '#b48cff', count: 88, total: 52180, pct: 52 },
    { name: 'Barri', color: '#4dd8e6', count: 56, total: 9830, pct: 10 },
  ];
  const total = cos.reduce((a, c) => a + c.total, 0);
  return (
    <div style={dbStyle.card}>
      <div style={dbStyle.cardHead}>
        <div>
          <div style={dbStyle.eyebrow}>// BY COMPANY · MAR</div>
          <div style={dbStyle.cardTitle}>Transfer breakdown</div>
        </div>
      </div>
      <div style={{padding: '18px 22px 22px'}}>
        {/* Stacked bar */}
        <div style={{display: 'flex', height: 10, borderRadius: 999, overflow: 'hidden', border: '1px solid #1c202a', marginBottom: 20}}>
          {cos.map(c => (
            <div key={c.name} style={{width: `${c.pct}%`, background: c.color, boxShadow: `inset 0 0 10px ${c.color}66`}}/>
          ))}
        </div>
        {cos.map(c => (
          <div key={c.name} style={{display: 'grid', gridTemplateColumns: '14px 1fr auto auto', gap: 12, alignItems: 'center', padding: '10px 0', borderBottom: '1px solid #1c202a'}}>
            <span style={{width: 8, height: 8, borderRadius: 2, background: c.color}}/>
            <div>
              <div style={{color: '#e5e7eb', fontSize: 13, fontWeight: 500}}>{c.name}</div>
              <div style={{color: '#6b7280', fontSize: 11, fontFamily: "'JetBrains Mono', monospace"}}>{c.count} transfers</div>
            </div>
            <div style={{textAlign: 'right'}}>
              <div style={{color: '#e5e7eb', fontSize: 13, fontFamily: "'JetBrains Mono', monospace", fontVariantNumeric: 'tabular-nums'}}>${c.total.toLocaleString()}</div>
              <div style={{color: '#6b7280', fontSize: 10.5, fontFamily: "'JetBrains Mono', monospace"}}>{c.pct}%</div>
            </div>
          </div>
        ))}
        <div style={{display: 'flex', justifyContent: 'space-between', paddingTop: 14, marginTop: 4}}>
          <span style={{fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6b7280', letterSpacing: 1}}>TOTAL MONTH</span>
          <span style={{fontFamily: "'Space Grotesk', sans-serif", fontSize: 20, color: '#3fff00', fontWeight: 600, fontVariantNumeric: 'tabular-nums'}}>${total.toLocaleString()}</span>
        </div>
      </div>
    </div>
  );
}

function AchCard() {
  const rows = [
    { date: '03/12', co: 'Intermex', amount: 6420.00, status: 'clear' },
    { date: '03/10', co: 'Maxi', amount: 5830.00, status: 'clear' },
    { date: '03/08', co: 'Intermex', amount: 4210.00, status: 'variance' },
    { date: '03/06', co: 'Barri', amount: 1840.00, status: 'clear' },
  ];
  return (
    <div style={dbStyle.card}>
      <div style={dbStyle.cardHead}>
        <div>
          <div style={dbStyle.eyebrow}>// RECONCILIATION</div>
          <div style={dbStyle.cardTitle}>Recent ACH batches</div>
        </div>
        <a href="#" style={dbStyle.linkBtn}>All batches →</a>
      </div>
      <div>
        {rows.map((r, i) => {
          const isVar = r.status === 'variance';
          return (
            <div key={i} style={{padding: '12px 22px', borderTop: '1px solid #1c202a', display: 'grid', gridTemplateColumns: '60px 1fr auto auto', gap: 14, alignItems: 'center'}}>
              <span style={{fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#9199a8'}}>{r.date}</span>
              <span style={{fontSize: 13, color: '#e5e7eb', fontWeight: 500}}>{r.co}</span>
              <span style={{fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color: '#e5e7eb', textAlign: 'right', fontVariantNumeric: 'tabular-nums'}}>
                ${r.amount.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
              </span>
              <span style={{display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 8px', borderRadius: 999, fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: .5,
                ...(isVar
                  ? {background: 'rgba(255,77,109,.1)', color: '#ff4d6d', border: '1px solid rgba(255,77,109,.3)'}
                  : {background: 'rgba(63,255,0,.1)', color: '#3fff00', border: '1px solid rgba(63,255,0,.3)'})
              }}>
                <span style={{width: 4, height: 4, borderRadius: 999, background: isVar ? '#ff4d6d' : '#3fff00'}}/>
                {isVar ? 'variance' : 'clear'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const dbStyle = {
  grid2: { display: 'grid', gridTemplateColumns: '1.55fr 1fr', gap: 16, marginBottom: 16 },
  bottomGrid: { display: 'grid', gridTemplateColumns: '1.55fr 1fr', gap: 16 },
  card: { background: '#0e1117', border: '1px solid #272c38', borderRadius: 14, overflow: 'hidden', fontFamily: "'Inter', sans-serif" },
  cardHead: { padding: '18px 22px', borderBottom: '1px solid #1c202a', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' },
  eyebrow: { fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#3fff00', letterSpacing: 1.5, marginBottom: 4 },
  cardTitle: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 16, color: '#e5e7eb', fontWeight: 600, letterSpacing: '-.01em' },
  headStats: { display: 'flex', gap: 24 },
  hsLabel: { fontFamily: "'JetBrains Mono', monospace", fontSize: 9.5, color: '#6b7280', letterSpacing: 1, marginBottom: 2 },
  hsVal: { fontFamily: "'JetBrains Mono', monospace", fontSize: 14, color: '#e5e7eb', fontWeight: 600, fontVariantNumeric: 'tabular-nums' },
  linkBtn: { padding: '6px 12px', borderRadius: 8, border: '1px solid #272c38', color: '#9199a8', textDecoration: 'none', fontSize: 12, background: '#0b0d12' },
};
window.Dashboard = Dashboard;
