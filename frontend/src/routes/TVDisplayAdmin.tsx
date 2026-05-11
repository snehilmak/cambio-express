import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  useClaimTVPairCode,
  useCreateTVDisplayCountry,
  useDeleteTVDisplayCountry,
  useRegenerateTVDisplayToken,
  useRevokeTVPairing,
  useSaveTVDisplaySettings,
  useTVDisplayOverview,
} from "../api/tvDisplay";
import { ApiError } from "../lib/api";
import { ErrorState, Loading } from "../components/ui";

// /app/tv-display — TV Display add-on operator console.
//
// One store = one layout (enforced at the data layer). This page
// surfaces:
//   • the public URL the in-store TVs point at (with copy + rotate)
//   • the Fire TV pairing flow (operator types the code shown on the TV)
//   • the active pairing pill + unpair action
//   • settings form (title/subtitle/orientation/theme)
//   • country sections grid (links into the legacy editor for now —
//     the country editor migrates next)
//
// Strings "Public display URL", "Display settings", "Country sections"
// are referenced by tests (legacy + new). Don't rename them.

// Static country picker — same list as the legacy `_TV_COUNTRY_PICKER`
// in app.py. This list grows roughly once a year as new corridors
// come online, so inlining it here keeps the bundle simple and
// avoids an extra round-trip on page load.
const COUNTRY_PICKER: ReadonlyArray<readonly [string, string]> = [
  ["MX", "Mexico"], ["GT", "Guatemala"], ["HN", "Honduras"],
  ["SV", "El Salvador"], ["DO", "Dominican Republic"], ["NI", "Nicaragua"],
  ["CR", "Costa Rica"], ["PA", "Panama"], ["CO", "Colombia"],
  ["EC", "Ecuador"], ["PE", "Peru"], ["VE", "Venezuela"],
  ["CU", "Cuba"], ["HT", "Haiti"], ["JM", "Jamaica"],
  ["BR", "Brazil"], ["AR", "Argentina"], ["CL", "Chile"],
  ["BO", "Bolivia"], ["PY", "Paraguay"], ["UY", "Uruguay"],
  ["PH", "Philippines"], ["IN", "India"], ["PK", "Pakistan"],
  ["BD", "Bangladesh"], ["VN", "Vietnam"], ["NG", "Nigeria"],
  ["GH", "Ghana"], ["KE", "Kenya"], ["ET", "Ethiopia"],
];

const PAIR_CODE_ALPHABET = "ACDEFGHJKMNPQRTUVWXYZ234579";
const ORIENTATION_OPTIONS = [
  { value: "auto",      label: "Auto (follow device)" },
  { value: "landscape", label: "Landscape (16:9)" },
  { value: "portrait",  label: "Portrait (vertical TV)" },
];
const THEME_OPTIONS = [
  { value: "light", label: "Light (high readability)" },
  { value: "dark",  label: "Dark (low-light room)" },
];

function flagEmoji(iso2: string): string {
  if (!iso2 || iso2.length !== 2) return "";
  const code = iso2.toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return "";
  return String.fromCodePoint(
    ...[...code].map((c) => 0x1f1e6 + (c.charCodeAt(0) - 65)),
  );
}

function formatPairTimestamp(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
    timeZone: "UTC",
  }) + " UTC";
}

