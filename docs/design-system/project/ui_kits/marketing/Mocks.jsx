// Pixel-perfect mini UI mockups shown alongside each feature row

const card = { background: '#0e1117', border: '1px solid #272c38', borderRadius: 16, overflow: 'hidden', fontFamily: "'Inter', sans-serif" };
const header = { padding: '14px 18px', borderBottom: '1px solid #1c202a', display: 'flex', alignItems: 'center', justifyContent: 'space-between' };
const label = { fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#9199a8', letterSpacing: '1.5px', textTransform: 'uppercase' };
const mono = { fontFamily: "'JetBrains Mono', monospace", fontVariantNumeric: 'tabular-nums' };

function MockDailyBook() {
  return (
    <div style={card}>
      <div style={header}>
        <span style={label}>DAILY BOOK · MAR 14</span>
        <span style={{...mono, fontSize: 10, color: '#3fff00', padding: '2px 8px', border: '1px solid rgba(63,255,0,.4)', borderRadius: 4, background: 'rgba(63,255,0,.08)'}}>SAVED</span>
      </div>
      <div style={{padding: 20}}>
        <div style={{fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#3fff00', letterSpacing: 1.5, marginBottom: 10}}>CASH FLOW</div>
        {[
          ['Cash In', '$4,200.00', '#e5e7eb'],
          ['Cash Out', '$3,850.00', '#e5e7eb'],
          ['Net', '+$350.00', '#3fff00'],
        ].map((r, i) => (
          <div key={i} style={{display: 'flex', justifyContent: 'space-between', padding: '9px 0', borderBottom: i < 2 ? '1px solid #1c202a' : 'none', fontSize: 13, color: r[2]}}>
            <span style={{color: '#9199a8'}}>{r[0]}</span>
            <span style={{...mono, fontWeight: i === 2 ? 600 : 500, color: r[2]}}>{r[1]}</span>
          </div>
        ))}
        <div style={{fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#9199a8', letterSpacing: 1.5, margin: '20px 0 10px'}}>SALES &amp; SERVICES</div>
        {[
          ['Store sales', '$620.00'],
          ['Money orders', '$1,100.00'],
          ['Check cashing', '$280.00'],
        ].map((r, i) => (
          <div key={i} style={{display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: i < 2 ? '1px solid #1c202a' : 'none', fontSize: 13}}>
            <span style={{color: '#9199a8'}}>{r[0]}</span>
            <span style={{...mono, color: '#e5e7eb'}}>{r[1]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MockTransfers() {
  const rows = [
    ['03/14 14:22', 'Maria Gonzalez', 'Inter', '$450.00', 'sent'],
    ['03/14 13:08', 'Luis Vargas', 'Maxi', '$1,200.00', 'pending'],
    ['03/14 11:45', 'Ana Ramirez', 'Barri', '$85.00', 'sent'],
    ['03/14 10:12', 'Sofia Reyes', 'Maxi', '$550.00', 'sent'],
    ['03/14 09:30', 'Diego Flores', 'Inter', '$180.00', 'sent'],
  ];
  const co = { Inter: '#5ea9ff', Maxi: '#b48cff', Barri: '#4dd8e6' };
  return (
    <div style={card}>
      <div style={header}>
        <span style={label}>TRANSFERS · TODAY</span>
        <div style={{display: 'flex', gap: 4, background: '#0b0d12', border: '1px solid #1c202a', borderRadius: 8, padding: 2}}>
          {['All', 'Sent', 'Pending'].map((t, i) => (
            <span key={t} style={{padding: '4px 10px', borderRadius: 5, fontSize: 10.5, ...mono, color: i === 0 ? '#0a1a00' : '#9199a8', background: i === 0 ? '#3fff00' : 'transparent'}}>{t}</span>
          ))}
        </div>
      </div>
      <div style={{padding: '4px 0'}}>
        {rows.map((r, i) => (
          <div key={i} style={{display: 'grid', gridTemplateColumns: '80px 1fr 50px 80px 60px', gap: 12, padding: '11px 18px', fontSize: 12, alignItems: 'center', borderBottom: i < rows.length - 1 ? '1px solid #1c202a' : 'none'}}>
            <span style={{...mono, color: '#6b7280', fontSize: 11}}>{r[0]}</span>
            <span style={{color: '#e5e7eb'}}>{r[1]}</span>
            <span style={{color: co[r[2]], fontWeight: 600}}>{r[2]}</span>
            <span style={{...mono, color: '#e5e7eb', textAlign: 'right'}}>{r[3]}</span>
            <span style={{justifySelf: 'end', padding: '2px 7px', borderRadius: 999, fontSize: 9.5, fontWeight: 600, ...(r[4] === 'sent' ? {background: 'rgba(63,255,0,.12)', color: '#3fff00', border: '1px solid rgba(63,255,0,.3)'} : {background: 'rgba(255,176,32,.12)', color: '#ffb020', border: '1px solid rgba(255,176,32,.3)'})}}>● {r[4]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MockACH() {
  return (
    <div style={card}>
      <div style={header}>
        <span style={label}>ACH BATCH · MAR 12</span>
        <span style={{...mono, fontSize: 10, color: '#ff4d6d', padding: '2px 8px', border: '1px solid rgba(255,77,109,.4)', borderRadius: 4, background: 'rgba(255,77,109,.08)'}}>VARIANCE</span>
      </div>
      <div style={{padding: 20}}>
        <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20}}>
          <div>
            <div style={{fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#9199a8', letterSpacing: 1.2, marginBottom: 6}}>YOUR LOG</div>
            <div style={{...mono, fontSize: 24, color: '#e5e7eb', fontWeight: 500}}>$6,420.00</div>
            <div style={{...mono, fontSize: 11, color: '#9199a8', marginTop: 4}}>14 transfers</div>
          </div>
          <div>
            <div style={{fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#9199a8', letterSpacing: 1.2, marginBottom: 6}}>BATCH RECEIVED</div>
            <div style={{...mono, fontSize: 24, color: '#e5e7eb', fontWeight: 500}}>$6,398.00</div>
            <div style={{...mono, fontSize: 11, color: '#9199a8', marginTop: 4}}>Intermex</div>
          </div>
        </div>
        <div style={{background: 'rgba(255,77,109,.08)', border: '1px solid rgba(255,77,109,.3)', borderRadius: 10, padding: '12px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between'}}>
          <div>
            <div style={{fontSize: 12, color: '#ff4d6d', fontWeight: 600}}>Variance detected</div>
            <div style={{fontSize: 11, color: '#9199a8', marginTop: 2}}>$22.00 short · 1 transfer missing</div>
          </div>
          <span style={{...mono, fontSize: 18, color: '#ff4d6d'}}>−$22.00</span>
        </div>
      </div>
    </div>
  );
}

function MockPL() {
  const rows = [
    ['Transfer fees', 3420, '#3fff00'],
    ['Check cashing', 2180, '#3fff00'],
    ['Money order margin', 960, '#3fff00'],
    ['Store sales', 1840, '#3fff00'],
    ['— Rent', -2400, '#ff4d6d'],
    ['— Utilities', -320, '#ff4d6d'],
    ['— Payroll', -3200, '#ff4d6d'],
  ];
  const net = rows.reduce((a, r) => a + r[1], 0);
  const max = 3420;
  return (
    <div style={card}>
      <div style={header}>
        <span style={label}>P&amp;L · MARCH 2026</span>
        <span style={{...mono, fontSize: 10, color: '#9199a8'}}>AUTO-SYNCED</span>
      </div>
      <div style={{padding: 20}}>
        {rows.map((r, i) => {
          const w = Math.abs(r[1]) / max * 100;
          const neg = r[1] < 0;
          return (
            <div key={i} style={{padding: '6px 0'}}>
              <div style={{display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 4}}>
                <span style={{color: '#c4cad6'}}>{r[0]}</span>
                <span style={{...mono, color: r[2]}}>{neg ? '' : '+'}${Math.abs(r[1]).toLocaleString()}</span>
              </div>
              <div style={{height: 4, background: '#1c202a', borderRadius: 2, overflow: 'hidden'}}>
                <div style={{width: `${w}%`, height: '100%', background: r[2], opacity: neg ? .5 : 1, boxShadow: neg ? 'none' : '0 0 8px rgba(63,255,0,.5)'}}/>
              </div>
            </div>
          );
        })}
        <div style={{display: 'flex', justifyContent: 'space-between', padding: '16px 0 0', marginTop: 10, borderTop: '1px solid #272c38'}}>
          <span style={{color: '#e5e7eb', fontWeight: 600, fontSize: 13}}>Net income</span>
          <span style={{...mono, color: '#3fff00', fontWeight: 600, fontSize: 18}}>+${net.toLocaleString()}</span>
        </div>
      </div>
    </div>
  );
}

function MockBankSync() {
  return (
    <div style={card}>
      <div style={header}>
        <span style={label}>BANK SYNC · LIVE</span>
        <span style={{...mono, fontSize: 10, color: '#3fff00', display: 'inline-flex', alignItems: 'center', gap: 6}}>
          <span style={{width: 6, height: 6, borderRadius: 999, background: '#3fff00', boxShadow: '0 0 8px #3fff00'}}/> CONNECTED
        </span>
      </div>
      <div style={{padding: 20}}>
        {[
          ['Chase · Operating', 28410, 28432, 'ok'],
          ['BofA · Deposits', 12080, 12080, 'ok'],
          ['Wells · Reserve', 5200, 5180, 'drift'],
        ].map((a, i) => {
          const drift = a[3] === 'drift';
          return (
            <div key={i} style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 0', borderBottom: i < 2 ? '1px solid #1c202a' : 'none'}}>
              <div>
                <div style={{fontSize: 13, color: '#e5e7eb', fontWeight: 500}}>{a[0]}</div>
                <div style={{...mono, fontSize: 11, color: '#9199a8', marginTop: 3}}>book ${a[1].toLocaleString()}.00 · bank ${a[2].toLocaleString()}.00</div>
              </div>
              <div style={{textAlign: 'right'}}>
                <div style={{...mono, fontSize: 18, color: '#e5e7eb', fontWeight: 500}}>${a[2].toLocaleString()}</div>
                <div style={{...mono, fontSize: 10, color: drift ? '#ff4d6d' : '#3fff00', marginTop: 3}}>{drift ? '△ $20 drift' : '● matched'}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

Object.assign(window, { MockDailyBook, MockTransfers, MockACH, MockPL, MockBankSync });
