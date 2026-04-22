const NAV_GROUPS = [
  { label: 'Workspace', items: [
    { id: 'dashboard', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>), text: 'Dashboard' },
    { id: 'transfers', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>), text: 'Transfers' },
    { id: 'new_transfer', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>), text: 'New Transfer' },
  ]},
  { label: 'Books', items: [
    { id: 'daily', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>), text: 'Daily Book' },
    { id: 'monthly', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>), text: 'Monthly P&L' },
    { id: 'batches', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>), text: 'ACH Batches' },
  ]},
  { label: 'Finance', items: [
    { id: 'bank', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>), text: 'Bank Sync' },
    { id: 'billing', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>), text: 'Billing' },
  ]},
  { label: 'Account', items: [
    { id: 'team', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>), text: 'Team' },
    { id: 'referrals', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 20h20L12 4 2 20z"/></svg>), text: 'Referrals' },
    { id: 'settings', icon: (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>), text: 'Settings' },
  ]},
];

function Sidebar({ current, onNav }) {
  return (
    <aside style={sbStyle.sidebar}>
      <div style={sbStyle.logo}>
        <div style={sbStyle.brandRow}>
          <div style={sbStyle.mark}><span style={sbStyle.markD}>$</span></div>
          <span style={sbStyle.brand}>DineroBook</span>
        </div>
      </div>
      <div style={sbStyle.user}>
        <div style={sbStyle.avatar}>MG</div>
        <div style={{minWidth: 0, flex: 1}}>
          <div style={sbStyle.uname}>María González</div>
          <div style={sbStyle.urole}>Taquería El Sol</div>
        </div>
        <span style={sbStyle.planPill}>PRO</span>
      </div>
      <nav style={sbStyle.nav}>
        {NAV_GROUPS.map(g => (
          <div key={g.label}>
            <div style={sbStyle.sectionLabel}>{g.label}</div>
            {g.items.map(it => {
              const active = it.id === current;
              return (
                <a key={it.id} href="#" onClick={(e) => { e.preventDefault(); onNav(it.id); }} style={{...sbStyle.link, ...(active ? sbStyle.linkActive : {})}}>
                  <span style={{...sbStyle.icon, color: active ? '#3fff00' : '#6b7280'}}>{it.icon}</span>
                  <span>{it.text}</span>
                  {active && <span style={sbStyle.activeDot}/>}
                </a>
              );
            })}
          </div>
        ))}
      </nav>
      <div style={sbStyle.footer}>
        <div style={sbStyle.statusRow}>
          <span style={sbStyle.statusDot}/>
          <span style={sbStyle.statusText}>All systems operational</span>
        </div>
      </div>
    </aside>
  );
}

const sbStyle = {
  sidebar: { width: 240, background: '#0b0d12', borderRight: '1px solid #1c202a', display: 'flex', flexDirection: 'column', position: 'fixed', top: 0, left: 0, height: '100vh', zIndex: 100, overflowY: 'auto', fontFamily: "'Inter', sans-serif" },
  logo: { padding: '20px', borderBottom: '1px solid #1c202a' },
  brandRow: { display: 'flex', alignItems: 'center', gap: 10 },
  mark: { width: 28, height: 28, borderRadius: 8, background: '#3fff00', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 16px rgba(63,255,0,.35)' },
  markD: { fontFamily: "'Space Grotesk', sans-serif", color: '#0a1a00', fontWeight: 700, fontSize: 17 },
  brand: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 16, color: '#e5e7eb', fontWeight: 600, letterSpacing: '-.02em' },
  user: { padding: '14px 16px', borderBottom: '1px solid #1c202a', display: 'flex', alignItems: 'center', gap: 10 },
  avatar: { width: 30, height: 30, borderRadius: 8, background: 'linear-gradient(135deg,#3fff00,#2ecc00)', color: '#0a1a00', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: 11, flexShrink: 0 },
  uname: { fontSize: 12.5, color: '#e5e7eb', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  urole: { fontSize: 11, color: '#6b7280', marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  planPill: { fontFamily: "'JetBrains Mono', monospace", fontSize: 9, color: '#3fff00', padding: '2px 6px', border: '1px solid rgba(63,255,0,.35)', borderRadius: 4, background: 'rgba(63,255,0,.06)', letterSpacing: 1 },
  nav: { flex: 1, padding: '8px 0' },
  sectionLabel: { fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#4a5162', letterSpacing: 1.5, textTransform: 'uppercase', padding: '14px 20px 6px', fontWeight: 500 },
  link: { display: 'flex', alignItems: 'center', gap: 10, padding: '9px 18px', color: '#9199a8', textDecoration: 'none', fontSize: 13, fontWeight: 500, cursor: 'pointer', position: 'relative', transition: 'color .1s, background .1s' },
  linkActive: { color: '#e5e7eb', background: 'linear-gradient(90deg, rgba(63,255,0,.08), transparent 60%)' },
  icon: { width: 18, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' },
  activeDot: { position: 'absolute', left: 0, top: '50%', transform: 'translateY(-50%)', width: 3, height: 18, background: '#3fff00', borderRadius: '0 2px 2px 0', boxShadow: '0 0 10px #3fff00' },
  footer: { padding: '14px 18px', borderTop: '1px solid #1c202a' },
  statusRow: { display: 'flex', alignItems: 'center', gap: 8 },
  statusDot: { width: 6, height: 6, borderRadius: 999, background: '#3fff00', boxShadow: '0 0 8px #3fff00' },
  statusText: { fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#9199a8', letterSpacing: .5 },
};
window.Sidebar = Sidebar;
