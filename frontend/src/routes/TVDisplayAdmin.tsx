import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, Outlet } from "react-router-dom";

import {
  useClaimTVPairCode,
  useCreateTVDisplayCountry,
  useDeleteTVDisplayCountry,
  useRegenerateTVDisplayToken,
  useRevokeTVPairing,
  useSaveTVDisplaySettings,
  useTVDisplayOverview,
} from "../api/tvDisplay";
import { useProfile, useStoreInfo } from "../api/account";
import { ApiError } from "../lib/api";
import { formatTimestamp } from "../lib/datetime";
import {
  Button, ButtonLink, Card, ConfirmDialog, ErrorState, Field,
  IconButton, Input, Loading, PageShell, Section, Select,
  Breadcrumbs, TabsBar, TabsLink,
} from "../components/ui";
import styles from "./TVDisplayAdmin.module.css";

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

function formatPairTimestamp(
  iso: string,
  userTimezone: string,
  storeTimezone: string,
): string {
  return formatTimestamp(iso, { userTimezone, storeTimezone });
}

// /app/tv-display — tabbed admin hub.  Layout route: this
// component renders the page chrome (title + tab bar) + the
// shared loading/error state, then `<Outlet />` for the active
// child tab.  Each tab is a child route mounted in App.tsx
// (`TVDisplayOverview`, `TVDisplayContent`, `TVDisplayDevice`).
// Tab URLs are deep-linkable.
//
// /app/tv-display (bare) redirects to /overview.
export default function TVDisplayAdmin() {
  const { data, isLoading, isError, error, refetch } = useTVDisplayOverview();

  if (isLoading) {
    return (
      <PageShell gap="1.25rem">
        <Loading />
      </PageShell>
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
        <PageShell gap="1.25rem">
          <h1 className={styles.title}>TV Display</h1>
          <p className={styles.muted}>
            The TV Display add-on isn't active for this store.{" "}
            <a href="/admin/subscription" className={styles.link}>
              Turn it on from your subscription page.
            </a>
          </p>
        </PageShell>
      );
    }
    return (
      <PageShell gap="1.25rem">
        <h1 className={styles.title}>TV Display</h1>
        <ErrorState
          message={`Couldn't load the TV display.${error instanceof Error ? ` ${error.message}` : ""}`}
          onRetry={() => { void refetch(); }}
        />
      </PageShell>
    );
  }

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[{ label: "TV Display" }]} />
      <TabsBar>
        <TabsLink to="/tv-display/overview">Overview</TabsLink>
        <TabsLink to="/tv-display/content">Content</TabsLink>
        <TabsLink to="/tv-display/device">Device & Settings</TabsLink>
      </TabsBar>
      <Outlet />
    </PageShell>
  );
}


/** Per-tab components.  Each fetches the same overview data via
 *  the existing React-Query hook (cached at the layout route's
 *  level so the second render is instant), then renders the
 *  subset of widgets that belong to its tab.  Keeps the diff
 *  minimal: existing sub-components are unchanged. */
export function TVDisplayOverview() {
  const { data } = useTVDisplayOverview();
  const { data: profile } = useProfile();
  const { data: storeInfo } = useStoreInfo();
  const regenerateToken = useRegenerateTVDisplayToken();
  if (!data) return null;
  const userTz = profile?.timezone ?? "";
  const storeTz = storeInfo?.store?.timezone ?? "";
  return (
    <>
      <Hero data={data} userTimezone={userTz} storeTimezone={storeTz} />
      <PublicUrlBar
        publicUrl={data.public_url}
        onRegenerate={() => regenerateToken.mutate()}
        regenerating={regenerateToken.isPending}
      />
    </>
  );
}


export function TVDisplayContent() {
  const { data } = useTVDisplayOverview();
  const createCountry = useCreateTVDisplayCountry();
  const deleteCountry = useDeleteTVDisplayCountry();
  if (!data) return null;
  return (
    <CountrySections
      countries={data.countries}
      onCreate={(payload) => createCountry.mutateAsync(payload)}
      onDelete={(id) => deleteCountry.mutateAsync(id)}
      createPending={createCountry.isPending}
      deletePending={deleteCountry.isPending}
    />
  );
}