export default function TVDisplayAdmin() {
  const { data, isLoading, isError, error, refetch } = useTVDisplayOverview();

  const saveSettings    = useSaveTVDisplaySettings();
  const regenerateToken = useRegenerateTVDisplayToken();
  const claimPair       = useClaimTVPairCode();
  const revokePair      = useRevokeTVPairing();
  const createCountry   = useCreateTVDisplayCountry();
  const deleteCountry   = useDeleteTVDisplayCountry();

  if (isLoading) {
    return (
      <main style={pageStyle}>
        <Loading />
      </main>
    );
  }
  if (isError || !data) {
    // 409 from the addon-not-active guard surfaces here. We can't
    // redirect to /admin/subscription from React without losing the
    // session cookie path, so a clear message + a link is the
    // closest match to the legacy flash banner.
    const status = error instanceof ApiError ? error.status : 0;
    if (status === 409) {
      return (
        <main style={pageStyle}>
          <h1 style={titleStyle}>TV Display</h1>
          <p style={mutedStyle}>
            The TV Display add-on isn't active for this store.{" "}
            <a href="/admin/subscription" style={linkStyle}>
              Turn it on from your subscription page.
            </a>
          </p>
        </main>
      );
    }
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>TV Display</h1>
        <ErrorState
          message={`Couldn't load the TV display.${error instanceof Error ? ` ${error.message}` : ""}`}
          onRetry={() => { void refetch(); }}
        />
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <Hero data={data} />
      <PublicUrlBar
        publicUrl={data.public_url}
        onRegenerate={() => regenerateToken.mutate()}
        regenerating={regenerateToken.isPending}
      />
      <PairFireTV
        activePairing={data.active_pairing}
        onClaim={(code) => claimPair.mutateAsync(code)}
        onRevoke={(id) => revokePair.mutateAsync(id)}
        claimError={extractClaimError(claimPair.error)}
        claimPending={claimPair.isPending}
        revokePending={revokePair.isPending}
      />
      <SettingsAndStatsGrid
        data={data}
        onSave={(payload) => saveSettings.mutateAsync(payload)}
        savePending={saveSettings.isPending}
      />
      <CountrySections
        countries={data.countries}
        onCreate={(payload) => createCountry.mutateAsync(payload)}
        onDelete={(id) => deleteCountry.mutateAsync(id)}
        createPending={createCountry.isPending}
        deletePending={deleteCountry.isPending}
      />
    </main>
  );
}


// ── Hero ──────────────────────────────────────────────────────

function Hero({ data }: { data: import("../api/tvDisplay").TVDisplayOverviewResponse }) {
  const lastEdited = data.last_updated_at
    ? formatPairTimestamp(data.last_updated_at)
    : null;
  return (
    <section style={heroStyle}>
      <div>
        <div style={eyebrowStyle}>TV Display · Live layout</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
          <h1 style={heroTitleStyle}>{data.title || "Cheapest Money Transfer"}</h1>
          <span style={statusPillStyle}>
            <span style={statusDotStyle} />
            Live
          </span>
        </div>
        <div style={heroMetaStyle}>
          <b>One layout</b> per store · one paired Fire TV at a time, plus
          tablets/Chromecasts on the shared URL.
          {lastEdited ? (
            <> Last edited <b>{lastEdited}</b>.</>
          ) : null}
        </div>
      </div>
      <div>
        <a
          href={data.public_url}
          target="_blank"
          rel="noopener"
          style={primaryButtonStyle}
        >
          Open TV view ↗
        </a>
      </div>
    </section>
  );
}


// ── Public URL bar + regenerate-token panel ─────────────────────

function PublicUrlBar({
  publicUrl, onRegenerate, regenerating,
}: {
  publicUrl: string;
  onRegenerate: () => void;
  regenerating: boolean;
}) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "fail">("idle");
  const [showRegenForm, setShowRegenForm] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(publicUrl);
      setCopyState("copied");
      setTimeout(() => setCopyState("idle"), 1200);
    } catch {
      setCopyState("fail");
      setTimeout(() => setCopyState("idle"), 1500);
    }
  }

  function regenerate() {
    if (!window.confirm(
      "This invalidates the current display URL. Any TV pointing at the " +
      "old link will stop working until you reconfigure it. Continue?",
    )) return;
    onRegenerate();
  }

  return (
    <section style={{ marginTop: 18 }}>
      <div style={urlBarStyle} aria-label="Public display URL">
        <span style={urlBarLabelStyle}>Public display URL</span>
        <input
          type="text"
          value={publicUrl}
          readOnly
          aria-label="Public TV display URL"
          style={urlBarInputStyle}
        />
        <button type="button" onClick={copy} style={urlBarButtonStyle}>
          {copyState === "copied" ? "Copied"
            : copyState === "fail" ? "Select + copy"
            : "Copy"}
        </button>
        <a
          href={publicUrl}
          target="_blank"
          rel="noopener"
          style={urlBarButtonStyle}
        >
          Open ↗
        </a>
      </div>
      <details
        style={{ marginTop: 8 }}
        open={showRegenForm}
        onToggle={(e) => setShowRegenForm((e.currentTarget as HTMLDetailsElement).open)}
      >
        <summary style={detailsSummaryStyle}>
          URL leaked or lost? Regenerate the token.
        </summary>
        <div style={regenPanelStyle}>
          <p style={regenCopyStyle}>
            Rotating the token immediately breaks the current URL.
            You'll need to reload every TV in your store after rotating.
          </p>
          <button
            type="button"
            onClick={regenerate}
            disabled={regenerating}
            style={dangerOutlineButtonStyle}
          >
            {regenerating ? "Regenerating…" : "Regenerate display URL"}
          </button>
        </div>
      </details>
    </section>
  );
}


