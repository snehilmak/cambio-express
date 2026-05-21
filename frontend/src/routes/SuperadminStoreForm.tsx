import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  createSuperadminStore,
  updateSuperadminStore,
  useSuperadminStore,
  type SuperadminStoreCreateBody,
  type SuperadminStoreUpdateBody,
} from "../api/superadmin";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Alert, Button, ButtonLink, Card, ErrorState, Field, Input, Loading,
  PageHeader, PageShell, SectionTitle, Select,
} from "../components/ui";
import styles from "./SuperadminStoreForm.module.css";

// /app/superadmin/stores/new + /app/superadmin/stores/:id/edit
//
// Migrated from templates/superadmin_store_form.html. The legacy
// form was create-only — adding an inline edit screen here so the
// SPA covers the full lifecycle (which the legacy system handled
// through the per-action POST endpoints in /superadmin/controls
// and never had a unified edit page for the store identity fields).
//
// Field-level errors mirror the create endpoint's 422/409 shape:
//   { detail: { field, message } }
// The SPA renders inline next to the offending input.

const PLAN_OPTIONS: { value: string; label: string }[] = [
  { value: "trial",    label: "Trial" },
  { value: "basic",    label: "Basic" },
  { value: "pro",      label: "Pro" },
  { value: "inactive", label: "Inactive" },
];

const SPAN_2 = { gridColumn: "1 / -1" } as const;