export function TVDisplayDevice() {
  const { data } = useTVDisplayOverview();
  const { data: profile } = useProfile();
  const { data: storeInfo } = useStoreInfo();
  const saveSettings = useSaveTVDisplaySettings();
  const claimPair = useClaimTVPairCode();
  const revokePair = useRevokeTVPairing();
  if (!data) return null;
  const userTz = profile?.timezone ?? "";
  const storeTz = storeInfo?.store?.timezone ?? "";
  return (
    <>
      <PairFireTV
        activePairing={data.active_pairing}
        onClaim={(code) => claimPair.mutateAsync(code)}
        onRevoke={(id) => revokePair.mutateAsync(id)}
        claimError={extractClaimError(claimPair.error)}
        claimPending={claimPair.isPending}
        revokePending={revokePair.isPending}
        userTimezone={userTz}
        storeTimezone={storeTz}
      />
      <SettingsAndStatsGrid
        data={data}
        onSave={(payload) => saveSettings.mutateAsync(payload)}
        savePending={saveSettings.isPending}
      />
    </>
  );
}


// ── Hero ──────────────────────────────────────────────────────

function Hero({
  data, userTimezone, storeTimezone,
}: {
  data: import("../api/tvDisplay").TVDisplayOverviewResponse;
  userTimezone: string;
  storeTimezone: string;
}) {
  const lastEdited = data.last_updated_at
    ? formatPairTimestamp(data.last_updated_at, userTimezone, storeTimezone)
    : null;
  return (
    <section className={styles.hero}>
      <div>
        <div className={styles.eyebrow}>TV Display · Live layout</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
          <h1 className={styles.heroTitle}>{data.title || "Cheapest Money Transfer"}</h1>
          <span className={styles.statusPill}>
            <span className={styles.statusDot} />
            Live
          </span>
        </div>
        <div className={styles.heroMeta}>
          <b>One layout</b> per store · one paired Fire TV at a time, plus
          tablets/Chromecasts on the shared URL.
          {lastEdited ? (
            <> Last edited <b>{lastEdited}</b>.</>
          ) : null}
        </div>
      </div>
      <div>
        <ButtonLink
          href={data.public_url}
          target="_blank"
          rel="noopener"
        >
          Open TV view ↗
        </ButtonLink>
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
  const [confirmingRegen, setConfirmingRegen] = useState(false);

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

  function doRegenerate() {
    setConfirmingRegen(false);
    onRegenerate();
  }

  return (
    <section style={{ marginTop: 18 }}>
      <div className={styles.urlBar} aria-label="Public display URL">
        <span className={styles.urlBarLabel}>Public display URL</span>
        <input
          type="text"
          value={publicUrl}
          readOnly
          aria-label="Public TV display URL"
          className={styles.urlBarInput}
        />
        <Button
          tone="secondary" size="sm"
          onClick={copy}
        >
          {copyState === "copied" ? "Copied"
            : copyState === "fail" ? "Select + copy"
            : "Copy"}
        </Button>
        <ButtonLink
          href={publicUrl}
          tone="secondary" size="sm"
          target="_blank"
          rel="noopener"
        >
          Open ↗
        </ButtonLink>
      </div>
      <details
        style={{ marginTop: 8 }}
        open={showRegenForm}
        onToggle={(e) => setShowRegenForm((e.currentTarget as HTMLDetailsElement).open)}
      >
        <summary className={styles.detailsSummary}>
          URL leaked or lost? Regenerate the token.
        </summary>
        <div className={styles.regenPanel}>
          <p className={styles.regenCopy}>
            Rotating the token immediately breaks the current URL.
            You'll need to reload every TV in your store after rotating.
          </p>
          <Button
            tone="danger" size="sm"
            onClick={() => setConfirmingRegen(true)}
            busy={regenerating}
            disabled={regenerating}
          >
            {regenerating ? "Regenerating…" : "Regenerate display URL"}
          </Button>
        </div>
      </details>

      <ConfirmDialog
        open={confirmingRegen}
        title="Rotate display URL?"
        message="This invalidates the current display URL.  Any TV pointing at the old link will stop showing the board until you reconfigure it with the new URL."
        confirmLabel="Rotate URL"
        confirmTone="danger"
        busy={regenerating}
        onConfirm={doRegenerate}
        onCancel={() => setConfirmingRegen(false)}
      />
    </section>
  );
}


// ── Pair-a-Fire-TV ──────────────────────────────────────────

function PairFireTV({
  activePairing, onClaim, onRevoke,
  claimError, claimPending, revokePending,
  userTimezone, storeTimezone,
}: {
  activePairing: import("../api/tvDisplay").TVPairingSummary | null;
  onClaim: (code: string) => Promise<unknown>;
  onRevoke: (id: number) => Promise<unknown>;
  claimError: string | null;
  claimPending: boolean;
  revokePending: boolean;
  userTimezone: string;
  storeTimezone: string;
}) {
  const [code, setCode] = useState("");
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [pendingUnpair, setPendingUnpair] = useState<number | null>(null);
  const [unpairBusy, setUnpairBusy] = useState(false);

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

  async function doUnpair() {
    if (pendingUnpair == null) return;
    setFlash(null);
    setUnpairBusy(true);
    try {
      await onRevoke(pendingUnpair);
      setPendingUnpair(null);
      setFlash({
        kind: "ok",
        msg: "Fire TV unpaired. The device will stop showing the board on its next refresh.",
      });
    } finally {
      setUnpairBusy(false);
    }
  }

  // Claim button is enabled only when the input has 6 valid chars.
  const codeValid = code.length === 6
    && [...code].every((c) => PAIR_CODE_ALPHABET.includes(c));

  return (
    <section className={styles.pairWrapper}>
      <div className={styles.pairBox}>
        <div style={{ flex: "1 1 240px", minWidth: 0 }}>
          <h3 className={styles.pairTitle}>Pair a Fire TV</h3>
          <p className={styles.pairCopy}>
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
            className={styles.pairInput}
          />
          <Button
            type="submit"
            busy={claimPending}
            disabled={!codeValid || claimPending}
          >
            {claimPending ? "Pairing…" : "Pair"}
          </Button>
        </form>
      </div>
      {flash && (
        <div className={flash.kind === "ok" ? styles.flashOk : styles.flashErr}>
          {flash.msg}
        </div>
      )}
      {claimError && !flash && (
        <div className={styles.flashErr}>{claimError}</div>
      )}
      {activePairing && (
        <div className={styles.activePairing}>
          <span className={styles.activeDot} aria-hidden="true" />
          <div style={{ flex: "1 1 auto", minWidth: 0 }}>
            <b>
              Fire TV paired
              {activePairing.device_label ? ` — ${activePairing.device_label}` : ""}
            </b>
            <div className={styles.mutedSmall}>
              Paired {formatPairTimestamp(activePairing.paired_at, userTimezone, storeTimezone)} · last seen{" "}
              {formatPairTimestamp(activePairing.last_seen_at, userTimezone, storeTimezone)}
            </div>
          </div>
          <Button
            tone="danger" size="sm"
            onClick={() => setPendingUnpair(activePairing.id)}
            busy={revokePending}
            disabled={revokePending}
          >
            {revokePending ? "Unpairing…" : "Unpair this Fire TV"}
          </Button>
        </div>
      )}

      <ConfirmDialog
        open={pendingUnpair != null}
        title="Unpair Fire TV?"
        message="The device will stop showing the rate board on its next refresh.  You can pair a new device with a fresh code afterwards."
        confirmLabel="Unpair"
        confirmTone="danger"
        busy={unpairBusy}
        onConfirm={() => { void doUnpair(); }}
        onCancel={() => setPendingUnpair(null)}
      />
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
    <div className={styles.gridTwoOne}>
      <Card>
        <Section title="Display settings">
          <form onSubmit={submit}>
            <div className={styles.fieldGrid}>
              <Field label="Title (top line)">
                <Input
                  type="text"
                  value={draft.title}
                  maxLength={120}
                  placeholder="Cheapest Money Transfer"
                  onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
                />
              </Field>
              <Field label="Subtitle (second line, optional)">
                <Input
                  type="text"
                  value={draft.subtitle}
                  maxLength={120}
                  placeholder="Mejor Tipo de Cambio"
                  onChange={(e) => setDraft((d) => ({ ...d, subtitle: e.target.value }))}
                />
              </Field>
              <Field label="Orientation">
                <Select
                  value={draft.orientation}
                  onChange={(e) => setDraft((d) => ({ ...d, orientation: e.target.value }))}
                >
                  {ORIENTATION_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Board theme">
                <Select
                  value={draft.theme}
                  onChange={(e) => setDraft((d) => ({ ...d, theme: e.target.value }))}
                >
                  {THEME_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </Select>
              </Field>
            </div>
            <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end", gap: 12, alignItems: "center" }}>
              {saved && <span className={styles.savedFlash}>Saved</span>}
              <Button
                type="submit"
                busy={savePending}
                disabled={savePending}
              >
                {savePending ? "Saving…" : "Save settings"}
              </Button>
            </div>
          </form>
        </Section>
      </Card>
      <Card>
        <Section title="At a glance">
          <div className={styles.statRows}>
            <StatRow label="Country sections" value={data.countries.length} />
            <StatRow label="Payout banks"     value={stats.totalBanks} />
            <StatRow label="Rate cells filled" value={stats.totalRates} />
            <StatRow label="Subscription"     value="$5/mo" valueStyle={{ color: "var(--db-neon)" }} />
          </div>
        </Section>
      </Card>
    </div>
  );
}

function StatRow({ label, value, valueStyle }: { label: string; value: number | string; valueStyle?: React.CSSProperties }) {
  return (
    <div className={styles.statRow}>
      <span>{label}</span>
      <span className={styles.statValue} style={valueStyle}>{value}</span>
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
  const [pendingRemove, setPendingRemove] =
    useState<{ id: number; name: string } | null>(null);

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

  async function doRemove() {
    if (!pendingRemove) return;
    await onDelete(pendingRemove.id);
    setPendingRemove(null);
  }

  return (
    <>
      <div className={styles.countriesHead}>
        <div>
          <h2 className={styles.sectionTitle}>Country sections</h2>
          <div className={styles.mutedSmall}>
            Each country becomes one block on the TV board. Tap to edit its rate grid.
          </div>
        </div>
      </div>
      {countries.length === 0 && (
        <div className={styles.empty}>
          <h3 className={styles.sectionTitle} style={{ fontSize: 17 }}>No country sections yet</h3>
          <p style={{ margin: 0 }}>
            Add Mexico, Guatemala, Honduras — anywhere your store sends money — to start the rate board.
          </p>
        </div>
      )}
      <div className={styles.countryGrid}>
        {countries.map((c) => (
          <div key={c.id} className={styles.countryCardWrapper}>
            <Link
              to={`/tv-display/countries/${c.id}`}
              reloadDocument
              className={styles.countryCardLink}
            >
              <div className={c.country_code ? styles.flagBox : `${styles.flagBox} ${styles.flagBoxEmpty}`}>
                {c.country_code ? flagEmoji(c.country_code) : "—"}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className={styles.countryName}>
                  {c.country_name}
                  {c.country_code && <span className={styles.countryIso}>{c.country_code}</span>}
                </div>
                <div className={styles.countryStats}>
                  <span className={styles.countryStatNum}>{c.bank_count}</span> banks ·{" "}
                  <span className={styles.countryStatNum}>{c.rate_count}</span> rates
                </div>
              </div>
              <div className={styles.countryArrow} aria-hidden="true">→</div>
            </Link>
            {/* Absolute positioning lives in style here (vs the
                old `.countryDeleteButton` class) so the kit
                IconButton can own the visual treatment. */}
            <IconButton
              tone="neutral" size="sm"
              onClick={(e) => { e.preventDefault(); setPendingRemove({ id: c.id, name: c.country_name }); }}
              disabled={deletePending}
              title={`Remove ${c.country_name}`}
              style={{ position: "absolute", top: 6, right: 6 }}
            >
              ×
            </IconButton>
          </div>
        ))}
        <details
          className={styles.addCountry}
          open={showAdd}
          onToggle={(e) => setShowAdd((e.currentTarget as HTMLDetailsElement).open)}
        >
          <summary className={styles.addCountrySummary}>
            <div className={styles.plusIcon}>+</div>
            <div style={{ flex: 1 }}>
              <div className={styles.countryName} style={{ color: "var(--text-muted)" }}>Add a country</div>
              <div className={styles.countryStats}>
                Mexico, Guatemala, El Salvador, Honduras…
              </div>
            </div>
          </summary>
          <form onSubmit={addCountry} style={{ padding: 18 }}>
            <Field label="Country *" style={{ maxWidth: 460 }}>
              <Select
                value={picker}
                required
                onChange={(e) => setPicker(e.target.value)}
              >
                <option value="">— Pick a country —</option>
                {COUNTRY_PICKER.map(([iso, name]) => (
                  <option key={iso} value={iso}>{name}</option>
                ))}
              </Select>
            </Field>
            {createError && <div className={styles.flashErr} style={{ marginTop: 12 }}>{createError}</div>}
            <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-end" }}>
              <Button
                type="submit"
                busy={createPending}
                disabled={createPending}
              >
                {createPending ? "Adding…" : "Add country"}
              </Button>
            </div>
          </form>
        </details>
      </div>

      <ConfirmDialog
        open={pendingRemove != null}
        title="Remove country?"
        message={
          `Remove ${pendingRemove?.name ?? "this country"}? `
          + "This deletes its banks and rates from the board."
        }
        confirmLabel="Remove"
        confirmTone="danger"
        busy={deletePending}
        onConfirm={() => { void doRemove(); }}
        onCancel={() => setPendingRemove(null)}
      />
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

