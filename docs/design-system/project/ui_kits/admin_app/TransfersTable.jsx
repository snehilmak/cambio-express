const { useState: useTTState } = React;

const ALL_TRANSFERS = [
  { date: '03/14 14:22', sender: 'Maria Gonzalez', co: 'Intermex', amount: 450.00, fee: 6.99, status: 'sent', recipient: 'Juan Gonzalez · MX' },
  { date: '03/14 13:08', sender: 'Luis Vargas', co: 'Maxi', amount: 1200.00, fee: 12.00, status: 'pending', recipient: 'Elena Vargas · GT' },
  { date: '03/14 11:45', sender: 'Ana Ramirez', co: 'Barri', amount: 85.00, fee: 3.99, status: 'sent', recipient: 'Pedro Ramirez · SV' },
  { date: '03/13 16:10', sender: 'Carlos Mendez', co: 'Intermex', amount: 320.00, fee: 5.99, status: 'canceled', recipient: 'Rosa Mendez · HN' },
  { date: '03/13 12:30', sender: 'Sofia Reyes', co: 'Maxi', amount: 550.00, fee: 7.99, status: 'sent', recipient: 'Miguel Reyes · MX' },
  { date: '03/12 15:44', sender: 'Diego Flores', co: 'Intermex', amount: 180.00, fee: 4.99, status: 'refunded', recipient: 'Lucia Flores · NI' },
  { date: '03/12 11:18', sender: 'Elena Martinez', co: 'Barri', amount: 95.00, fee: 3.99, status: 'rejected', recipient: 'Jose Martinez · EC' },
  { date: '03/12 09:50', sender: 'Ricardo Torres', co: 'Maxi', amount: 2500.00, fee: 22.00, status: 'sent', recipient: 'Carmen Torres · GT' },
];
window.ALL_TRANSFERS = ALL_TRANSFERS;

const CO_COLOR = { 'Intermex': '#5ea9ff', 'Maxi': '#b48cff', 'Barri': '#4dd8e6' };
const STATUS_STYLE = {
  sent:     { bg: 'rgba(63,255,0,.1)',   color: '#3fff00', border: 'rgba(63,255,0,.3)' },
  pending:  { bg: 'rgba(255,176,32,.1)', color: '#ffb020', border: 'rgba(255,176,32,.3)' },
  canceled: { bg: 'rgba(107,114,128,.1)',color: '#9199a8', border: 'rgba(107,114,128,.3)' },
  rejected: { bg: 'rgba(255,77,109,.1)', color: '#ff4d6d', border: 'rgba(255,77,109,.3)' },
  refunded: { bg: 'rgba(180,140,255,.1)',color: '#b48cff', border: 'rgba(180,140,255,.3)' },
};