// ── Pair-a-Fire-TV ──────────────────────────────────────────

function PairFireTV({
  activePairing, onClaim, onRevoke,
  claimError, claimPending, revokePending,
}: {
  activePairing: import("../api/tvDisplay").TVPairingSummary | null;
  onClaim: (code: string) => Promise<unknown>;
  onRevoke: (id: number) => Promise<unknown>;
  claimError: string | null;
  claimPending: boolean;
  revokePending: boolean;
}) {
  const [code, setCode] = useState("");
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  function normaliseInput(raw: string): string {
    return raw.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6);
  }

  async function submitClaim(e: FormEvent) {
    e.preventDefault();
    setFlash(null);
    try {
      await onClaim(code);
      setCode("");
      setFlash({
        kind: "ok",
        msg: "Fire TV paired. The screen will switch to the rate board within a few seconds.",
      });
    } catch (err) {
      const msg = (err instanceof ApiError && typeof err.body === "object" && err.body !== null
        ? (err.body as { detail?: string }).detail
        : null) ?? "Code not found or expired.";
      setFlash({ kind: "err", msg });
    }
  }

  async function revoke(id: number) {
    if (!window.confirm(
      "Unpair this Fire TV? It will stop showing the board on its next refresh, " +
      "and you can pair a new device with a fresh code.",
    )) return;
    setFlash(null);
    await onRevoke(id);
    setFlash({
      kind: "ok",
      msg: "Fire TV unpaired. The device will stop showing the board on its next refresh.",
    });
  }

  // Claim button is enabled only when the input has 6 valid chars.
  const codeValid = code.length === 6
    && [...code].every((c) => PAIR_CODE_ALPHABET.includes(c));

  return (
    <section style={pairWrapperStyle}>
      <div style={pairBoxStyle}>
        <div style={{ flex: "1 1 240px", minWidth: 0 }}>
          <h3 style={pairTitleStyle}>Pair a Fire TV</h3>
          <p style={pairCopyStyle}>
            Install the <b>DineroBook TV</b> app on your Fire TV from the
            Amazon Appstore and open it. Type the 6-character code shown
            on the TV here. Pairing a new Fire TV automatically unpairs
            the old one — one Fire TV per subscription.
          </p>
        </div>
        <form onSubmit={submitClaim} style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(normaliseInput(e.target.value))}
            maxLength={8}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            inputMode="text"
            placeholder="ABC234"
            aria-label="Code shown on your Fire TV"
            style={pairInputStyle}
          />
          <button
            type="submit"
            disabled={!codeValid || claimPending}
            style={primaryButtonStyle}
          >
            {claimPending ? "Pairing…" : "Pair"}
          </button>
        </form>
      </div>
      {flash && (
        <div style={flash.kind === "ok" ? flashOkStyle : flashErrStyle}>
          {flash.msg}
        </div>
      )}
      {claimError && !flash && (
        <div style={flashErrStyle}>{claimError}</div>
      )}
      {activePairing && (
        <div style={activePairingStyle}>
          <span style={activeDotStyle} aria-hidden="true" />
          <div style={{ flex: "1 1 auto", minWidth: 0 }}>
            <b>
              Fire TV paired
              {activePairing.device_label ? ` — ${activePairing.device_label}` : ""}
            </b>
            <div style={mutedSmallStyle}>
              Paired {formatPairTimestamp(activePairing.paired_at)} · last seen{" "}
              {formatPairTimestamp(activePairing.last_seen_at)}
            </div>
          </div>
          <button
            type="button"
            onClick={() => revoke(activePairing.id)}
            disabled={revokePending}
            style={dangerOutlineButtonStyle}
          >
            {revokePending ? "Unpairing…" : "Unpair this Fire TV"}
          </button>
        </div>
      )}
    </section>
  );
}


