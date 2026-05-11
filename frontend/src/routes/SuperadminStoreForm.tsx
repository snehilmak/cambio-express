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
      <main style={pageStyle}>
        <h1 style={titleStyle}>{isEdit ? "Edit store" : "Add store"}</h1>
        <p style={errorStyle}>Superadmin scope required.</p>
      </main>
    );
  }

  if (isEdit && detailQuery.isLoading) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Edit store</h1>
        <p style={mutedStyle}>Loading…</p>
      </main>
    );
  }
  if (isEdit && (detailQuery.isError || !detailQuery.data)) {
    const err = detailQuery.error;
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Edit store</h1>
        <p style={errorStyle}>
          Couldn&rsquo;t load the store.
          {err instanceof Error ? ` ${err.message}` : ""}
        </p>
      </main>
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
    <main style={pageStyle}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: "1.25rem",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <h1 style={titleStyle}>{heading}</h1>
        <a href="/app/superadmin/stores" style={btnOutlineStyle}>
          ← Back to stores
        </a>
      </header>

      <section style={cardStyle}>
        <h2 style={cardTitleStyle}>{cardTitle}</h2>

        {serverError && <div style={alertErrorStyle}>{serverError}</div>}
        {saved && <div style={alertOkStyle} role="status">Store updated.</div>}

        <form onSubmit={onSubmit} autoComplete="off">
          <div style={sectionTitleStyle}>Business info</div>

          <div style={formGridStyle}>
            <Field label="Business name *" error={fieldErrors.name}>
              <input
                type="text" required maxLength={120}
                value={name}
                onChange={(e) => { setName(e.target.value); clearFieldError("name"); }}
                placeholder="e.g. Austin Money Center"
                disabled={busy} style={inputStyle}
              />
            </Field>

            <Field label="URL slug *" error={fieldErrors.slug}
                   hint="Lowercase, dashes for spaces. Used in store-scoped URLs.">
              <input
                type="text" required maxLength={60}
                value={slug}
                onChange={(e) => { setSlug(e.target.value); clearFieldError("slug"); }}
                placeholder="e.g. austin-money-center"
                disabled={busy} style={inputStyle}
              />
            </Field>

            <Field label="Email" error={fieldErrors.email}>
              <input
                type="email" maxLength={120}
                value={email}
                onChange={(e) => { setEmail(e.target.value); clearFieldError("email"); }}
                placeholder="owner@business.com"
                disabled={busy} style={inputStyle}
              />
            </Field>

            <Field label="Phone" error={fieldErrors.phone}>
              <input
                type="tel" maxLength={40}
                value={phone}
                onChange={(e) => { setPhone(e.target.value); clearFieldError("phone"); }}
                placeholder="(512) 555-0000"
                disabled={busy} style={inputStyle}
              />
            </Field>

            <Field label="Address" error={fieldErrors.address}
                   span={2}>
              <input
                type="text" maxLength={255}
                value={address}
                onChange={(e) => { setAddress(e.target.value); clearFieldError("address"); }}
                placeholder="Full address"
                disabled={busy} style={inputStyle}
              />
            </Field>

            <Field label="Plan" error={fieldErrors.plan}>
              <select
                value={plan}
                onChange={(e) => { setPlan(e.target.value); clearFieldError("plan"); }}
                disabled={busy} style={inputStyle}
              >
                {PLAN_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </Field>

            {isEdit && (
              <Field label="Federal tax rate"
                     error={fieldErrors.federal_tax_rate}
                     hint="Decimal, 0.01 = 1%. Applied to every transfer at save time.">
                <input
                  type="number" step="0.0001" min="0" max="1"
                  value={federalTaxRate}
                  onChange={(e) => {
                    setFederalTaxRate(e.target.value);
                    clearFieldError("federal_tax_rate");
                  }}
                  disabled={busy} style={inputStyle}
                />
              </Field>
            )}
          </div>

          {!isEdit && (
            <>
              <div style={sectionTitleStyle}>Admin login for this store</div>
              <div style={formGridStyle}>
                <Field label="Admin full name"
                       error={fieldErrors.admin_name}>
                  <input
                    type="text" maxLength={120}
                    value={adminName}
                    onChange={(e) => {
                      setAdminName(e.target.value);
                      clearFieldError("admin_name");
                    }}
                    placeholder="Store Owner Name"
                    disabled={busy} style={inputStyle}
                  />
                </Field>

                <Field label="Admin username *"
                       error={fieldErrors.admin_username}>
                  <input
                    type="text" required maxLength={80}
                    value={adminUsername}
                    onChange={(e) => {
                      setAdminUsername(e.target.value);
                      clearFieldError("admin_username");
                    }}
                    disabled={busy} style={inputStyle}
                  />
                </Field>

                <Field label="Admin password *"
                       error={fieldErrors.admin_password}
                       span={2}>
                  <input
                    type="password" required maxLength={200}
                    value={adminPassword}
                    onChange={(e) => {
                      setAdminPassword(e.target.value);
                      clearFieldError("admin_password");
                    }}
                    placeholder="Set a strong password"
                    autoComplete="new-password"
                    disabled={busy} style={inputStyle}
                  />
                </Field>
              </div>
            </>
          )}

          <div style={{ marginTop: "1.5rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <button
              type="submit"
              disabled={busy || !name || !slug || (!isEdit && !adminPassword)}
              style={btnPrimaryStyle}
            >
              {busy
                ? (isEdit ? "Saving…" : "Creating…")
                : (isEdit ? "Save changes" : "Create store")}
            </button>
            <a href="/app/superadmin/stores" style={btnOutlineStyle}>
              Cancel
            </a>
          </div>
        </form>
      </section>
    </main>
  );
}


function Field({
  label, error, hint, span, children,
}: {
  label:    string;
  error?:   string;
  hint?:    string;
  span?:    number;
  children: React.ReactNode;
}) {
  return (
    <label
      style={{
        ...fieldStyle,
        ...(span === 2 ? { gridColumn: "1 / -1" } : {}),
      }}
    >
      <span style={labelStyle}>{label}</span>
      {children}
      {error && <span style={fieldErrorStyle}>{error}</span>}
      {hint && !error && <span style={hintStyle}>{hint}</span>}
    </label>
  );
}


const pageStyle: React.CSSProperties = {
  flex: 1, display: "flex", flexDirection: "column",
  padding: "2rem 1.5rem", maxWidth: "44rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600, margin: 0,
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem", padding: "1.5rem",
};

const cardTitleStyle: React.CSSProperties = {
  margin: "0 0 1rem", fontSize: "1.05rem", fontWeight: 600,
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  fontWeight: 600,
  color: "var(--db-text-muted, #a3a3a3)",
  margin: "1.5rem 0 0.75rem",
};

const formGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))",
  gap: "0.75rem 1rem",
};