export default function SuperadminStoreForm() {
  const identity = getCurrentIdentity();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const params = useParams<{ id?: string }>();
  const storeId = params.id ? Number(params.id) : null;
  const isEdit = storeId !== null && Number.isFinite(storeId);

  const detailQuery = useSuperadminStore(storeId);

  // Identity fields. Plan defaults to "trial" on create; PATCH
  // hydrates from the loaded row.
  const [name,    setName]    = useState("");
  const [slug,    setSlug]    = useState("");
  const [email,   setEmail]   = useState("");
  const [phone,   setPhone]   = useState("");
  const [address, setAddress] = useState("");
  const [plan,    setPlan]    = useState("trial");
  // Federal tax — stored as a fraction (0.01 = 1%) to match the
  // Store column. Only rendered on edit; create doesn't expose it
  // (the legacy form didn't either; default of 0.01 ships from
  // the Store model definition).
  const [federalTaxRate, setFederalTaxRate] = useState<string>("0.01");

  // Initial admin user — create only.
  const [adminName,     setAdminName]     = useState("Store Admin");
  const [adminUsername, setAdminUsername] = useState("admin");
  const [adminPassword, setAdminPassword] = useState("");

  const [busy,        setBusy]        = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saved,       setSaved]       = useState(false);

  // Hydrate the form once the GET resolves on edit.
  useEffect(() => {
    if (!isEdit) return;
    const s = detailQuery.data?.store;
    if (!s) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable store fields from server-fetched store row on edit
    setName(s.name);
    setSlug(s.slug);
    setEmail(s.email);
    setPhone(s.phone);
    setAddress(s.address);
    setPlan(s.plan || "trial");
    setFederalTaxRate(String(s.federal_tax_rate ?? 0.01));
  }, [detailQuery.data, isEdit]);

  if (identity?.role !== "superadmin") {
    return (
      <PageShell maxWidth="44rem">
        <PageHeader title={isEdit ? "Edit store" : "Add store"} />
        <ErrorState message="Superadmin scope required." />
      </PageShell>
    );
  }

  if (isEdit && detailQuery.isLoading) {
    return (
      <PageShell maxWidth="44rem">
        <PageHeader title="Edit store" />
        <Loading />
      </PageShell>
    );
  }
  if (isEdit && (detailQuery.isError || !detailQuery.data)) {
    const err = detailQuery.error;
    return (
      <PageShell maxWidth="44rem">
        <PageHeader title="Edit store" />
        <ErrorState
          message={`Couldn't load the store.${err instanceof Error ? ` ${err.message}` : ""}`}
          onRetry={() => { void detailQuery.refetch(); }}
        />
      </PageShell>
    );
  }

  function clearFieldError(key: string) {
    setFieldErrors((e) => {
      if (!e[key]) return e;
      const next = { ...e };
      delete next[key];
      return next;
    });
  }

  function handleApiError(err: unknown) {
    if (err instanceof ApiError) {
      // Field-level error envelope from FastAPI:
      //   { detail: { field: "slug", message: "..." } }
      const detail = (err.body as { detail?: unknown } | null)?.detail;
      if (
        detail && typeof detail === "object" &&
        "field" in detail && "message" in detail
      ) {
        const d = detail as { field: string; message: string };
        setFieldErrors({ [d.field]: d.message });
        return;
      }
      // Pydantic 422 multi-error envelope: detail is an array of
      // { loc, msg, ... }. Pull the first one out.
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { loc?: unknown[]; msg?: string };
        const loc = Array.isArray(first.loc) ? first.loc : [];
        const fieldName = loc.length > 1 ? String(loc[loc.length - 1]) : "";
        const msg = first.msg || err.message;
        if (fieldName) {
          setFieldErrors({ [fieldName]: msg });
          return;
        }
      }
      setServerError(err.message);
    } else {
      setServerError("Network error. Try again.");
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setServerError(null);
    setFieldErrors({});
    setSaved(false);
    try {
      if (isEdit && storeId !== null) {
        const body: SuperadminStoreUpdateBody = {
          name:    name.trim(),
          slug:    slug.trim(),
          email:   email.trim(),
          phone:   phone.trim(),
          address: address.trim(),
          plan,
        };
        const parsedRate = Number.parseFloat(federalTaxRate);
        if (Number.isFinite(parsedRate)) {
          body.federal_tax_rate = parsedRate;
        }
        await updateSuperadminStore(storeId, body);
        // Refresh the detail + list caches so the next paint shows
        // the canonical normalized values (lowercased slug, etc.).
        queryClient.invalidateQueries({ queryKey: ["superadmin", "store", storeId] });
        queryClient.invalidateQueries({ queryKey: ["superadmin", "stores"] });
        setSaved(true);
      } else {
        const body: SuperadminStoreCreateBody = {
          name:           name.trim(),
          slug:           slug.trim(),
          email:          email.trim(),
          phone:          phone.trim(),
          address:        address.trim(),
          plan,
          admin_username: adminUsername.trim() || "admin",
          admin_name:     adminName.trim() || "Store Admin",
          admin_password: adminPassword,
        };
        await createSuperadminStore(body);
        queryClient.invalidateQueries({ queryKey: ["superadmin", "stores"] });
        navigate("/superadmin/stores");
      }
    } catch (err) {
      handleApiError(err);
    } finally {
      setBusy(false);
    }
  }

  const heading = isEdit
    ? `Edit store${detailQuery.data?.store.name ? ` — ${detailQuery.data.store.name}` : ""}`
    : "Add new store";
  const cardTitle = isEdit
    ? "Update business account"
    : "Create a new business account";

  return (
    <PageShell maxWidth="44rem">
      <div className={styles.headerRow}>
        <PageHeader title={heading} />
        <ButtonLink to="/superadmin/stores" tone="secondary">
          ← Back to stores
        </ButtonLink>
      </div>

      <Card padding="1.5rem">
        <SectionTitle>{cardTitle}</SectionTitle>

        <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {serverError && <Alert tone="error">{serverError}</Alert>}
          {saved && <Alert tone="success">Store updated.</Alert>}
        </div>

        <form onSubmit={onSubmit} autoComplete="off">
          <div className={styles.sectionTitle}>Business info</div>

          <div className={styles.formGrid}>
            <Field label="Business name *" error={fieldErrors.name}>
              <Input
                type="text" required maxLength={120}
                value={name}
                onChange={(e) => { setName(e.target.value); clearFieldError("name"); }}
                placeholder="e.g. Austin Money Center"
                disabled={busy}
              />
            </Field>

            <Field
              label="URL slug *"
              error={fieldErrors.slug}
              hint="Lowercase, dashes for spaces. Used in store-scoped URLs."
            >
              <Input
                type="text" required maxLength={60}
                value={slug}
                onChange={(e) => { setSlug(e.target.value); clearFieldError("slug"); }}
                placeholder="e.g. austin-money-center"
                disabled={busy}
              />
            </Field>

            <Field label="Email" error={fieldErrors.email}>
              <Input
                type="email" maxLength={120}
                value={email}
                onChange={(e) => { setEmail(e.target.value); clearFieldError("email"); }}
                placeholder="owner@business.com"
                disabled={busy}
              />
            </Field>

            <Field label="Phone" error={fieldErrors.phone}>
              <Input
                type="tel" maxLength={40}
                value={phone}
                onChange={(e) => { setPhone(e.target.value); clearFieldError("phone"); }}
                placeholder="(512) 555-0000"
                disabled={busy}
              />
            </Field>

            <Field label="Address" error={fieldErrors.address} style={SPAN_2}>
              <Input
                type="text" maxLength={255}
                value={address}
                onChange={(e) => { setAddress(e.target.value); clearFieldError("address"); }}
                placeholder="Full address"
                disabled={busy}
              />
            </Field>

            <Field label="Plan" error={fieldErrors.plan}>
              <Select
                value={plan}
                onChange={(e) => { setPlan(e.target.value); clearFieldError("plan"); }}
                disabled={busy}
              >
                {PLAN_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </Select>
            </Field>

            {isEdit && (
              <Field
                label="Federal tax rate"
                error={fieldErrors.federal_tax_rate}
                hint="Decimal, 0.01 = 1%. Applied to every transfer at save time."
              >
                <Input
                  type="number" step="0.0001" min="0" max="1"
                  value={federalTaxRate}
                  onChange={(e) => {
                    setFederalTaxRate(e.target.value);
                    clearFieldError("federal_tax_rate");
                  }}
                  disabled={busy}
                />
              </Field>
            )}
          </div>

          {!isEdit && (
            <>
              <div className={styles.sectionTitle}>Admin login for this store</div>
              <div className={styles.formGrid}>
                <Field label="Admin full name" error={fieldErrors.admin_name}>
                  <Input
                    type="text" maxLength={120}
                    value={adminName}
                    onChange={(e) => {
                      setAdminName(e.target.value);
                      clearFieldError("admin_name");
                    }}
                    placeholder="Store Owner Name"
                    disabled={busy}
                  />
                </Field>

                <Field label="Admin username *" error={fieldErrors.admin_username}>
                  <Input
                    type="text" required maxLength={80}
                    value={adminUsername}
                    onChange={(e) => {
                      setAdminUsername(e.target.value);
                      clearFieldError("admin_username");
                    }}
                    disabled={busy}
                  />
                </Field>

                <Field
                  label="Admin password *"
                  error={fieldErrors.admin_password}
                  style={SPAN_2}
                >
                  <Input
                    type="password" required maxLength={200}
                    value={adminPassword}
                    onChange={(e) => {
                      setAdminPassword(e.target.value);
                      clearFieldError("admin_password");
                    }}
                    placeholder="Set a strong password"
                    autoComplete="new-password"
                    disabled={busy}
                  />
                </Field>
              </div>
            </>
          )}

          <div style={{ marginTop: "1.5rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <Button
              type="submit"
              busy={busy}
              disabled={busy || !name || !slug || (!isEdit && !adminPassword)}
            >
              {busy
                ? (isEdit ? "Saving…" : "Creating…")
                : (isEdit ? "Save changes" : "Create store")}
            </Button>
            <ButtonLink to="/superadmin/stores" tone="secondary">
              Cancel
            </ButtonLink>
          </div>
        </form>
      </Card>
    </PageShell>
  );
}