// ── Settings + at-a-glance grid ──────────────────────────────

function SettingsAndStatsGrid({
  data, onSave, savePending,
}: {
  data: import("../api/tvDisplay").TVDisplayOverviewResponse;
  onSave: (payload: import("../api/tvDisplay").TVDisplaySettingsUpdate) => Promise<unknown>;
  savePending: boolean;
}) {
  const [draft, setDraft] = useState(() => ({
    title:       data.title,
    subtitle:    data.subtitle,
    orientation: data.orientation || "auto",
    theme:       data.theme || "light",
  }));
  const [saved, setSaved] = useState(false);

  // Re-sync if the upstream data changes (e.g. after a save invalidation).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- re-hydrate local editable draft from server-fetched TV display config after save invalidation
    setDraft({
      title:       data.title,
      subtitle:    data.subtitle,
      orientation: data.orientation || "auto",
      theme:       data.theme || "light",
    });
  }, [data.title, data.subtitle, data.orientation, data.theme]);

  const stats = useMemo(() => {
    let totalBanks = 0, totalRates = 0;
    for (const c of data.countries) {
      totalBanks += c.bank_count;
      totalRates += c.rate_count;
    }
    return { totalBanks, totalRates };
  }, [data.countries]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaved(false);
    await onSave(draft);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div style={gridTwoOneStyle}>
      <section style={cardStyle}>
        <header style={cardHeadStyle}>
          <span style={cardTitleStyle}>Display settings</span>
        </header>
        <div style={cardBodyStyle}>
          <form onSubmit={submit}>
            <div style={fieldGridStyle}>
              <label style={fieldStyle}>
                <span style={fieldLabelStyle}>Title (top line)</span>
                <input
                  type="text"
                  value={draft.title}
                  maxLength={120}
                  placeholder="Cheapest Money Transfer"
                  onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
                  style={inputStyle}
                />
              </label>
              <label style={fieldStyle}>
                <span style={fieldLabelStyle}>Subtitle (second line, optional)</span>
                <input
                  type="text"
                  value={draft.subtitle}
                  maxLength={120}
                  placeholder="Mejor Tipo de Cambio"
                  onChange={(e) => setDraft((d) => ({ ...d, subtitle: e.target.value }))}
                  style={inputStyle}
                />
              </label>
              <label style={fieldStyle}>
                <span style={fieldLabelStyle}>Orientation</span>
                <select
                  value={draft.orientation}
                  onChange={(e) => setDraft((d) => ({ ...d, orientation: e.target.value }))}
                  style={inputStyle}
                >
                  {ORIENTATION_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </label>
              <label style={fieldStyle}>
                <span style={fieldLabelStyle}>Board theme</span>
                <select
                  value={draft.theme}
                  onChange={(e) => setDraft((d) => ({ ...d, theme: e.target.value }))}
                  style={inputStyle}
                >
                  {THEME_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </label>
            </div>
            <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end", gap: 12, alignItems: "center" }}>
              {saved && <span style={savedFlashStyle}>Saved</span>}
              <button type="submit" disabled={savePending} style={primaryButtonStyle}>
                {savePending ? "Saving…" : "Save settings"}
              </button>
            </div>
          </form>
        </div>
      </section>
      <section style={cardStyle}>
        <header style={cardHeadStyle}>
          <span style={cardTitleStyle}>At a glance</span>
        </header>
        <div style={cardBodyStyle}>
          <div style={statRowsStyle}>
            <StatRow label="Country sections" value={data.countries.length} />
            <StatRow label="Payout banks"     value={stats.totalBanks} />
            <StatRow label="Rate cells filled" value={stats.totalRates} />
            <StatRow label="Subscription"     value="$5/mo" valueStyle={{ color: "var(--db-neon)" }} />
          </div>
        </div>
      </section>
    </div>
  );
}

function StatRow({ label, value, valueStyle }: { label: string; value: number | string; valueStyle?: React.CSSProperties }) {
  return (
    <div style={statRowStyle}>
      <span>{label}</span>
      <span style={{ ...statValueStyle, ...valueStyle }}>{value}</span>
    </div>
  );
}


// ── Country sections ─────────────────────────────────────────

function CountrySections({
  countries, onCreate, onDelete, createPending, deletePending,
}: {
  countries: import("../api/tvDisplay").TVDisplayCountryStat[];
  onCreate: (payload: import("../api/tvDisplay").TVDisplayCreateCountryRequest) => Promise<import("../api/tvDisplay").TVDisplayCreateCountryResponse>;
  onDelete: (id: number) => Promise<unknown>;
  createPending: boolean;
  deletePending: boolean;
}) {
  const [showAdd, setShowAdd] = useState(false);
  const [picker, setPicker] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  async function addCountry(e: FormEvent) {
    e.preventDefault();
    setCreateError(null);
    const match = COUNTRY_PICKER.find(([iso]) => iso === picker);
    if (!match) {
      setCreateError("Pick a country.");
      return;
    }
    try {
      const created = await onCreate({
        country_name: match[1],
        country_code: match[0],
      });
      // Legacy flow redirects to the country editor (still on Flask)
      // so the operator can add banks + rates immediately. Mirror it.
      window.location.assign(`/tv-display/countries/${created.id}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to create country.";
      setCreateError(msg);
    }
  }

  async function removeCountry(id: number, name: string) {
    if (!window.confirm(`Remove ${name}? This deletes its banks and rates.`)) return;
    await onDelete(id);
  }

  return (
    <>
      <div style={countriesHeadStyle}>
        <div>
          <h2 style={sectionTitleStyle}>Country sections</h2>
          <div style={mutedSmallStyle}>
            Each country becomes one block on the TV board. Tap to edit its rate grid.
          </div>
        </div>
      </div>
      {countries.length === 0 && (
        <div style={emptyStyle}>
          <h3 style={{ ...sectionTitleStyle, fontSize: 17 }}>No country sections yet</h3>
          <p style={{ margin: 0 }}>
            Add Mexico, Guatemala, Honduras — anywhere your store sends money — to start the rate board.
          </p>
        </div>
      )}
      <div style={countryGridStyle}>
        {countries.map((c) => (
          <div key={c.id} style={countryCardWrapperStyle}>
            <Link
              to={`/tv-display/countries/${c.id}`}
              reloadDocument
              style={countryCardLinkStyle}
            >
              <div style={c.country_code ? flagBoxStyle : flagBoxEmptyStyle}>
                {c.country_code ? flagEmoji(c.country_code) : "—"}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={countryNameStyle}>
                  {c.country_name}
                  {c.country_code && <span style={countryIsoStyle}>{c.country_code}</span>}
                </div>
                <div style={countryStatsStyle}>
                  <span style={countryStatNumStyle}>{c.bank_count}</span> banks ·{" "}
                  <span style={countryStatNumStyle}>{c.rate_count}</span> rates
                </div>
              </div>
              <div style={countryArrowStyle} aria-hidden="true">→</div>
            </Link>
            <button
              type="button"
              onClick={(e) => { e.preventDefault(); removeCountry(c.id, c.country_name); }}
              disabled={deletePending}
              style={countryDeleteButtonStyle}
              title={`Remove ${c.country_name}`}
            >
              ×
            </button>
          </div>
        ))}
        <details
          style={addCountryStyle}
          open={showAdd}
          onToggle={(e) => setShowAdd((e.currentTarget as HTMLDetailsElement).open)}
        >
          <summary style={addCountrySummaryStyle}>
            <div style={plusIconStyle}>+</div>
            <div style={{ flex: 1 }}>
              <div style={{ ...countryNameStyle, color: "var(--text-muted)" }}>Add a country</div>
              <div style={countryStatsStyle}>
                Mexico, Guatemala, El Salvador, Honduras…
              </div>
            </div>
          </summary>
          <form onSubmit={addCountry} style={{ padding: 18 }}>
            <label style={{ ...fieldStyle, maxWidth: 460 }}>
              <span style={fieldLabelStyle}>Country *</span>
              <select
                value={picker}
                required
                onChange={(e) => setPicker(e.target.value)}
                style={inputStyle}
              >
                <option value="">— Pick a country —</option>
                {COUNTRY_PICKER.map(([iso, name]) => (
                  <option key={iso} value={iso}>{name}</option>
                ))}
              </select>
            </label>
            {createError && <div style={{ ...flashErrStyle, marginTop: 12 }}>{createError}</div>}
            <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-end" }}>
              <button type="submit" disabled={createPending} style={primaryButtonStyle}>
                {createPending ? "Adding…" : "Add country"}
              </button>
            </div>
          </form>
        </details>
      </div>
    </>
  );
}


// ── Helpers ──────────────────────────────────────────────────

function extractClaimError(err: unknown): string | null {
  if (err instanceof ApiError) {
    const detail = (err.body as { detail?: string } | null)?.detail;
    return detail ?? err.message;
  }
  if (err instanceof Error) return err.message;
  return null;
}


// ── Inline styles ────────────────────────────────────────────

const pageStyle: React.CSSProperties = {
  maxWidth: 1100, margin: "0 auto", padding: "1.5rem 1rem 3rem",
  fontFamily: "'Inter', system-ui, sans-serif",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "'Space Grotesk', 'Inter', sans-serif",
  fontSize: 24, fontWeight: 700, margin: 0, color: "var(--text)",
};
const mutedStyle: React.CSSProperties = { color: "var(--text-muted)", fontSize: 14 };
const linkStyle: React.CSSProperties = { color: "var(--db-neon)", textDecoration: "underline" };

const heroStyle: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto",
  gap: 18, alignItems: "center",
  padding: "22px 24px",
  background: "linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%)",
  border: "1px solid var(--border)", borderRadius: 14,
  position: "relative", overflow: "hidden",
};
const eyebrowStyle: React.CSSProperties = {
  fontSize: 10.5, fontWeight: 700, letterSpacing: "0.14em",
  textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 6,
};
const heroTitleStyle: React.CSSProperties = {
  fontFamily: "'Space Grotesk', 'Inter', sans-serif",
  fontSize: 26, fontWeight: 700, letterSpacing: "-0.01em",
  color: "var(--text)", lineHeight: 1.15, margin: 0,
};
const statusPillStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "4px 10px",
  background: "var(--db-neon-glow-15)",
  border: "1px solid var(--db-neon-dim)",
  borderRadius: 999, fontSize: 11, fontWeight: 700,
  letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--db-neon)",
};
const statusDotStyle: React.CSSProperties = {
  width: 6, height: 6, borderRadius: "50%", background: "var(--db-neon)",
  boxShadow: "0 0 0 3px var(--db-neon-glow-25)",
};
const heroMetaStyle: React.CSSProperties = {
  marginTop: 8, fontSize: 13, color: "var(--text-muted)",
};

const primaryButtonStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  padding: "10px 18px",
  background: "var(--db-neon)", color: "#000",
  border: "1px solid var(--db-neon)", borderRadius: 8,
  fontFamily: "'Inter', sans-serif", fontWeight: 700, fontSize: 13,
  cursor: "pointer", textDecoration: "none",
};
const dangerOutlineButtonStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  padding: "8px 14px",
  background: "transparent", color: "var(--db-negative)",
  border: "1px solid var(--db-negative)", borderRadius: 8,
  fontFamily: "'Inter', sans-serif", fontWeight: 600, fontSize: 12.5,
  cursor: "pointer",
};

const urlBarStyle: React.CSSProperties = {
  display: "flex", alignItems: "stretch",
  background: "var(--surface-2)",
  border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden",
};
const urlBarLabelStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", padding: "0 14px",
  fontSize: 10.5, fontWeight: 700, letterSpacing: "0.12em",
  textTransform: "uppercase", color: "var(--text-muted)",
  borderRight: "1px solid var(--border)", flexShrink: 0,
};
const urlBarInputStyle: React.CSSProperties = {
  flex: 1, minWidth: 0, padding: "12px 14px",
  fontFamily: "'JetBrains Mono', Consolas, monospace",
  fontSize: 13, background: "transparent", border: 0, color: "var(--text)",
};
const urlBarButtonStyle: React.CSSProperties = {
  padding: "0 16px", display: "inline-flex", alignItems: "center", gap: 6,
  fontSize: 12.5, fontWeight: 600, background: "transparent", border: 0,
  borderLeft: "1px solid var(--border)", color: "var(--text)",
  cursor: "pointer", textDecoration: "none",
};
const detailsSummaryStyle: React.CSSProperties = {
  cursor: "pointer", fontSize: 12.5, color: "var(--text-muted)",
  padding: "6px 4px",
};
const regenPanelStyle: React.CSSProperties = {
  marginTop: 6, padding: "12px 14px",
  background: "var(--surface-2)", border: "1px solid var(--border)",
  borderRadius: 8,
};
const regenCopyStyle: React.CSSProperties = {
  margin: "0 0 10px", fontSize: 13, color: "var(--text-muted)",
};

const pairWrapperStyle: React.CSSProperties = { marginTop: 14 };
const pairBoxStyle: React.CSSProperties = {
  padding: "18px 20px",
  background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: 12,
  display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap",
};
const pairTitleStyle: React.CSSProperties = {
  fontFamily: "'Space Grotesk', 'Inter', sans-serif",
  fontSize: 15, fontWeight: 700, margin: "0 0 4px", color: "var(--text)",
};
const pairCopyStyle: React.CSSProperties = {
  fontSize: 13, color: "var(--text-muted)", margin: 0, maxWidth: "60ch",
};
const pairInputStyle: React.CSSProperties = {
  width: 220, padding: "14px 18px",
  background: "var(--surface-2)", border: "1px solid var(--border)",
  borderRadius: 10,
  fontFamily: "'JetBrains Mono', Consolas, monospace",
  fontWeight: 700, fontSize: 26, letterSpacing: "0.18em",
  textAlign: "center", textTransform: "uppercase", color: "var(--text)",
};
const flashOkStyle: React.CSSProperties = {
  marginTop: 10, padding: "10px 14px",
  background: "var(--db-neon-glow-15)", border: "1px solid var(--db-neon-dim)",
  borderRadius: 8, color: "var(--db-neon)", fontSize: 13, fontWeight: 600,
};
const flashErrStyle: React.CSSProperties = {
  marginTop: 10, padding: "10px 14px",
  background: "rgba(255, 70, 70, 0.08)", border: "1px solid var(--db-negative)",
  borderRadius: 8, color: "var(--db-negative)", fontSize: 13, fontWeight: 600,
};
const activePairingStyle: React.CSSProperties = {
  marginTop: 14, padding: "14px 18px",
  background: "var(--surface)", border: "1px solid var(--db-neon-dim)",
  borderRadius: 12,
  display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap",
};
const activeDotStyle: React.CSSProperties = {
  width: 10, height: 10, borderRadius: "50%", background: "var(--db-neon)",
  boxShadow: "0 0 0 4px var(--db-neon-glow-25)", flexShrink: 0,
};
const mutedSmallStyle: React.CSSProperties = {
  fontSize: 12.5, color: "var(--text-muted)", marginTop: 2,
};

const gridTwoOneStyle: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr)",
  gap: 18, marginTop: 22,
};
const cardStyle: React.CSSProperties = {
  background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: 12, overflow: "hidden",
};
const cardHeadStyle: React.CSSProperties = {
  padding: "14px 18px", borderBottom: "1px solid var(--border)",
  display: "flex", alignItems: "center", justifyContent: "space-between",
};
const cardTitleStyle: React.CSSProperties = {
  fontFamily: "'Space Grotesk', 'Inter', sans-serif",
  fontSize: 14, fontWeight: 700, color: "var(--text)",
};
const cardBodyStyle: React.CSSProperties = { padding: 18 };
const fieldGridStyle: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 14,
};
const fieldStyle: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 6 };
const fieldLabelStyle: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, color: "var(--text-muted)",
  textTransform: "uppercase", letterSpacing: "0.05em",
};
const inputStyle: React.CSSProperties = {
  padding: "10px 12px", borderRadius: 8,
  border: "1px solid var(--border)", background: "var(--surface-2)",
  color: "var(--text)", fontSize: 13, fontFamily: "'Inter', sans-serif",
};
const savedFlashStyle: React.CSSProperties = {
  fontSize: 12, fontWeight: 700, color: "var(--db-neon)",
};

const statRowsStyle: React.CSSProperties = { display: "flex", flexDirection: "column" };
const statRowStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "space-between",
  padding: "10px 0", borderBottom: "1px dashed var(--border)",
  fontSize: 13, color: "var(--text-muted)",
};
const statValueStyle: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 15, fontWeight: 700, color: "var(--text)",
};

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: "'Space Grotesk', 'Inter', sans-serif",
  fontSize: 18, fontWeight: 700, margin: 0, color: "var(--text)",
};
const countriesHeadStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "space-between",
  marginTop: 30, marginBottom: 14, flexWrap: "wrap", gap: 12,
};
const emptyStyle: React.CSSProperties = {
  padding: "40px 20px", textAlign: "center", color: "var(--text-muted)",
  fontSize: 14, background: "var(--surface)",
  border: "1px dashed var(--border)", borderRadius: 12, marginBottom: 14,
};
const countryGridStyle: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
  gap: 14,
};
const countryCardWrapperStyle: React.CSSProperties = {
  position: "relative",
};
const countryCardLinkStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 14,
  padding: 16, background: "var(--surface)",
  border: "1px solid var(--border)", borderRadius: 12,
  textDecoration: "none", color: "inherit",
};
const flagBoxStyle: React.CSSProperties = {
  width: 48, height: 48, flexShrink: 0,
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  background: "var(--surface-2)", border: "1px solid var(--border)",
  borderRadius: 10, fontSize: 26, lineHeight: 1, overflow: "hidden",
};
const flagBoxEmptyStyle: React.CSSProperties = {
  ...flagBoxStyle,
  color: "var(--text-muted)", fontSize: 16, fontWeight: 700,
  fontFamily: "'Space Grotesk', sans-serif",
};
const countryNameStyle: React.CSSProperties = {
  fontFamily: "'Space Grotesk', 'Inter', sans-serif",
  fontSize: 15, fontWeight: 700, color: "var(--text)", lineHeight: 1.2,
  display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap",
};
const countryIsoStyle: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 11, fontWeight: 600, color: "var(--text-muted)",
  letterSpacing: "0.05em",
};
const countryStatsStyle: React.CSSProperties = {
  marginTop: 6, fontSize: 12, color: "var(--text-muted)",
};
const countryStatNumStyle: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace",
  fontWeight: 700, color: "var(--text)",
};
const countryArrowStyle: React.CSSProperties = {
  flexShrink: 0, color: "var(--text-muted)", fontSize: 18, lineHeight: 1,
};
const countryDeleteButtonStyle: React.CSSProperties = {
  position: "absolute", top: 6, right: 6,
  width: 22, height: 22, borderRadius: "50%",
  background: "transparent", border: "1px solid var(--border)",
  color: "var(--text-muted)", cursor: "pointer",
  fontSize: 14, lineHeight: 1, display: "inline-flex",
  alignItems: "center", justifyContent: "center",
};
const addCountryStyle: React.CSSProperties = {
  display: "block", borderStyle: "dashed", background: "transparent",
  cursor: "pointer", border: "1px dashed var(--border)",
  borderRadius: 12, gridColumn: "auto",
};
const addCountrySummaryStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 14,
  padding: 16, listStyle: "none", cursor: "pointer",
  color: "var(--text-muted)",
  fontFamily: "'Space Grotesk', 'Inter', sans-serif", fontWeight: 600,
};
const plusIconStyle: React.CSSProperties = {
  width: 48, height: 48, flexShrink: 0,
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  border: "1px dashed var(--border)", borderRadius: 10,
  fontSize: 24, lineHeight: 1, color: "var(--text-muted)",
};
