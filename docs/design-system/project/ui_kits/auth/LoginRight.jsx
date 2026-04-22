function LoginRight({ onSignIn }) {
  const [u, setU] = React.useState('');
  const [p, setP] = React.useState('');
  const [show, setShow] = React.useState(false);
  const [remember, setRemember] = React.useState(true);
  const submit = (e) => { e.preventDefault(); if (u && p) onSignIn(); };

  return (
    <div style={R.pane}>
      <div style={R.card}>
        <div style={R.status}>
          <span style={R.statusDot}/> <span style={R.statusText}>ALL SYSTEMS OPERATIONAL</span>
        </div>

        <h2 style={R.h2}>Sign in</h2>
        <p style={R.sub}>Welcome back. Pick up where you left off.</p>

        <form onSubmit={submit} style={R.form}>
          <div style={R.field}>
            <label style={R.label}>USERNAME OR EMAIL</label>
            <input
              type="text"
              value={u}
              onChange={e => setU(e.target.value)}
              placeholder="admin@store.com"
              style={R.input}
              autoComplete="username"
            />
          </div>

          <div style={R.field}>
            <div style={R.labelRow}>
              <label style={R.label}>PASSWORD</label>
              <a href="#" style={R.forgot}>Forgot?</a>
            </div>
            <div style={R.passwordWrap}>
              <input
                type={show ? 'text' : 'password'}
                value={p}
                onChange={e => setP(e.target.value)}
                placeholder="••••••••"
                style={R.input}
                autoComplete="current-password"
              />
              <button type="button" onClick={() => setShow(!show)} style={R.eyeBtn} aria-label="Toggle password">
                {show ? '◐' : '○'}
              </button>
            </div>
          </div>

          <label style={R.remember}>
            <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} style={R.checkbox}/>
            <span>Remember this device for 30 days</span>
          </label>

          <button type="submit" style={R.submit}>
            Sign in <span style={{marginLeft: 8}}>→</span>
          </button>
        </form>

        <div style={R.divider}><span style={R.dividerText}>OR CONTINUE WITH</span></div>

        <div style={R.sso}>
          <button style={R.ssoBtn}>
            <svg width="16" height="16" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.5 12.27c0-.79-.07-1.54-.19-2.27H12v4.29h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.22-4.74 3.22-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.24 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.1a6.88 6.88 0 010-4.2V7.06H2.18a11 11 0 000 9.88l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z"/></svg>
            Google
          </button>
          <button style={R.ssoBtn}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="#e5e7eb"><path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.53 4.08zM12 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/></svg>
            Apple
          </button>
        </div>

        <div style={R.switcher}>
          <span style={{color: '#9199a8'}}>New to DineroBook?</span>
          <a href="#" style={R.switcherLink}>Create an account →</a>
        </div>
      </div>

      <div style={R.footer}>
        <div style={R.footerRow}>
          <span style={R.footerItem}><span style={R.lock}>🔒</span> Bank-grade encryption</span>
          <span style={R.footerItem}>SOC 2 · Type II</span>
          <span style={R.footerItem}>99.9% uptime</span>
        </div>
        <div style={R.copyright}>© 2026 DineroBook · <a href="#" style={R.footerLink}>Privacy</a> · <a href="#" style={R.footerLink}>Terms</a></div>
      </div>
    </div>
  );
}

const R = {
  pane: { flex: 1, background: '#0b0d12', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: '40px 32px', position: 'relative' },
  card: { width: '100%', maxWidth: 400, color: '#e5e7eb' },
  status: { display: 'inline-flex', alignItems: 'center', gap: 8, padding: '4px 10px', border: '1px solid #1c202a', borderRadius: 999, background: '#0e1117', marginBottom: 28 },
  statusDot: { width: 6, height: 6, borderRadius: 999, background: '#3fff00', boxShadow: '0 0 8px #3fff00' },
  statusText: { fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#9199a8', letterSpacing: 1.2 },
  h2: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 36, fontWeight: 600, letterSpacing: '-.03em', color: '#e5e7eb', marginBottom: 8 },
  sub: { fontSize: 14, color: '#9199a8', marginBottom: 32, fontFamily: "'Inter', sans-serif" },
  form: {},
  field: { marginBottom: 18 },
  labelRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  label: { display: 'block', fontSize: 10.5, fontWeight: 500, color: '#6b7280', fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1.5, marginBottom: 8, textTransform: 'uppercase' },
  input: { width: '100%', padding: '13px 14px', background: '#0e1117', border: '1px solid #272c38', borderRadius: 10, fontSize: 14, color: '#e5e7eb', fontFamily: "'Inter', sans-serif", outline: 'none', transition: 'border-color .15s, box-shadow .15s' },
  forgot: { fontSize: 12, color: '#3fff00', textDecoration: 'none', fontFamily: "'Inter', sans-serif" },
  passwordWrap: { position: 'relative' },
  eyeBtn: { position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'transparent', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 16, padding: 6 },
  remember: { display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: '#c4cad6', marginBottom: 22, cursor: 'pointer', fontFamily: "'Inter', sans-serif" },
  checkbox: { width: 15, height: 15, accentColor: '#3fff00', cursor: 'pointer' },
  submit: { width: '100%', padding: '14px', background: '#3fff00', color: '#0a1a00', border: 'none', borderRadius: 10, fontSize: 14.5, fontWeight: 600, cursor: 'pointer', fontFamily: "'Inter', sans-serif", letterSpacing: '-.01em', boxShadow: '0 0 0 1px #3fff00, 0 0 28px rgba(63,255,0,.35)', transition: 'transform .1s' },
  divider: { textAlign: 'center', margin: '28px 0 20px', position: 'relative', borderTop: '1px solid #1c202a', height: 1 },
  dividerText: { position: 'absolute', top: -8, left: '50%', transform: 'translateX(-50%)', background: '#0b0d12', padding: '0 12px', fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#6b7280', letterSpacing: 1.5 },
  sso: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 24 },
  ssoBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, padding: '12px', background: '#0e1117', color: '#e5e7eb', border: '1px solid #272c38', borderRadius: 10, fontSize: 13.5, fontWeight: 500, cursor: 'pointer', fontFamily: "'Inter', sans-serif" },
  switcher: { textAlign: 'center', fontSize: 13.5, fontFamily: "'Inter', sans-serif", display: 'flex', justifyContent: 'center', gap: 6, flexWrap: 'wrap' },
  switcherLink: { color: '#3fff00', textDecoration: 'none', fontWeight: 500 },
  footer: { marginTop: 40, textAlign: 'center', fontFamily: "'Inter', sans-serif" },
  footerRow: { display: 'flex', gap: 16, justifyContent: 'center', flexWrap: 'wrap', marginBottom: 10 },
  footerItem: { fontSize: 11.5, color: '#6b7280', display: 'inline-flex', alignItems: 'center', gap: 5 },
  lock: { fontSize: 11 },
  copyright: { fontSize: 11, color: '#4a5162' },
  footerLink: { color: '#6b7280', textDecoration: 'none' },
};
window.LoginRight = LoginRight;