function TransfersTable({ compact = false, rows = ALL_TRANSFERS }) {
  const [coFilter, setCoFilter] = useTTState('All');
  const [statusFilter, setStatusFilter] = useTTState('All');
  const filtered = rows.filter(r =>
    (coFilter === 'All' || r.co === coFilter) &&
    (statusFilter === 'All' || r.status === statusFilter)
  );

  return (
    <div style={ttStyle.card}>
      <div style={ttStyle.header}>
        <div>
          <div style={ttStyle.eyebrow}>// LIVE FEED</div>
          <div style={ttStyle.title}>{compact ? 'Recent Transfers' : 'All Transfers'}</div>
        </div>
        {compact ? (
          <a href="#" style={ttStyle.outlineBtn}>View all →</a>
        ) : (
          <div style={{display: 'flex', gap: 8}}>
            <Segmented value={coFilter} onChange={setCoFilter} options={['All', 'Intermex', 'Maxi', 'Barri']}/>
            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={ttStyle.select}>
              <option>All</option><option value="sent">Sent</option><option value="pending">Pending</option><option value="canceled">Canceled</option><option value="rejected">Rejected</option><option value="refunded">Refunded</option>
            </select>
          </div>
        )}
      </div>
      <div style={{overflowX: 'auto'}}>
        <table style={ttStyle.table}>
          <thead>
            <tr>
              <th style={ttStyle.th}>Time</th>
              <th style={ttStyle.th}>Sender</th>
              {!compact && <th style={ttStyle.th}>Recipient</th>}
              <th style={ttStyle.th}>Co.</th>
              <th style={{...ttStyle.th, textAlign: 'right'}}>Amount</th>
              {!compact && <th style={{...ttStyle.th, textAlign: 'right'}}>Fee</th>}
              <th style={ttStyle.th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => {
              const st = STATUS_STYLE[r.status];
              return (
                <tr key={i} style={ttStyle.tr}>
                  <td style={{...ttStyle.td, ...ttStyle.mono, color: '#6b7280', fontSize: 11.5}}>{r.date}</td>
                  <td style={ttStyle.td}>{r.sender}</td>
                  {!compact && <td style={{...ttStyle.td, color: '#9199a8', fontSize: 12.5}}>{r.recipient}</td>}
                  <td style={{...ttStyle.td, color: CO_COLOR[r.co], fontWeight: 600}}>{r.co}</td>
                  <td style={{...ttStyle.td, ...ttStyle.mono, textAlign: 'right', color: '#e5e7eb'}}>${r.amount.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}</td>
                  {!compact && <td style={{...ttStyle.td, ...ttStyle.mono, textAlign: 'right', color: '#9199a8'}}>${r.fee.toFixed(2)}</td>}
                  <td style={ttStyle.td}>
                    <span style={{display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 9px', borderRadius: 999, fontSize: 10.5, fontWeight: 600, background: st.bg, color: st.color, border: `1px solid ${st.border}`, textTransform: 'uppercase', letterSpacing: .5}}>
                      <span style={{width: 5, height: 5, borderRadius: 999, background: st.color}}/>
                      {r.status}
                    </span>
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={compact ? 5 : 7} style={{textAlign: 'center', padding: 32, color: '#6b7280', fontSize: 13}}>No transfers match those filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Segmented({ value, onChange, options }) {
  return (
    <div style={ttStyle.segWrap}>
      {options.map(o => (
        <button key={o} onClick={() => onChange(o)} style={{...ttStyle.seg, ...(value === o ? ttStyle.segActive : {})}}>
          {o}
        </button>
      ))}
    </div>
  );
}
window.Segmented = Segmented;

const ttStyle = {
  card: { background: '#0e1117', border: '1px solid #272c38', borderRadius: 14, overflow: 'hidden', fontFamily: "'Inter', sans-serif" },
  header: { padding: '18px 22px', borderBottom: '1px solid #1c202a', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' },
  eyebrow: { fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#3fff00', letterSpacing: 1.5, marginBottom: 4 },
  title: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 16, color: '#e5e7eb', fontWeight: 600, letterSpacing: '-.01em' },
  outlineBtn: { padding: '6px 12px', borderRadius: 8, border: '1px solid #272c38', color: '#9199a8', textDecoration: 'none', fontSize: 12, background: '#0b0d12' },
  segWrap: { display: 'inline-flex', background: '#0b0d12', border: '1px solid #1c202a', borderRadius: 8, padding: 2, gap: 2 },
  seg: { padding: '5px 11px', borderRadius: 5, fontSize: 11.5, fontFamily: "'Inter', sans-serif", fontWeight: 500, background: 'transparent', color: '#9199a8', border: 'none', cursor: 'pointer' },
  segActive: { background: '#3fff00', color: '#0a1a00', fontWeight: 600 },
  select: { padding: '6px 10px', borderRadius: 8, border: '1px solid #272c38', background: '#0b0d12', fontSize: 12, color: '#e5e7eb', fontFamily: "'Inter', sans-serif" },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: { padding: '10px 18px', textAlign: 'left', fontSize: 10, fontWeight: 500, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1.2, fontFamily: "'JetBrains Mono', monospace", borderBottom: '1px solid #1c202a', background: '#0b0d12' },
  tr: { borderBottom: '1px solid #1c202a' },
  td: { padding: '12px 18px', color: '#e5e7eb', verticalAlign: 'middle' },
  mono: { fontFamily: "'JetBrains Mono', monospace", fontVariantNumeric: 'tabular-nums' },
};
window.TransfersTable = TransfersTable;
