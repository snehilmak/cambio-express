import { Fragment, useEffect, useState, type FormEvent } from "react";
import { Outlet } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  changePassword,
  deletePasskey,
  passkeysSupported,
  registerPasskey,
  updateProfile,
  updateStoreInfo,
  usePasskeys,
  useProfile,
  useStoreInfo,
  type ProfileUpdateBody,
  type StoreHourEntry,
} from "../api/account";
import { ApiError } from "../lib/api";
import { formatTimestamp } from "../lib/datetime";
import { getCurrentIdentity } from "../lib/auth";
import {
  GeolocationDeniedError,
  GeolocationUnavailableError,
  getCurrentCoordinates,
} from "../lib/geolocation";
import {
  Breadcrumbs,
  Alert, Button, ButtonLink, Card, Checkbox, ConfirmDialog, ErrorState, Field,
  Input, Loading, PageHeader, PageShell, SectionTitle, Select, space, Switch,
  TabsBar, TabsLink, useToast,
} from "../components/ui";
import styles from "./Settings.module.css";

// /app/settings — tabbed admin / account hub.  The route is a
// LAYOUT route (this default export renders the page chrome +
// `<Outlet />`); each tab is a child route mounted in App.tsx
// (`SettingsGeneral`, `SettingsTeam`, `SettingsBilling`,
// `SettingsSecurity`).  Tab URLs are deep-linkable, browser back
// works correctly, and each section's form-save logic stays
// independent.
//
// /app/settings (no sub-path) redirects to /app/settings/general
// so existing inbound links keep working.

export default function Settings() {
  const identity = getCurrentIdentity();
  // Owners run cross-store via the umbrella — billing happens
  // per-store inside each connected store's admin context, not
  // at the owner level.  The /settings/billing route still
  // exists (SubscriptionCard renders empty for store_id == null),
  // but the tab is hidden from the bar so owners don't click into
  // a no-op page.
  const isOwner = identity?.role === "owner";

  return (
    <PageShell maxWidth="60rem" gap="1rem">

      <Breadcrumbs crumbs={[{ label: "Settings" }]} />

      <PageHeader title="Settings" subtitle={identity?.username || "—"} />

      <TabsBar>
        <TabsLink to="/settings/profile">Profile</TabsLink>
        <TabsLink to="/settings/general">General</TabsLink>
        {!isOwner && <TabsLink to="/settings/billing">Billing</TabsLink>}
        <TabsLink to="/settings/security">Security</TabsLink>
      </TabsBar>

      <Outlet />
    </PageShell>
  );
}


/** Tab content components.  Each is registered as a child route in
 *  App.tsx.  They wrap the existing pre-tabs `…Card` components
 *  unchanged, so the form-save logic + state management didn't have
 *  to be rewritten — the refactor is purely structural.  */
export function SettingsProfile() {
  return <ProfileCard />;
}

export function SettingsGeneral() {
  return <StoreInfoCard />;
}

export function SettingsBilling() {
  return <SubscriptionCard />;
}

export function SettingsSecurity() {
  return (
    <>
      <ChangePasswordCard />
      <PasskeysCard />
    </>
  );
}