const fieldStyle: React.CSSProperties = {
  display: "flex", flexDirection: "column",
  gap: "0.35rem",
};

const labelStyle: React.CSSProperties = {
  fontSize: "0.7rem", letterSpacing: "0.06em",
  textTransform: "uppercase", fontWeight: 600,
  color: "var(--db-text-muted, #a3a3a3)",
};

const inputStyle: React.CSSProperties = {
  padding: "0.6rem 0.75rem",
  background: "var(--db-bg-input, #0d0d0d)",
  color: "var(--db-text, #e5e5e5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem", fontSize: "0.95rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
};

const hintStyle: React.CSSProperties = {
  fontSize: "0.78rem", color: "var(--db-text-muted, #a3a3a3)",
};

const fieldErrorStyle: React.CSSProperties = {
  fontSize: "0.8rem", color: "var(--db-negative, #ff4d6d)",
};

const btnPrimaryStyle: React.CSSProperties = {
  padding: "0.65rem 1.1rem",
  fontWeight: 600, fontSize: "0.92rem",
  background: "var(--db-neon, #3fff00)",
  color: "var(--db-neon-ink, #001a0f)",
  border: "none", borderRadius: "0.5rem",
  cursor: "pointer",
};

const btnOutlineStyle: React.CSSProperties = {
  padding: "0.65rem 1.1rem",
  fontWeight: 500, fontSize: "0.92rem",
  background: "transparent",
  color: "var(--db-text, #e5e5e5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  textDecoration: "none",
  display: "inline-block",
  cursor: "pointer",
};

const alertErrorStyle: React.CSSProperties = {
  padding: "0.6rem 0.85rem",
  marginBottom: "1rem",
  background: "rgba(255,77,109,0.08)",
  border: "1px solid rgba(255,77,109,0.3)",
  borderRadius: "0.5rem",
  color: "var(--db-negative, #ff4d6d)",
  fontSize: "0.88rem",
};

const alertOkStyle: React.CSSProperties = {
  padding: "0.6rem 0.85rem",
  marginBottom: "1rem",
  background: "rgba(63,255,0,0.08)",
  border: "1px solid rgba(63,255,0,0.3)",
  borderRadius: "0.5rem",
  color: "var(--db-neon, #3fff00)",
  fontSize: "0.88rem",
};

const mutedStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-text-muted, #a3a3a3)",
};

const errorStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-negative, #ff4d6d)",
};
