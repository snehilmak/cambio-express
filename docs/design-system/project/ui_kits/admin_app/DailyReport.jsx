const { useState: useDrState } = React;

function DailyReport() {
  const [cashIn, setCashIn] = useDrState('4200.00');
  const [cashOut, setCashOut] = useDrState('3850.00');
  const [sales, setSales] = useDrState('620.00');
  const [moneyOrders, setMoneyOrders] = useDrState('1100.00');
  const [checkCashing, setCheckCashing] = useDrState('280.00');
  const [notes, setNotes] = useDrState('');

  const net = (parseFloat(cashIn) || 0) - (parseFloat(cashOut) || 0);

  return (
    <div>
      <Section accent="#3fff00" num="01" title="Cash Flow" sub="What moved through the register today">
        <div style={drStyle.row}>
          <Field label="Cash In" value={cashIn} set={setCashIn}/>
          <Field label="Cash Out" value={cashOut} set={setCashOut}/>
        </div>
        <div style={drStyle.totals}>
          <span style={drStyle.totalsLabel}>NET</span>
          <span style={{...drStyle.totalsValue, color: net >= 0 ? '#3fff00' : '#ff4d6d'}}>
            {net >= 0 ? '+' : ''}${net.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
          </span>
        </div>
      </Section>

      <Section accent="#5ea9ff" num="02" title="Sales & Services" sub="Non-transfer revenue">
        <div style={drStyle.row}>
          <Field label="Store Sales" value={sales} set={setSales}/>
          <Field label="Money Orders" value={moneyOrders} set={setMoneyOrders}/>
          <Field label="Check Cashing" value={checkCashing} set={setCheckCashing}/>
        </div>
      </Section>

      <Section accent="#b48cff" num="03" title="Notes" sub="Anything unusual about today">
        <textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="Power out for 20 min in the afternoon…" style={drStyle.textarea}/>
      </Section>

      <div style={drStyle.saveBar}>
        <div style={drStyle.saveStatus}>
          <span style={drStyle.saveDot}/>
          <span style={{fontSize: 12.5, color: '#9199a8'}}>Auto-saved · 2m ago</span>
        </div>
        <div style={{display: 'flex', gap: 10}}>
          <button style={drStyle.outlineBtn}>Reset</button>
          <button style={drStyle.primaryBtn}>Save report →</button>
        </div>
      </div>
    </div>
  );
}

function Section({ accent, num, title, sub, children }) {
  return (
    <div style={drStyle.section}>
      <div style={drStyle.sectionHeader}>
        <div style={{...drStyle.accentBar, background: accent, boxShadow: `0 0 12px ${accent}`}}/>
        <div style={{display: 'flex', alignItems: 'baseline', gap: 14}}>
          <span style={{...drStyle.num, color: accent}}>{num}</span>
          <div>
            <div style={drStyle.sectionTitle}>{title}</div>
            <div style={drStyle.sectionSub}>{sub}</div>
          </div>
        </div>
      </div>
      <div style={drStyle.sectionBody}>{children}</div>
    </div>
  );
}

function Field({ label, value, set }) {
  const [focused, setFocused] = useDrState(false);
  return (
    <div style={drStyle.field}>
      <label style={drStyle.label}>{label}</label>
      <div style={{position: 'relative'}}>
        <span style={drStyle.currency}>$</span>
        <input
          type="text"
          value={value}
          onChange={e => set(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={{...drStyle.input, ...(focused ? drStyle.inputFocus : {})}}
        />
      </div>
    </div>
  );
}

const drStyle = {
  section: { background: '#0e1117', border: '1px solid #272c38', borderRadius: 14, marginBottom: 16, overflow: 'hidden', fontFamily: "'Inter', sans-serif" },
  sectionHeader: { padding: '18px 22px', borderBottom: '1px solid #1c202a', position: 'relative', background: 'linear-gradient(180deg, #11141b, #0e1117)' },
  accentBar: { position: 'absolute', left: 0, top: 0, bottom: 0, width: 3 },
  num: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, fontWeight: 600, letterSpacing: 1.5 },
  sectionTitle: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 17, color: '#e5e7eb', fontWeight: 600, lineHeight: 1.2, letterSpacing: '-.01em' },
  sectionSub: { fontSize: 12, color: '#6b7280', marginTop: 3 },
  sectionBody: { padding: 22 },
  row: { display: 'flex', gap: 14, flexWrap: 'wrap' },
  field: { flex: '1 1 180px', minWidth: 0 },
  label: { display: 'block', fontSize: 10.5, fontWeight: 500, color: '#6b7280', fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1.3, marginBottom: 6, textTransform: 'uppercase' },
  currency: { position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#6b7280', fontFamily: "'JetBrains Mono', monospace", fontSize: 13 },
  input: { width: '100%', padding: '11px 14px 11px 24px', border: '1px solid #272c38', borderRadius: 10, fontSize: 14, color: '#e5e7eb', background: '#0b0d12', fontFamily: "'JetBrains Mono', monospace", textAlign: 'right', outline: 'none', transition: 'all .15s', fontVariantNumeric: 'tabular-nums' },
  inputFocus: { borderColor: '#3fff00', boxShadow: '0 0 0 3px rgba(63,255,0,.15)' },
  textarea: { width: '100%', minHeight: 90, padding: '11px 14px', border: '1px solid #272c38', borderRadius: 10, fontSize: 14, fontFamily: "'Inter', sans-serif", color: '#e5e7eb', background: '#0b0d12', resize: 'vertical', outline: 'none' },
  totals: { marginTop: 18, padding: '14px 16px', background: '#0b0d12', border: '1px solid #272c38', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  totalsLabel: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6b7280', letterSpacing: 1.5, fontWeight: 500 },
  totalsValue: { fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 600, fontVariantNumeric: 'tabular-nums' },
  saveBar: { position: 'sticky', bottom: 0, background: 'rgba(11,13,18,.9)', backdropFilter: 'blur(10px)', padding: '16px 20px', marginTop: 20, border: '1px solid #1c202a', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  saveStatus: { display: 'flex', alignItems: 'center', gap: 8 },
  saveDot: { width: 6, height: 6, borderRadius: 999, background: '#3fff00', boxShadow: '0 0 8px #3fff00' },
  outlineBtn: { padding: '10px 16px', borderRadius: 8, border: '1px solid #363c4a', color: '#e5e7eb', background: 'transparent', fontSize: 13, fontWeight: 500, cursor: 'pointer', fontFamily: "'Inter', sans-serif" },
  primaryBtn: { padding: '10px 20px', borderRadius: 8, background: '#3fff00', color: '#0a1a00', border: 'none', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: "'Inter', sans-serif", boxShadow: '0 0 0 1px #3fff00, 0 0 20px rgba(63,255,0,.3)' },
};
window.DailyReport = DailyReport;