function ProfileCard() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useProfile();
  const { data: storeInfo } = useStoreInfo();
  const storeTz = storeInfo?.store?.timezone ?? "";

  const toast = useToast();
  const [draft, setDraft] = useState<ProfileUpdateBody>({});
  const [busy, setBusy]   = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!data) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable draft from server-fetched profile so inputs are controlled from first paint
    setDraft({
      full_name:        data.full_name,
      email:            data.email,
      phone:            data.phone,
      timezone:         data.timezone,
      theme_preference: data.theme_preference,
    });
  }, [data]);

  function set<K extends keyof ProfileUpdateBody>(
    key: K, value: ProfileUpdateBody[K],
  ) {
    setDraft((d) => ({ ...d, [key]: value }));
    if (fieldErrors[key as string]) {
      setFieldErrors((e) => {
        const next = { ...e }; delete next[key as string]; return next;
      });
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!data) return;
    setBusy(true);
    setServerError(null);
    setFieldErrors({});
    try {
      await updateProfile(draft);
      toast({ message: "Profile updated.", tone: "success" });
      queryClient.invalidateQueries({ queryKey: ["account", "profile"] });
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const detail = (err.body as { detail?: { field_errors?: Record<string, string> } })?.detail;
        if (detail?.field_errors) {
          setFieldErrors(detail.field_errors);
        } else {
          setServerError(err.message);
        }
      } else if (err instanceof ApiError) {
        setServerError(err.message);
      } else {
        setServerError("Network error. Try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) {
    return <Card><SectionTitle>Personal info</SectionTitle><Loading /></Card>;
  }
  if (isError || !data) {
    return (
      <Card>
        <SectionTitle>Personal info</SectionTitle>
        <ErrorState
          message={`Couldn't load your profile.${error instanceof Error ? ` ${error.message}` : ""}`}
          onRetry={() => { void refetch(); }}
        />
      </Card>
    );
  }

  const memberSince = data.created_at
    ? new Date(data.created_at).toLocaleDateString("en-US", {
        month: "short", day: "2-digit", year: "numeric",
      })
    : "—";
  const lastLogin = data.last_login_at
    ? formatTimestamp(data.last_login_at, {
        userTimezone: data.timezone,
        storeTimezone: storeTz,
      })
    : "—";

  return (
    <Card>
      <SectionTitle>Personal info</SectionTitle>
      <p className={styles.profileLead}>
        Used for things addressed to you personally — receipts,
        password-reset emails, audit-log attribution. Your
        username and role are set by your store admin and shown
        here for reference.
      </p>

      {serverError && <Alert tone="error">{serverError}</Alert>}

      <form
        onSubmit={onSubmit}
        autoComplete="off"
        style={{ display: "flex", flexDirection: "column", gap: space.lg, marginTop: space.lg }}
      >
        <Field label="Display name *" error={fieldErrors.full_name}>
          <Input
            type="text" maxLength={120} required
            value={draft.full_name ?? ""}
            onChange={(e) => set("full_name", e.target.value)}
            disabled={busy}
          />
        </Field>

        <Field
          label="Email"
          error={fieldErrors.email}
          hint="We use this for password reset and account notices. Leave blank if you'd rather not receive email."
        >
          <Input
            type="email" maxLength={255}
            autoComplete="email"
            placeholder="you@example.com"
            value={draft.email ?? ""}
            onChange={(e) => set("email", e.target.value)}
            disabled={busy}
          />
        </Field>

        <Field label="Phone" error={fieldErrors.phone}>
          <Input
            type="tel" maxLength={40}
            autoComplete="tel"
            placeholder="+1 555 123 4567"
            value={draft.phone ?? ""}
            onChange={(e) => set("phone", e.target.value)}
            disabled={busy}
          />
        </Field>

        <Field
          label="Timezone"
          error={fieldErrors.timezone}
          hint="Daily reports + audit timestamps render in this zone for you. Don't see yours? Ask your admin to add it."
        >
          <Select
            value={draft.timezone ?? ""}
            onChange={(e) => set("timezone", e.target.value)}
            disabled={busy}
          >
            <option value="">— Use store / UTC default —</option>
            {data.timezone_choices.map((tz) => (
              <option key={tz} value={tz}>{tz}</option>
            ))}
          </Select>
        </Field>

        <Field
          label="Appearance"
          error={fieldErrors.theme_preference}
          hint="Follows you to every browser you sign in on. The topbar toggle is a quicker shortcut for the same setting."
        >
          <Select
            value={draft.theme_preference ?? "dark"}
            onChange={(e) =>
              set(
                "theme_preference",
                e.target.value as "dark" | "light",
              )
            }
            disabled={busy}
          >
            <option value="dark">Dark (default)</option>
            <option value="light">Light</option>
          </Select>
        </Field>

        <hr className={styles.profileHr} />

        <div className={styles.profileReadOnlyGrid}>
          <ProfileReadOnly label="Username" value={data.username} />
          <ProfileReadOnly label="Role" value={
            data.role.charAt(0).toUpperCase() + data.role.slice(1)
          } />
          <ProfileReadOnly label="Member since" value={memberSince} />
          <ProfileReadOnly label="Last sign-in" value={lastLogin} />
        </div>

        <div style={{ marginTop: space.sm, display: "flex", gap: "0.6rem" }}>
          <Button type="submit" busy={busy} disabled={busy}>
            {busy ? "Saving…" : "Save profile"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ProfileReadOnly({ label, value }: { label: string; value: string }) {
  return (
    <Field label={label}>
      <Input
        type="text" disabled value={value || "—"}
        style={{ opacity: 0.7, cursor: "not-allowed" }}
      />
    </Field>
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
  // Pending passkey staged for removal — null when no confirm
  // is showing.  Holds id + label so the dialog can reference
  // both without re-resolving from the list.
  const [pendingRemove, setPendingRemove] =
    useState<{ id: number; label: string } | null>(null);
  const supported = passkeysSupported();

  if (identity == null) return null;

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["account", "passkeys"] });
  }

  async function doRemove() {
    if (!pendingRemove) return;
    const { id } = pendingRemove;
    setErr(null); setBusyId(id);
    try {
      await deletePasskey(id);
      refresh();
      setPendingRemove(null);
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
                onClick={() => setPendingRemove({ id: p.id, label: p.name })}
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
      <ConfirmDialog
        open={pendingRemove != null}
        title="Remove passkey"
        message={
          `Remove "${pendingRemove?.label || "this device"}"? `
          + "You can re-enroll it later if you change your mind, but "
          + "anyone with this device will lose passkey access."
        }
        confirmLabel="Remove"
        confirmTone="danger"
        busy={busyId != null}
        onConfirm={() => { void doRemove(); }}
        onCancel={() => setPendingRemove(null)}
      />
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
        <ButtonLink to="/subscribe" tone="primary">
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
  const [lateThreshold, setLateThreshold] = useState("5");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const toast = useToast();

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
    setLateThreshold(
      String(data.store.timeclock_late_minutes_threshold ?? 5),
    );
  }, [data]);

  const canEdit =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
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
        timeclock_late_minutes_threshold: Math.max(
          0, Math.min(240, Math.round(Number(lateThreshold) || 5)),
        ),
      });
      await queryClient.invalidateQueries({
        queryKey: ["admin", "store-info"],
      });
      toast({ message: "Store info saved.", tone: "success" });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  // Owners run the cross-store umbrella, not any single store —
  // per-store fields (name, hours, tax rate, time-clock policy)
  // live inside each connected store's own admin sign-in.  Give
  // them an "Owner umbrella" panel here with shortcuts to the
  // pages where umbrella-level settings actually exist, so the
  // tab isn't a dead-end "you're in the wrong role" message.
  if (identity?.role === "owner") {
    return (
      <Card>
        <SectionTitle>Owner umbrella</SectionTitle>
        <p className={styles.muted}>
          Per-store settings (name, address, tax rate, business
          hours, time-clock policy) live inside each connected
          store's own admin sign-in.  Umbrella-level controls
          live on the Owner pages below.
        </p>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: space.sm,
            marginTop: space.md,
          }}
        >
          <ButtonLink to="/owner/cross-store-defaults" tone="secondary">
            Cross-store defaults →
          </ButtonLink>
          <ButtonLink to="/owner/locations" tone="secondary">
            Locations →
          </ButtonLink>
        </div>
      </Card>
    );
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
    // One form wraps all three cards so the operator can edit
    // anywhere and save the whole tab atomically.  Splitting the
    // form would create "did I save just this section?" doubt.
    <form
      onSubmit={onSubmit}
      style={{ display: "flex", flexDirection: "column", gap: space.lg }}
    >
      <Card>
        <SectionTitle>Store</SectionTitle>
        <p className={styles.slugRow}>
          Slug <code className={styles.slug}>{data.store.slug}</code>{" "}
          · plan {data.store.plan}
        </p>
        <div className={styles.storeGrid}>
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
        </div>
        {/* Receipt customization fields are intentionally hidden —
           DineroBook is a ledger, not a money-transmitter, so
           customer-facing receipts don't belong here. The columns
           still live on Store and the state hooks above still
           hydrate / send them (empty strings round-trip cleanly)
           so re-enabling is a single-file revert. See App.tsx
           lazy-import comment for the matching route hide. */}
      </Card>

      <Card>
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
        <div className={styles.enforceRow}>
          <Switch
            checked={enforceHours}
            disabled={!canEdit}
            onChange={setEnforceHours}
          >
            Block transfers outside these hours
            <span className={styles.enforceHint}>
              {" "}— refuses transfer saves with an error when
              outside the open window. The soft warning on the New
              Transfer form fires regardless of this toggle.
            </span>
          </Switch>
        </div>
      </Card>

      <Card>
        <SectionTitle>Time-clock policy</SectionTitle>
        <p className={styles.helpText}>
          Anti-buddy-punching gates for clock-in / clock-out and
          the lateness threshold used by the payroll view.
        </p>
        <div className={styles.enforceRow}>
          <Switch
            checked={requirePasskey}
            disabled={!canEdit}
            onChange={setRequirePasskey}
          >
            Block time-clock punches without a passkey
            <span className={styles.enforceHint}>
              {" "}— every clock-in / clock-out demands a fresh
              Windows Hello / Touch ID / Face ID prompt. Enroll
              each cashier's device from
              {" "}<code>/app/admin/timeclock/credentials</code>
              {" "}before flipping this on.
            </span>
          </Switch>
        </div>
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
        <Field
          label="Lateness threshold (store-local minutes)"
          hint="The payroll page flags an entry as 'Late' only when clock-in exceeds the planned shift's start by this many minutes. 0–240. Default 5."
        >
          <Input
            type="number" step="1" min="0" max="240"
            value={lateThreshold}
            onChange={(e) => setLateThreshold(e.target.value)}
            disabled={!canEdit}
          />
        </Field>
      </Card>

      {err && <Alert tone="error">{err}</Alert>}

      {canEdit && (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Button type="submit" busy={busy} disabled={busy || !name}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      )}
    </form>
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
      <div className={styles.enforceRow}>
        <Switch
          checked={requireGeofence}
          disabled={!canEdit}
          onChange={onChangeRequireGeofence}
        >
          Block time-clock punches outside the store's location
          <span className={styles.enforceHint}>
            {" "}— anti-buddy-punching: pin a lat/lng + radius below,
            then every clock-in / clock-out checks the cashier's
            browser GPS against the pin. Refused when outside the
            radius or when GPS permission is denied.
          </span>
        </Switch>
      </div>
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
      {geoErr && <Alert tone="error">{geoErr}</Alert>}
    </>
  );
}

function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await changePassword({
        current_password: current,
        new_password:     next,
        confirm_password: confirm,
      });
      toast({ message: "Password updated.", tone: "success" });
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
          <Checkbox
            checked={row.closed}
            disabled={disabled}
            onChange={(next) => setRow(i, { closed: next })}
          >
            Closed
          </Checkbox>
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
