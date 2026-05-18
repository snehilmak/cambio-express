import { Fragment, useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  changePassword,
  createTeamMember,
  deactivateTeamMember,
  deletePasskey,
  passkeysSupported,
  registerPasskey,
  updateStoreInfo,
  updateTeamMember,
  usePasskeys,
  useStoreInfo,
  useTeam,
  type StoreHourEntry,
  type TeamMemberRow,
} from "../api/account";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  GeolocationDeniedError,
  GeolocationUnavailableError,
  getCurrentCoordinates,
} from "../lib/geolocation";
import {
  Alert, Button, ButtonLink, Card, ErrorState, Field, Input, Loading,
  PageHeader, PageShell, SectionTitle, Select,
} from "../components/ui";
import styles from "./Settings.module.css";

// Account settings page at /app/settings. v1 ships the
// change-password card; subsequent PRs add profile / preferences /
// 2FA / passkey management.

export default function Settings() {
  const identity = getCurrentIdentity();

  return (
    <PageShell maxWidth="60rem" gap="1rem">
      <PageHeader title="Settings" subtitle={identity?.username || "—"} />

      <StoreInfoCard />
      <SubscriptionCard />
      <TeamCard />
      <ChangePasswordCard />
      <PasskeysCard />
    </PageShell>
  );
}

