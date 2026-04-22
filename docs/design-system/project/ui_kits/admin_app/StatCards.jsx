function StatCards() {
  return (
    <div style={scStyle.grid}>
      <StatCard label="Today · Transfers" value="17" delta="+4" deltaPositive sub="vs yesterday" sparkline={[2,3,2,4,3,5,4,6,5,7]}/>
      <StatCard label="Today · Volume" value="$12,480" delta="+8.2%" deltaPositive sub="Mar 14" sparkline={[5,6,4,7,6,8,7,9,8,10]}/>
      <StatCard label="Month · Net Income" value="$8,432" delta="+$1,120" deltaPositive sub="on track for $14k" highlight/>
      <StatCard label="Unreconciled ACH" value="0" status="ok" sub="All batches clear"/>
      <StatCard label="Bank Sync" valueText="Chase · BofA" status="ok" sub="09:42 AM · auto"/>
      <StatCard label="Daily Book · Today" valueText="Saved" status="ok" sub="María · 2m ago"/>
    </div>
  );
}

function StatCard({ label, value, valueText, delta, deltaPositive, sub, sparkline, status, highlight }) {
  return (
    <div style={{...scStyle.card, ...(highlight ? scStyle.cardHi : {})}}>
      <div style={scStyle.top}>
        <div style={scStyle.label}>{label}</div>
        {status === 'ok' && <span style={scStyle.okDot}/>}
      </div>
      <div style={scStyle.row}>
        <div>
          {value && <div style={{...scStyle.value, color: highlight ? '#3fff00' : '#e5e7eb'}}>{value}</div>}
          {valueText && <div style={scStyle.valueText}>{valueText}</div>}
          <div style={scStyle.subRow}>
            {delta && (
              <span style={{...scStyle.delta, color: deltaPositive ? '#3fff00' : '#ff4d6d'}}>
                {deltaPositive ? '▲' : '▼'} {delta}
              </span>
            )}
            <span style={scStyle.sub}>{sub}</span>
          </div>
        </div>
        {sparkline && <Sparkline data={sparkline} highlight={highlight}/>}
      </div>
    </div>
  );
}

function Sparkline({ data, highlight }) {
  const w = 68, h = 32;
  const max = Math.max(...data), min = Math.min(...data);
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / (max - min || 1)) * h;
    return `${x},${y}`;
  }).join(' ');
  const color = highlight ? '#3fff00' : '#9199a8';
  return (
    <svg width={w} height={h} style={{flexShrink: 0}}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{filter: highlight ? 'drop-shadow(0 0 4px #3fff00)' : 'none'}}/>
    </svg>
  );
}

const scStyle = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12, marginBottom: 24 },
  card: { background: '#0e1117', border: '1px solid #272c38', borderRadius: 14, padding: '18px 18px', fontFamily: "'Inter', sans-serif", position: 'relative', overflow: 'hidden' },
  cardHi: { borderColor: 'rgba(63,255,0,.35)', background: 'linear-gradient(135deg, #0e1117, #11141b)', boxShadow: 'inset 0 0 40px rgba(63,255,0,.04)' },
  top: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  label: { fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1.2, fontFamily: "'JetBrains Mono', monospace", fontWeight: 500 },
  okDot: { width: 6, height: 6, borderRadius: 999, background: '#3fff00', boxShadow: '0 0 8px #3fff00' },
  row: { display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 8 },
  value: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 30, fontWeight: 600, lineHeight: 1, letterSpacing: '-.02em', fontVariantNumeric: 'tabular-nums' },
  valueText: { fontSize: 17, color: '#e5e7eb', fontWeight: 500, lineHeight: 1.1, display: 'flex', alignItems: 'center', gap: 6 },
  subRow: { display: 'flex', alignItems: 'center', gap: 10, marginTop: 8, flexWrap: 'wrap' },
  delta: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, fontWeight: 600 },
  sub: { fontSize: 11.5, color: '#6b7280' },
};
window.StatCards = StatCards;
