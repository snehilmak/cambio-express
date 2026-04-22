function TrialBanner({ daysLeft = 3 }) {
  if (daysLeft > 7) return null;
  const over = daysLeft <= 0;
  const msg = over
    ? 'Your free trial has ended. Upgrade now to keep full access.'
    : <>Your free trial ends in <strong style={{color: '#3fff00'}}>{daysLeft} day{daysLeft === 1 ? '' : 's'}</strong> — keep your daily books.</>;
  return (
    <div style={tbbStyle.bar}>
      <div style={tbbStyle.left}>
        <span style={tbbStyle.dot}/>
        <span style={tbbStyle.msg}>{msg}</span>
      </div>
      <a href="#" style={tbbStyle.cta}>{over ? 'Upgrade now →' : 'Choose a plan →'}</a>
    </div>
  );
}
const tbbStyle = {
  bar: { background: 'linear-gradient(90deg, rgba(63,255,0,.08), rgba(63,255,0,.02))', border: '1px solid rgba(63,255,0,.3)', borderRadius: 12, padding: '12px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, fontFamily: "'Inter', sans-serif", marginBottom: 20 },
  left: { display: 'flex', alignItems: 'center', gap: 12 },
  dot: { width: 8, height: 8, borderRadius: 999, background: '#3fff00', boxShadow: '0 0 10px #3fff00', flexShrink: 0 },
  msg: { fontSize: 13.5, color: '#c4cad6' },
  cta: { padding: '7px 14px', borderRadius: 8, background: '#3fff00', color: '#0a1a00', textDecoration: 'none', fontSize: 12.5, fontWeight: 600, fontFamily: "'Inter', sans-serif", whiteSpace: 'nowrap' },
};
window.TrialBanner = TrialBanner;