function PasskeysCard() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, refetch } = usePasskeys();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addBusy, setAddBusy] = useState(false);
  const [newName, setNewName] = useState("");
  const supported = passkeysSupported();

  if (identity == null) return null;

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["account", "passkeys"] });
  }

  async function remove(id: number, label: string) {
    if (!confirm(`Remove "${label || "this device"}"?`)) return;
    setErr(null); setBusyId(id);
    try {
      await deletePasskey(id);
      refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not remove device.");
    } finally {
      setBusyId(null);
    }
  }

  async function add() {
    setErr(null); setAddBusy(true);
    try {
      await registerPasskey(newName.trim());
      setAdding(false);
      setNewName("");
      refresh();
    } catch (e) {
      // navigator.credentials.create() rejects on cancel / wrong
      // device / etc. with browser-specific messages — surface
      // them as-is so users see the actual reason.
      const msg = e instanceof ApiError
        ? e.message
        : (e instanceof Error ? e.message : "Could not create passkey.");
      setErr(msg);
    } finally {
      setAddBusy(false);
    }
  }

  return (
    <Card>
      <div className={styles.sectionHead}>
        <div style={{ flex: 1 }}>
          <SectionTitle>Passkeys</SectionTitle>
        </div>
        {supported && !adding && (
          <Button
            tone="secondary" size="sm"
            onClick={() => { setAdding(true); setErr(null); }}
          >
            + Add a passkey
          </Button>
        )}
      </div>
      <p className={styles.helpText}>
        Sign in with your device (Touch ID, Face ID, Windows Hello,
        or a hardware key) instead of a password. Passkeys are
        phishing-resistant and count as two-factor auth, so a passkey
        login skips the verification-code step.
      </p>
      {!supported && (
        <Alert tone="info">
          This browser doesn't expose the WebAuthn API, so passkeys
          aren't available here. Use a modern Chrome, Safari, Firefox,
          or Edge build.
        </Alert>
      )}
      {adding && (
        <div className={styles.addInset}>
          <Field label="Nickname for this passkey">
            <Input
              type="text" value={newName} maxLength={120}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. MacBook Touch ID"
              autoFocus disabled={addBusy}
            />
          </Field>
          <div className={styles.addInsetActions}>
            <Button onClick={add} busy={addBusy} disabled={addBusy} size="sm">
              {addBusy ? "Creating…" : "Create passkey"}
            </Button>
            <Button
              tone="secondary" size="sm"
              onClick={() => { setAdding(false); setNewName(""); setErr(null); }}
              disabled={addBusy}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message="Could not load passkeys."
          onRetry={() => { void refetch(); }}
        />
      )}
      {data && data.passkeys.length === 0 && !isLoading && (
        <p className={styles.muted}>No passkeys registered yet.</p>
      )}
      {data && data.passkeys.length > 0 && (
        <ul className={styles.list}>
          {data.passkeys.map((p) => (
            <li key={p.id} className={styles.row}>
              <span className={styles.rowBody}>
                <div className={styles.rowTitle}>
                  {p.name || "Unnamed device"}
                </div>
                <div className={styles.rowMeta}>
                  Added {p.created_at.slice(0, 10)}
                  {p.last_used_at &&
                    ` · last used ${p.last_used_at.slice(0, 10)}`}
                </div>
              </span>
              <Button
                tone="secondary" size="sm"
                onClick={() => remove(p.id, p.name)}
                busy={busyId === p.id}
                disabled={busyId === p.id}
              >
                {busyId === p.id ? "Removing…" : "Remove"}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {err && <Alert tone="error">{err}</Alert>}
    </Card>
  );
}

function SubscriptionCard() {
  const identity = getCurrentIdentity();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canManage =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";
  if (!canManage || identity?.store_id == null) return null;

  async function openPortal() {
    setErr(null);
    setBusy(true);
    try {
      const { openBillingPortal } = await import("../api/billing");
      const result = await openBillingPortal();
      window.location.assign(result.url);
    } catch (e) {
      // 409 = no Stripe customer yet (trial store) — push to subscribe
      if (e instanceof ApiError && e.status === 409) {
        window.location.assign("/app/subscribe");
        return;
      }
      setErr(e instanceof ApiError ? e.message : "Could not open billing portal.");
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionTitle>Subscription</SectionTitle>
      <p className={styles.subscriptionInfo}>
        Change plan, update payment method, or cancel — all on Stripe's
        secure billing portal. Trial stores can pick a plan instead.
      </p>
      <div className={styles.actionsRow}>
        <ButtonLink href="/app/subscribe" tone="primary">
          Choose / change plan
        </ButtonLink>
        <Button
          tone="secondary"
          onClick={openPortal}
          busy={busy}
          disabled={busy}
        >
          {busy ? "Opening…" : "Manage on Stripe"}
        </Button>
      </div>
      {err && <Alert tone="error">{err}</Alert>}
    </Card>
  );
}

function TeamCard() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError } = useTeam();
  const [newName, setNewName] = useState("");
  const [newRate, setNewRate] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [rateDraftById, setRateDraftById] =
    useState<Record<number, string>>({});
  const canEdit =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";

  function refetch() {
    queryClient.invalidateQueries({ queryKey: ["admin", "team"] });
    // Also invalidate the transfer-form's roster hook so the
    // dropdown picks up new / removed cashiers without a reload.
    queryClient.invalidateQueries({ queryKey: ["transfers", "employees"] });
  }

  async function add() {
    setErr(null);
    setBusy(true);
    try {
      const rate = Number(newRate);
      await createTeamMember(
        newName,
        Number.isFinite(rate) && rate >= 0 ? rate : 0,
      );
      setNewName(""); setNewRate("");
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't add member");
    } finally {
      setBusy(false);
    }
  }

  async function saveRate(m: TeamMemberRow) {
    setErr(null);
    const raw = rateDraftById[m.id];
    if (raw == null) return;
    const rate = Number(raw);
    if (!Number.isFinite(rate) || rate < 0) {
      setErr("Hourly rate must be a non-negative number.");
      return;
    }
    try {
      await updateTeamMember(m.id, { hourly_rate: rate });
      setRateDraftById((prev) => {
        const next = { ...prev };
        delete next[m.id];
        return next;
      });
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't update rate");
    }
  }

  async function toggle(m: TeamMemberRow) {
    setErr(null);
    try {
      await updateTeamMember(m.id, { is_active: !m.is_active });
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't update");
    }
  }

  async function remove(m: TeamMemberRow) {
    setErr(null);
    try {
      await deactivateTeamMember(m.id);
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't deactivate");
    }
  }

  if (identity?.store_id == null) return null;

  return (
    <Card>
      <SectionTitle>Team</SectionTitle>
      <p className={styles.helpText}>
        Cashier names that appear in the "Processed by" dropdown
        on the transfer form. Deactivated rows stay so historical
        transfer attribution survives.
      </p>

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message="Could not load team."
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <ul className={styles.listSpaced}>
          {data.members.length === 0 && (
            <li className={styles.emptyRow}>No team members yet.</li>
          )}
          {data.members.map((m) => {
            const draft = rateDraftById[m.id];
            const displayRate = draft != null
              ? draft
              : (m.hourly_rate || 0).toFixed(2);
            return (
              <li key={m.id} className={styles.rowTeam}>
                <span className={m.is_active ? styles.memberActive : styles.memberInactive}>
                  {m.name}
                </span>
                {canEdit && (
                  <>
                    <span className={styles.rateGroup}>
                      <span className={styles.rateLabel}>$/hr</span>
                      <Input
                        type="number" min="0" step="0.25"
                        value={displayRate}
                        onChange={(e) => setRateDraftById((prev) => ({
                          ...prev, [m.id]: e.target.value,
                        }))}
                        disabled={!m.is_active}
                        style={{ width: "5.5rem" }}
                      />
                      {draft != null && (
                        <Button
                          tone="secondary" size="sm"
                          onClick={() => saveRate(m)}
                        >
                          Save
                        </Button>
                      )}
                    </span>
                    <Button
                      tone="secondary" size="sm"
                      onClick={() => toggle(m)}
                      title={m.is_active ? "Deactivate" : "Reactivate"}
                    >
                      {m.is_active ? "Deactivate" : "Reactivate"}
                    </Button>
                    {m.is_active && (
                      <Button
                        tone="secondary" size="sm"
                        onClick={() => remove(m)}
                      >
                        ✕
                      </Button>
                    )}
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {canEdit && (
        <div className={styles.actionsInlineRow}>
          <Input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="New cashier name"
            onKeyDown={(e) => {
              if (e.key === "Enter" && newName.trim()) {
                e.preventDefault();
                add();
              }
            }}
          />
          <Input
            type="number" min="0" step="0.25"
            value={newRate}
            onChange={(e) => setNewRate(e.target.value)}
            placeholder="$/hr (optional)"
            style={{ width: "9rem" }}
          />
          <Button
            onClick={add}
            busy={busy}
            disabled={busy || !newName.trim()}
          >
            + Add
          </Button>
        </div>
      )}
      {err && <Alert tone="error">{err}</Alert>}
    </Card>
  );
}

function StoreInfoCard() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, refetch } = useStoreInfo();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [taxRatePct, setTaxRatePct] = useState("");
  const [receiptLogoUrl, setReceiptLogoUrl] = useState("");
  const [receiptFooter, setReceiptFooter] = useState("");
  const [receiptTaxId, setReceiptTaxId] = useState("");
  const [timezone, setTimezone] = useState("");
  const [hours, setHours] = useState<StoreHourEntry[]>(() => defaultHours());
  const [enforceHours, setEnforceHours] = useState(false);
  const [requirePasskey, setRequirePasskey] = useState(false);
  const [requireGeofence, setRequireGeofence] = useState(false);
  // Lat / lng are stored as strings so the input round-trips an
  // empty "" cleanly (number-state would coerce "" → 0 and pin
  // the geofence to the equator).  Validated on submit.
  const [geoLat,     setGeoLat]     = useState("");
  const [geoLng,     setGeoLng]     = useState("");
  const [geoRadiusM, setGeoRadiusM] = useState("100");
  const [geoBusy,    setGeoBusy]    = useState(false);
  const [geoErr,     setGeoErr]     = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  // Hydrate the form from the read-side row when it arrives.
  // Federal tax is stored as a decimal (0.01 = 1%) but operators
  // think in percents — display + edit accordingly.
  useEffect(() => {
    if (!data?.store) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable store-settings fields from server-fetched row (federal_tax_rate gets a decimal->percent conversion for display)
    setName(data.store.name);
    setEmail(data.store.email);
    setPhone(data.store.phone);
    setAddress(data.store.address);
    setTaxRatePct(((data.store.federal_tax_rate || 0) * 100).toFixed(2));
    setReceiptLogoUrl(data.store.receipt_logo_url);
    setReceiptFooter(data.store.receipt_footer);
    setReceiptTaxId(data.store.receipt_tax_id);
    setTimezone(data.store.timezone);
    setHours(
      data.store.store_hours && data.store.store_hours.length === 7
        ? data.store.store_hours.map((h) => ({ ...h }))
        : defaultHours(),
    );
    setEnforceHours(Boolean(data.store.enforce_business_hours));
    setRequirePasskey(Boolean(data.store.timeclock_require_passkey));
    setRequireGeofence(Boolean(data.store.timeclock_require_geofence));
    setGeoLat(
      data.store.timeclock_geofence_lat == null
        ? "" : String(data.store.timeclock_geofence_lat),
    );
    setGeoLng(
      data.store.timeclock_geofence_lng == null
        ? "" : String(data.store.timeclock_geofence_lng),
    );
    setGeoRadiusM(String(data.store.timeclock_geofence_radius_m ?? 100));
  }, [data]);

  const canEdit =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setOkMsg(null);
    setBusy(true);
    try {
      // Geofence inputs are strings — turn them into numbers (or
      // null) at the boundary so the API contract holds.  Empty
      // lat / lng round-trips as null so the operator can clear
      // the pin without disabling the toggle separately.
      const latNum = geoLat.trim() === "" ? null : Number(geoLat);
      const lngNum = geoLng.trim() === "" ? null : Number(geoLng);
      const radiusNum = Math.max(10, Math.round(Number(geoRadiusM) || 100));
      if (requireGeofence && (latNum == null || lngNum == null)) {
        throw new ApiError(
          400,
          "Pin a location before turning on the geofence — use "
          + "'Use my current location' or enter lat/lng manually.",
          null,
        );
      }
      if (latNum != null && (latNum < -90 || latNum > 90)) {
        throw new ApiError(400, "Latitude must be between -90 and 90.", null);
      }
      if (lngNum != null && (lngNum < -180 || lngNum > 180)) {
        throw new ApiError(400, "Longitude must be between -180 and 180.", null);
      }
      await updateStoreInfo({
        name, email, phone, address,
        federal_tax_rate: Number(taxRatePct) / 100,
        receipt_logo_url: receiptLogoUrl,
        receipt_footer:   receiptFooter,
        receipt_tax_id:   receiptTaxId,
        timezone,
        store_hours: hours,
        enforce_business_hours:     enforceHours,
        timeclock_require_passkey:  requirePasskey,
        timeclock_require_geofence: requireGeofence,
        timeclock_geofence_lat:     latNum,
        timeclock_geofence_lng:     lngNum,
        timeclock_geofence_radius_m: radiusNum,
      });
      await queryClient.invalidateQueries({
        queryKey: ["admin", "store-info"],
      });
      setOkMsg("Store info saved.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <Card>
        <SectionTitle>Store</SectionTitle>
        <p className={styles.muted}>
          Sign in as a store admin to manage store info.
        </p>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <SectionTitle>Store</SectionTitle>
        <Loading />
      </Card>
    );
  }
  if (isError || !data) {
    return (
      <Card>
        <SectionTitle>Store</SectionTitle>
        <ErrorState
          message="Could not load store info."
          onRetry={() => { void refetch(); }}
        />
      </Card>
    );
  }

  return (
    <Card>
      <SectionTitle>Store</SectionTitle>
      <p className={styles.slugRow}>
        Slug <code className={styles.slug}>{data.store.slug}</code>{" "}
        · plan {data.store.plan}
      </p>
      <form onSubmit={onSubmit} className={styles.storeGrid}>
        <Field label="Store name">
          <Input type="text" value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={!canEdit} required />
        </Field>
        <Field label="Email">
          <Input type="email" value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={!canEdit} />
        </Field>
        <Field label="Phone">
          <Input type="tel" value={phone}
            onChange={(e) => setPhone(e.target.value)}
            disabled={!canEdit} />
        </Field>
        <Field label="Address">
          <Input type="text" value={address}
            onChange={(e) => setAddress(e.target.value)}
            disabled={!canEdit} />
        </Field>
        <Field label="Federal tax rate (%)">
          <Input type="number" step="0.01" min="0" max="100"
            value={taxRatePct}
            onChange={(e) => setTaxRatePct(e.target.value)}
            disabled={!canEdit} />
        </Field>
        <Field
          label="Timezone"
          hint="Default timezone for date / time rendering. Cashiers can override on their personal profile. Empty = use the browser default."
        >
          <Select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            disabled={!canEdit}
          >
            <option value="">Use browser default</option>
            {(data.store.timezone_choices ?? []).map((tz) => (
              <option key={tz} value={tz}>{tz}</option>
            ))}
          </Select>
        </Field>
        {/* Receipt customization fields are intentionally hidden —
           DineroBook is a ledger, not a money-transmitter, so
           customer-facing receipts don't belong here. The columns
           still live on Store and the state hooks above still
           hydrate / send them (empty strings round-trip cleanly)
           so re-enabling is a single-file revert. See App.tsx
           lazy-import comment for the matching route hide. */}
        <div className={styles.spanFull}>
          <SectionTitle>Business hours</SectionTitle>
          <p className={styles.helpText}>
            One row per day (Monday-first). Toggle "Closed" to mark
            the day off; open / close times use 24-hour
            <code> HH:MM</code> format. Saving with no edits keeps
            the default Mon-Sat 9-6 / Sun closed template.
          </p>
          <StoreHoursEditor
            hours={hours}
            onChange={setHours}
            disabled={!canEdit}
          />
          <label className={styles.enforceRow}>
            <input
              type="checkbox"
              checked={enforceHours}
              disabled={!canEdit}
              onChange={(e) => setEnforceHours(e.target.checked)}
            />{" "}
            Block transfers outside these hours
            <span className={styles.enforceHint}>
              {" "}— refuses transfer saves with an error when
              outside the open window. The soft warning on the New
              Transfer form fires regardless of this toggle.
            </span>
          </label>
          <label className={styles.enforceRow}>
            <input
              type="checkbox"
              checked={requirePasskey}
              disabled={!canEdit}
              onChange={(e) => setRequirePasskey(e.target.checked)}
            />{" "}
            Block time-clock punches without a passkey
            <span className={styles.enforceHint}>
              {" "}— anti-buddy-punching: every clock-in / clock-out
              demands a fresh Windows Hello / Touch ID / Face ID
              prompt. Enroll each cashier's device from
              {" "}<code>/app/admin/timeclock/credentials</code>
              {" "}before flipping this on.
            </span>
          </label>
          <GeofenceSettingsSection
            canEdit={canEdit}
            requireGeofence={requireGeofence}
            onChangeRequireGeofence={setRequireGeofence}
            geoLat={geoLat}     onChangeGeoLat={setGeoLat}
            geoLng={geoLng}     onChangeGeoLng={setGeoLng}
            geoRadiusM={geoRadiusM}
            onChangeGeoRadiusM={setGeoRadiusM}
            geoBusy={geoBusy} setGeoBusy={setGeoBusy}
            geoErr={geoErr}   setGeoErr={setGeoErr}
          />
        </div>
        {err && (
          <div className={styles.spanFull}>
            <Alert tone="error">{err}</Alert>
          </div>
        )}
        {okMsg && (
          <div className={styles.spanFull}>
            <Alert tone="success">{okMsg}</Alert>
          </div>
        )}
        {canEdit && (
          <div className={styles.spanFullRight}>
            <Button type="submit" busy={busy} disabled={busy || !name}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        )}
      </form>
    </Card>
  );
}

// Geofence settings — pinned lat/lng + radius + the gate toggle.
// Lives under the time-clock section of the store form because
// "block punches outside the store's location" reads as a sibling
// of the existing passkey gate.  Lat/lng are kept as strings up
// here so the inputs can clear cleanly; StoreInfoCard.onSubmit
// coerces + validates them at the boundary.
function GeofenceSettingsSection({
  canEdit,
  requireGeofence, onChangeRequireGeofence,
  geoLat,     onChangeGeoLat,
  geoLng,     onChangeGeoLng,
  geoRadiusM, onChangeGeoRadiusM,
  geoBusy, setGeoBusy,
  geoErr,  setGeoErr,
}: {
  canEdit: boolean;
  requireGeofence: boolean;
  onChangeRequireGeofence: (v: boolean) => void;
  geoLat: string;     onChangeGeoLat: (v: string) => void;
  geoLng: string;     onChangeGeoLng: (v: string) => void;
  geoRadiusM: string; onChangeGeoRadiusM: (v: string) => void;
  geoBusy: boolean;   setGeoBusy: (v: boolean) => void;
  geoErr:  string | null;
  setGeoErr: (v: string | null) => void;
}) {
  async function readMyLocation() {
    setGeoErr(null);
    setGeoBusy(true);
    try {
      // 10s timeout matches the punch-flow read so admins
      // calibrate against the same accuracy budget cashiers hit.
      const coords = await getCurrentCoordinates();
      onChangeGeoLat(coords.lat.toFixed(6));
      onChangeGeoLng(coords.lng.toFixed(6));
    } catch (err) {
      if (err instanceof GeolocationDeniedError
          || err instanceof GeolocationUnavailableError) {
        setGeoErr(err.message);
      } else if (err instanceof Error) {
        setGeoErr(err.message);
      } else {
        setGeoErr("Could not read the current location.");
      }
    } finally {
      setGeoBusy(false);
    }
  }

  return (
    <>
      <label className={styles.enforceRow}>
        <input
          type="checkbox"
          checked={requireGeofence}
          disabled={!canEdit}
          onChange={(e) => onChangeRequireGeofence(e.target.checked)}
        />{" "}
        Block time-clock punches outside the store's location
        <span className={styles.enforceHint}>
          {" "}— anti-buddy-punching: pin a lat/lng + radius below,
          then every clock-in / clock-out checks the cashier's
          browser GPS against the pin. Refused when outside the
          radius or when GPS permission is denied.
        </span>
      </label>
      <div className={styles.geofenceGrid}>
        <Field label="Latitude" hint="-90 to 90">
          <Input
            type="number" step="0.000001" min="-90" max="90"
            value={geoLat}
            onChange={(e) => onChangeGeoLat(e.target.value)}
            disabled={!canEdit}
          />
        </Field>
        <Field label="Longitude" hint="-180 to 180">
          <Input
            type="number" step="0.000001" min="-180" max="180"
            value={geoLng}
            onChange={(e) => onChangeGeoLng(e.target.value)}
            disabled={!canEdit}
          />
        </Field>
        <Field
          label="Radius (meters)"
          hint="Minimum 10m. Typical storefront: 50–150m."
        >
          <Input
            type="number" step="1" min="10"
            value={geoRadiusM}
            onChange={(e) => onChangeGeoRadiusM(e.target.value)}
            disabled={!canEdit}
          />
        </Field>
      </div>
      {canEdit && (
        <div className={styles.geofenceActions}>
          <Button
            type="button" tone="secondary" busy={geoBusy}
            disabled={geoBusy} onClick={() => { void readMyLocation(); }}
          >
            {geoBusy ? "Reading…" : "Use my current location"}
          </Button>
          <span className={styles.enforceHint}>
            Stand at the storefront on the device you'll punch
            from. The browser will prompt for location permission.
          </span>
        </div>
      )}
      {geoErr && (
        <div className={styles.spanFull}>
          <Alert tone="error">{geoErr}</Alert>
        </div>
      )}
    </>
  );
}

function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setOkMsg(null);
    setBusy(true);
    try {
      await changePassword({
        current_password: current,
        new_password:     next,
        confirm_password: confirm,
      });
      setOkMsg("Password updated.");
      setCurrent(""); setNext(""); setConfirm("");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not update password.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionTitle>Change password</SectionTitle>
      <form onSubmit={onSubmit} className={styles.passwordForm}>
        <Field label="Current password">
          <Input
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </Field>
        <Field label="New password (≥ 8 chars)">
          <Input
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </Field>
        <Field label="Confirm new password">
          <Input
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </Field>
        {error && <Alert tone="error">{error}</Alert>}
        {okMsg && <Alert tone="success">{okMsg}</Alert>}
        <Button
          type="submit"
          busy={busy}
          disabled={busy || !current || !next || !confirm}
        >
          {busy ? "Saving…" : "Update password"}
        </Button>
      </form>
    </Card>
  );
}

// ── Store hours ───────────────────────────────────────────────

const DAY_LABELS = [
  "Monday", "Tuesday", "Wednesday", "Thursday",
  "Friday", "Saturday", "Sunday",
] as const;

// Mirrors ``Services.store_hours.DEFAULT_HOURS`` so the UI can
// hydrate a complete schedule when the column is NULL.
function defaultHours(): StoreHourEntry[] {
  return [
    { day: 0, open: "09:00", close: "18:00", closed: false },
    { day: 1, open: "09:00", close: "18:00", closed: false },
    { day: 2, open: "09:00", close: "18:00", closed: false },
    { day: 3, open: "09:00", close: "18:00", closed: false },
    { day: 4, open: "09:00", close: "18:00", closed: false },
    { day: 5, open: "09:00", close: "18:00", closed: false },
    { day: 6, open: "10:00", close: "14:00", closed: true },
  ];
}

function StoreHoursEditor({
  hours, onChange, disabled,
}: {
  hours: StoreHourEntry[];
  onChange: (next: StoreHourEntry[]) => void;
  disabled: boolean;
}) {
  function setRow(idx: number, patch: Partial<StoreHourEntry>) {
    onChange(hours.map((h, i) => (i === idx ? { ...h, ...patch } : h)));
  }
  return (
    <div className={styles.hoursTable}>
      {hours.map((row, i) => (
        <Fragment key={row.day}>
          <span
            className={`${styles.hoursDay} ${row.closed ? styles.hoursClosed : ""}`}
          >
            {DAY_LABELS[row.day]}
          </span>
          <label>
            <input
              type="checkbox"
              checked={row.closed}
              disabled={disabled}
              onChange={(e) => setRow(i, { closed: e.target.checked })}
            />{" "}
            Closed
          </label>
          <Input
            type="time"
            value={row.open}
            disabled={disabled || row.closed}
            className={styles.hoursTime}
            onChange={(e) => setRow(i, { open: e.target.value })}
            aria-label={`${DAY_LABELS[row.day]} open time`}
          />
          <span className={styles.hoursDashCell}>—</span>
          <Input
            type="time"
            value={row.close}
            disabled={disabled || row.closed}
            className={styles.hoursTime}
            onChange={(e) => setRow(i, { close: e.target.value })}
            aria-label={`${DAY_LABELS[row.day]} close time`}
          />
        </Fragment>
      ))}
    </div>
  );
}
