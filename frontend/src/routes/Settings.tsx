import { Fragment, useEffect, useState, type FormEvent } from "react";
import { Outlet } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  changePassword,
  deletePasskey,
  registerPasskey,
  updateProfile,
  updateStoreInfo,
  usePasskeys,
  useProfile,
  useStoreInfo,
  type MTCompanyEntry,
  type ProfileUpdateBody,
  type StoreHourEntry,
} from "../api/account";
import { redeemConnectCode } from "../api/owner";
import { ApiError } from "../lib/api";
import { formatDate, formatTimestamp } from "../lib/datetime";
import { timezoneFromAddress } from "../lib/timezoneFromAddress";
import { getCurrentIdentity } from "../lib/auth";
import { passkeysSupported } from "../lib/webauthn";
import { useUnsavedChangesGuard } from "../lib/useUnsavedChangesGuard";
import {
  Alert, Button, ButtonLink, Card, Checkbox, ConfirmDialog, ErrorState, Field,
  InfoTip, Input, Loading, PageHeader, PageShell, Pill, SectionTitle, Select,
  space, Switch, TabsBar, TabsLink, useToast,
  Empty,
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
  const role = identity?.role;
  const showGeneral = role !== "superadmin";
  const showBilling = role !== "owner" && role !== "superadmin";
  const showReferrals = role === "admin";

  return (
    <PageShell maxWidth="60rem" gap="1rem">

      <PageHeader title="Settings" subtitle={identity?.username || "—"} />

      <TabsBar>
        <TabsLink to="/settings/profile">Profile</TabsLink>
        {showGeneral && <TabsLink to="/settings/general">General</TabsLink>}
        {showBilling && <TabsLink to="/settings/billing">Billing</TabsLink>}
        {showReferrals && <TabsLink to="/settings/referrals">Referrals</TabsLink>}
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
  return (
    <>
      <StoreInfoCard />
      <OwnerAccessCard />
    </>
  );
}

export function SettingsBilling() {
  return <SubscriptionCard />;
}

export function SettingsSecurity() {
  return (
    <>
      <ChangePasswordCard />
      <PasskeysCard />
      <DataExportCard />
    </>
  );
}


function DataExportCard() {
  const [busy, setBusy] = useState(false);
  async function handleExport() {
    setBusy(true);
    try {
      const resp = await fetch("/api/v2/auth/account/export", {
        credentials: "include",
      });
      if (!resp.ok) throw new Error("Export failed");
      const blob = await resp.blob();
      const cd = resp.headers.get("content-disposition") || "";
      const match = cd.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : "dinerobook-data.json";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <SectionTitle>
        Download your data
        <InfoTip text="Exports a JSON file with your profile, notification preferences, session history, registered passkeys, and audit log entries." />
      </SectionTitle>
      <Button onClick={() => { void handleExport(); }} busy={busy} type="button">
        Download my data (JSON)
      </Button>
    </Card>
  );
}

function ProfileCard() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useProfile();
  const { data: storeInfo } = useStoreInfo();
  const storeTz = storeInfo?.store?.timezone ?? "";

  const toast = useToast();
  const [draft, setDraft] = useState<ProfileUpdateBody>({});
  // Last-saved snapshot; the form is "dirty" when `draft` drifts from it.
  const [baseline, setBaseline] = useState<ProfileUpdateBody>({});
  const [busy, setBusy]   = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!data) return;
    // Admin / owner accounts sign in with their email (it's stored as
    // the `username`), and the separate notices `email` is left blank
    // at signup. Surface the login email as the Email so the field
    // isn't confusingly empty; saving persists it so notices reach
    // the same address. Employees (username isn't an email) are
    // untouched.
    const loginIsEmail = (data.username || "").includes("@");
    const hydrated: ProfileUpdateBody = {
      full_name:        data.full_name,
      email:            data.email || (loginIsEmail ? data.username : ""),
      phone:            data.phone,
      theme_preference: data.theme_preference,
    };
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable draft + dirty baseline from server-fetched profile so inputs are controlled from first paint
    setDraft(hydrated);
    setBaseline(hydrated);
  }, [data]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  // Arm the browser "leave site?" prompt while there are unsaved edits.
  useUnsavedChangesGuard(isDirty && !busy);

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
      setBaseline(draft);  // edits are now the saved state — clear dirty
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

  // Email-login accounts (admin / owner) sign in with their email —
  // there's no separate username to show, so we hide that read-only
  // row and treat the Email field as the login/account email.
  const loginIsEmail = data.username.includes("@");

  return (
    <Card>
      <SectionTitle>Personal info</SectionTitle>
      <p className={styles.profileLead}>
        Used for things addressed to you personally — receipts,
        password-reset emails, audit-log attribution. Your
        {loginIsEmail ? " role is" : " username and role are"} set by
        your store admin and shown here for reference.
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
          hint={loginIsEmail
            ? "Your sign-in email. We also use it for password reset and account notices."
            : "We use this for password reset and account notices. Leave blank if you'd rather not receive email."}
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

        {/* Per-user timezone was removed — these are brick-and-mortar
            stores, so date/time rendering follows the store's timezone
            (set on Settings → General, suggested from the address). One
            timezone per store keeps reports + audit trails consistent
            across the whole team. */}

        <Field
          label={<>Appearance<InfoTip text="Follows you to every browser you sign in on. The topbar toggle is a quicker shortcut for the same setting." /></>}
          error={fieldErrors.theme_preference}
        >
          <Switch
            checked={(draft.theme_preference ?? "dark") === "light"}
            onChange={(on) =>
              set("theme_preference", on ? "light" : "dark")
            }
            disabled={busy}
          >
            Light theme (dark is the default)
          </Switch>
        </Field>

        <hr className={styles.profileHr} />

        <div className={styles.profileReadOnlyGrid}>
          {!loginIsEmail && (
            <ProfileReadOnly label="Username" value={data.username} />
          )}
          <ProfileReadOnly label="Role" value={
            data.role.charAt(0).toUpperCase() + data.role.slice(1)
          } />
          <ProfileReadOnly label="Member since" value={memberSince} />
          <ProfileReadOnly label="Last sign-in" value={lastLogin} />
        </div>

        <div style={{ marginTop: space.sm, display: "flex", gap: "0.6rem", alignItems: "center" }}>
          <Button type="submit" busy={busy} disabled={busy || !isDirty}>
            {busy ? "Saving…" : "Save profile"}
          </Button>
          {isDirty && !busy && (
            <Pill tone="warning" dot>Unsaved changes</Pill>
          )}
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
        <Empty>No passkeys registered yet.</Empty>
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
                  Added {formatDate(p.created_at)}
                  {p.last_used_at &&
                    ` · last used ${formatDate(p.last_used_at)}`}
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
  const [legalName, setLegalName] = useState("");
  const [ein, setEin] = useState("");
  const [businessAddress, setBusinessAddress] = useState("");
  const [taxRatePct, setTaxRatePct] = useState("");
  const [salesTaxPct, setSalesTaxPct] = useState("");
  const [receiptLogoUrl, setReceiptLogoUrl] = useState("");
  const [receiptFooter, setReceiptFooter] = useState("");
  const [receiptTaxId, setReceiptTaxId] = useState("");
  const [timezone, setTimezone] = useState("");
  const [hours, setHours] = useState<StoreHourEntry[]>(() => defaultHours());
  const [enforceHours, setEnforceHours] = useState(false);
  // Money-transfer company roster (name + enabled toggle). Saved
  // with the rest of the tab; `newCompany` is the transient add-row
  // input and deliberately NOT part of the dirty snapshot.
  const [mtCompanies, setMtCompanies] = useState<MTCompanyEntry[]>([]);
  const [newCompany, setNewCompany] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Last-saved snapshot (JSON) — the form is dirty when it drifts.
  const [baseline, setBaseline] = useState<string>("");
  const toast = useToast();

  // Serialize every editable field into one comparable snapshot. Same
  // key order here + at hydrate so the dirty compare is stable.
  const snapshot = (
    h: StoreHourEntry[], enforce: boolean, companies: MTCompanyEntry[],
  ) => JSON.stringify({
    name, email, phone, address, legalName, ein, businessAddress,
    taxRatePct, salesTaxPct, receiptLogoUrl, receiptFooter, receiptTaxId,
    timezone, hours: h, enforceHours: enforce, mtCompanies: companies,
  });

  // Hydrate the form from the read-side row when it arrives.
  // Federal tax is stored as a decimal (0.01 = 1%) but operators
  // think in percents — display + edit accordingly.
  useEffect(() => {
    if (!data?.store) return;
    const hydratedHours =
      data.store.store_hours && data.store.store_hours.length === 7
        ? data.store.store_hours.map((h) => ({ ...h }))
        : defaultHours();
    const taxPct = ((data.store.federal_tax_rate || 0) * 100).toFixed(2);
    const salesPct = ((data.store.sales_tax_rate || 0) * 100).toFixed(2);
    const enforce = Boolean(data.store.enforce_business_hours);
    const companies = (data.store.mt_companies ?? []).map((c) => ({ ...c }));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable store-settings fields + dirty baseline from server-fetched row (federal_tax_rate gets a decimal->percent conversion for display)
    setName(data.store.name);
    setEmail(data.store.email);
    setPhone(data.store.phone);
    setAddress(data.store.address);
    setLegalName(data.store.legal_name);
    setEin(data.store.ein);
    setBusinessAddress(data.store.business_address);
    setTaxRatePct(taxPct);
    setSalesTaxPct(salesPct);
    setReceiptLogoUrl(data.store.receipt_logo_url);
    setReceiptFooter(data.store.receipt_footer);
    setReceiptTaxId(data.store.receipt_tax_id);
    setTimezone(data.store.timezone);
    setHours(hydratedHours);
    setEnforceHours(enforce);
    setMtCompanies(companies);
    // Baseline mirrors the snapshot() shape exactly (same key order).
    setBaseline(JSON.stringify({
      name: data.store.name, email: data.store.email,
      phone: data.store.phone, address: data.store.address,
      legalName: data.store.legal_name, ein: data.store.ein,
      businessAddress: data.store.business_address,
      taxRatePct: taxPct, salesTaxPct: salesPct,
      receiptLogoUrl: data.store.receipt_logo_url,
      receiptFooter: data.store.receipt_footer,
      receiptTaxId: data.store.receipt_tax_id,
      timezone: data.store.timezone,
      hours: hydratedHours, enforceHours: enforce,
      mtCompanies: companies,
    }));
  }, [data]);

  const canEdit =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";

  const isDirty =
    baseline !== "" && snapshot(hours, enforceHours, mtCompanies) !== baseline;
  // Arm the browser "leave site?" prompt while there are unsaved edits.
  useUnsavedChangesGuard(isDirty && !busy && canEdit);

  function addCompany() {
    const trimmed = newCompany.trim();
    if (!trimmed) return;
    if (trimmed.includes(",")) {
      toast({ message: "Company names can’t contain commas.", tone: "info" });
      return;
    }
    if (mtCompanies.some((c) => c.name.toLowerCase() === trimmed.toLowerCase())) {
      toast({ message: `${trimmed} is already on the roster.`, tone: "info" });
      return;
    }
    setMtCompanies((list) => [...list, { name: trimmed, enabled: true }]);
    setNewCompany("");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await updateStoreInfo({
        name, email, phone, address,
        legal_name: legalName,
        ein,
        business_address: businessAddress,
        federal_tax_rate: Number(taxRatePct) / 100,
        sales_tax_rate: Number(salesTaxPct) / 100,
        receipt_logo_url: receiptLogoUrl,
        receipt_footer:   receiptFooter,
        receipt_tax_id:   receiptTaxId,
        timezone,
        store_hours: hours,
        enforce_business_hours:     enforceHours,
        mt_companies: mtCompanies,
      });
      await queryClient.invalidateQueries({
        queryKey: ["admin", "store-info"],
      });
      // Edits are now the saved state — clear the dirty flag.
      setBaseline(snapshot(hours, enforceHours, mtCompanies));
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
          <Field
            label={<>Timezone<InfoTip text="Used for every date and time across the store — reports, audit trails, receipts. Set it once here; “Detect from address” suggests it from the address above." /></>}
          >
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              <Select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                disabled={!canEdit}
                style={{ flex: "1 1 auto" }}
              >
                <option value="">Use browser default</option>
                {(data.store.timezone_choices ?? []).map((tz) => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </Select>
              <Button
                type="button"
                tone="secondary"
                size="sm"
                disabled={!canEdit || !address.trim()}
                onClick={() => {
                  const detected = timezoneFromAddress(address);
                  if (detected) {
                    setTimezone(detected);
                    toast({
                      message: `Timezone set to ${detected} from the address. Adjust if needed, then save.`,
                      tone: "success",
                    });
                  } else {
                    toast({
                      message: "Couldn’t detect a US state from the address — pick a timezone manually.",
                      tone: "info",
                    });
                  }
                }}
              >
                Detect from address
              </Button>
            </div>
          </Field>
        </div>
      </Card>

      {/* Money-transfer company roster. Toggle OFF hides a company
          from the daily book + transfer form without deleting it
          (historical days keep showing its data); Remove drops it
          from the roster entirely. Saved with the rest of the tab. */}
      <Card>
        <SectionTitle>
          Money transfer companies
          <InfoTip text="The companies available in the daily book's money-transfer breakdown and the transfer form. Toggle one off to hide it without losing its history; remove it to take it off the roster entirely." />
        </SectionTitle>
        <div style={{ display: "flex", flexDirection: "column", gap: space.sm }}>
          {mtCompanies.map((c, i) => (
            <div
              key={c.name}
              style={{ display: "flex", alignItems: "center", gap: space.md }}
            >
              <Switch
                checked={c.enabled}
                disabled={!canEdit}
                onChange={(next) =>
                  setMtCompanies((list) =>
                    list.map((row, j) =>
                      j === i ? { ...row, enabled: next } : row,
                    ),
                  )
                }
              >
                {c.name}
              </Switch>
              {!c.enabled && (
                <Pill tone="neutral">Hidden</Pill>
              )}
              <Button
                type="button"
                tone="ghost"
                size="sm"
                disabled={!canEdit || mtCompanies.length <= 1}
                onClick={() =>
                  setMtCompanies((list) => list.filter((_, j) => j !== i))
                }
                style={{ marginLeft: "auto" }}
              >
                Remove
              </Button>
            </div>
          ))}
        </div>
        <div
          style={{
            display: "flex", gap: space.sm, alignItems: "center",
            marginTop: space.md, maxWidth: "26rem",
          }}
        >
          <Input
            type="text"
            value={newCompany}
            onChange={(e) => setNewCompany(e.target.value)}
            placeholder="Add a company (e.g. Ria)"
            maxLength={40}
            disabled={!canEdit}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                // Enter adds the company instead of submitting the
                // whole settings form.
                e.preventDefault();
                addCompany();
              }
            }}
          />
          <Button
            type="button"
            tone="secondary"
            size="sm"
            disabled={!canEdit || !newCompany.trim()}
            onClick={addCompany}
          >
            Add
          </Button>
        </div>
      </Card>

      {/* Business / Legal is its own card — the compliance identity +
          tax config, kept apart from the day-to-day store contact
          fields above. (It used to be a bare <SectionTitle> dropped
          mid-grid, which rendered as a stray one-column cell.) */}
      <Card>
        <SectionTitle>
          Business / Legal
          <InfoTip text="Compliance identity and tax rates — used on tax exports and filings. Leave blank if they match the store info above." />
        </SectionTitle>
        <div className={styles.storeGrid}>
          <Field label={<>Legal name<InfoTip text="Official business name for compliance filings." /></>}>
            <Input type="text" value={legalName}
              onChange={(e) => setLegalName(e.target.value)}
              disabled={!canEdit} />
          </Field>
          <Field label={<>EIN<InfoTip text="Federal employer identification number." /></>}>
            <Input type="text" value={ein} placeholder="XX-XXXXXXX"
              maxLength={20}
              onChange={(e) => setEin(e.target.value)}
              disabled={!canEdit} />
          </Field>
          <Field label={<>Business address<InfoTip text="Legal address, if different from the store address." /></>}>
            <Input type="text" value={businessAddress}
              onChange={(e) => setBusinessAddress(e.target.value)}
              disabled={!canEdit} />
          </Field>
          <Field label="Federal tax rate (%)">
            <Input type="number" step="0.01" min="0" max="100"
              value={taxRatePct}
              onChange={(e) => setTaxRatePct(e.target.value)}
              disabled={!canEdit} />
          </Field>
          <Field
            label={<>Sales tax rate (%)<InfoTip text="Applied to a day's Taxable Sales in the daily book. When set, Sales Tax auto-calculates and can't be edited by hand. Leave at 0 to enter Sales Tax manually." /></>}
          >
            <Input type="number" step="0.01" min="0" max="100"
              value={salesTaxPct}
              onChange={(e) => setSalesTaxPct(e.target.value)}
              disabled={!canEdit} />
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
        <SectionTitle>
          Business hours
          <InfoTip text='One row per day (Monday-first). Toggle "Closed" to mark the day off; open and close times use 24-hour HH:MM format. Saving with no edits keeps the default Mon-Sat 9-6 / Sun closed template.' />
        </SectionTitle>
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

      {err && <Alert tone="error">{err}</Alert>}

      {canEdit && (
        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "0.6rem" }}>
          {isDirty && !busy && (
            <Pill tone="warning" dot>Unsaved changes</Pill>
          )}
          <Button type="submit" busy={busy} disabled={busy || !name || !isDirty}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      )}
    </form>
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


function OwnerAccessCard() {
  const toast = useToast();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [linked, setLinked] = useState<string | null>(null);

  async function handleRedeem(e: FormEvent) {
    e.preventDefault();
    if (!code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await redeemConnectCode(code.trim());
      setLinked(result.owner_name);
      setCode("");
      toast({ message: `Store linked to owner "${result.owner_name}"`, tone: "success" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not redeem code.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionTitle>
        Owner access
        <InfoTip text="If a multi-store owner gave you a connect code, enter it here to link this store to their umbrella." />
      </SectionTitle>
      {linked && (
        <Alert tone="success">
          Linked to owner: <strong>{linked}</strong>
        </Alert>
      )}
      {error && <Alert tone="error">{error}</Alert>}
      <form onSubmit={(e) => { void handleRedeem(e); }} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end" }}>
        <Field label="Connect code">
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="ABCD1234"
            maxLength={8}
            style={{ fontFamily: "var(--db-font-mono, monospace)", letterSpacing: "0.15em", width: "12rem" }}
          />
        </Field>
        <Button type="submit" busy={busy} disabled={!code.trim()}>
          Link store
        </Button>
      </form>
    </Card>
  );
}
