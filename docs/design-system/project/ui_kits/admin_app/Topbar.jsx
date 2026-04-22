function Topbar({ title }) {
  const today = new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  return (
    <div style={tbStyle.bar}>
      <div>
        <div style={tbStyle.crumb}>WORKSPACE · TAQUERÍA EL SOL</div>
        <div style={tbStyle.title}>{title}</div>
      </div>
      <div style={tbStyle.right}>
        <div style={tbStyle.search}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input placeholder="Search transfers, customers…" style={tbStyle.searchInput}/>
          <kbd style={tbStyle.kbd}>⌘K</kbd>
        </div>
        <span style={tbStyle.date}>{today}</span>
        <button style={tbStyle.iconBtn} aria-label="Notifications">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
          <span style={tbStyle.notifDot}/>
        </button>
        <button style={tbStyle.newBtn}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          New Transfer
        </button>
      </div>
    </div>
  );
}
const tbStyle = {
  bar: { background: '#0b0d12', borderBottom: '1px solid #1c202a', padding: '14px 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', position: 'sticky', top: 0, zIndex: 50, gap: 16 },
  crumb: { fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#4a5162', letterSpacing: 1.2, marginBottom: 4 },
  title: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 20, color: '#e5e7eb', fontWeight: 600, letterSpacing: '-.02em' },
  right: { display: 'flex', alignItems: 'center', gap: 10 },
  search: { display: 'flex', alignItems: 'center', gap: 8, background: '#0e1117', border: '1px solid #1c202a', borderRadius: 10, padding: '7px 12px', width: 280, color: '#6b7280' },
  searchInput: { flex: 1, background: 'transparent', border: 'none', color: '#e5e7eb', fontSize: 13, outline: 'none', fontFamily: "'Inter', sans-serif", minWidth: 0 },
  kbd: { fontFamily: "'JetBrains Mono', monospace", fontSize: 10, padding: '2px 6px', background: '#1c202a', border: '1px solid #272c38', borderRadius: 4, color: '#9199a8' },
  date: { fontSize: 11.5, color: '#6b7280', fontFamily: "'JetBrains Mono', monospace", letterSpacing: .3 },
  iconBtn: { position: 'relative', width: 34, height: 34, borderRadius: 8, border: '1px solid #1c202a', background: '#0e1117', color: '#9199a8', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' },
  notifDot: { position: 'absolute', top: 7, right: 7, width: 6, height: 6, borderRadius: 999, background: '#3fff00', boxShadow: '0 0 8px #3fff00' },
  newBtn: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: '#3fff00', color: '#0a1a00', border: 'none', borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: 'pointer', fontFamily: "'Inter', sans-serif", boxShadow: '0 0 0 1px #3fff00, 0 0 16px rgba(63,255,0,.3)' },
};
window.Topbar = Topbar;
