function FAQ() {
  const [open, setOpen] = React.useState(0);
  const items = [
    ['Do I need to switch from Intermex / Maxi / Barri?', 'No. DineroBook sits on top of the companies you already use. You keep sending transfers through the same terminals — we just log and reconcile them for you.'],
    ['Is my data safe?', 'Yes. Bank-grade encryption at rest and in transit. Bank sync uses Stripe Financial Connections, which is read-only — we can never move money from your accounts.'],
    ['What happens when my trial ends?', 'You can choose Basic ($20/mo) or Pro ($30/mo). We keep your data for 180 days after cancellation so you can always come back and export.'],
    ['Can my employees use it?', 'Yes. Invite unlimited employees per store. They get a simplified view for logging daily activity without seeing financial summaries.'],
    ['I run multiple stores. How does that work?', 'One owner account, unlimited stores. Customers auto-sync across your store umbrella so a sender logged at store A autocompletes at store B.'],
    ['Do you support QuickBooks / accountant export?', 'Yes — CSV and PDF export on every report. We\'re working on direct QuickBooks Online sync (Q3 2026).'],
  ];
  return (
    <section style={q.bg}>
      <div style={q.inner}>
        <div style={q.eye}>// QUESTIONS</div>
        <h2 style={q.title}>Answered.</h2>
        <div>
          {items.map((x, i) => {
            const isOpen = open === i;
            return (
              <div key={i} style={q.item} onClick={() => setOpen(isOpen ? -1 : i)}>
                <div style={q.q}>
                  <span>{x[0]}</span>
                  <span style={{...q.plus, color: isOpen ? '#3fff00' : '#9199a8', transform: isOpen ? 'rotate(45deg)' : 'none'}}>+</span>
                </div>
                {isOpen && <div style={q.a}>{x[1]}</div>}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
const q = {
  bg: { padding: '96px 48px', background: '#0b0d12', borderTop: '1px solid #1c202a' },
  inner: { maxWidth: 820, margin: '0 auto' },
  eye: { fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3fff00', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 18, textAlign: 'center' },
  title: { fontFamily: "'Space Grotesk', sans-serif", fontSize: 44, color: '#e5e7eb', fontWeight: 600, letterSpacing: '-.03em', lineHeight: 1.1, textAlign: 'center', marginBottom: 48 },
  item: { borderBottom: '1px solid #1c202a', cursor: 'pointer', padding: '20px 0' },
  q: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 16, color: '#e5e7eb', fontWeight: 500, fontFamily: "'Inter', sans-serif" },
  plus: { fontSize: 22, fontWeight: 300, transition: 'transform .2s, color .2s' },
  a: { marginTop: 12, fontSize: 14.5, color: '#9199a8', lineHeight: 1.6, fontFamily: "'Inter', sans-serif", maxWidth: 700 },
};
window.FAQ = FAQ;
