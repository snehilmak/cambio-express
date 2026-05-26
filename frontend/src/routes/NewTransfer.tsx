import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate } from "react-router-dom";

import SenderAutocomplete from "../components/SenderAutocomplete";
import RecipientSuggestions from "../components/RecipientSuggestions";
import {
  Alert,
  Breadcrumbs,
  Button,
  Card,
  DateInput,
  Field,
  FormActions,
  Input,
  MoneyInput,
  PageHeader,
  PageShell,
  Section,
  Select,
  space,
  tokens,
} from "../components/ui";
import { getOpenStatus } from "../lib/datetime";
import {
  createTransfer,
  previewFederalTax,
  useEmployees,
} from "../api/transfers";
import { useStoreInfo } from "../api/account";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

// New transfer form at /app/transfers/new.
//
// **Canonical example** for the SPA's form stack:
//
//   1. Layout — kit primitives from ``frontend/src/components/ui``
//      (P2 #9, PR #561). Forms compose ``<PageShell>`` /
//      ``<PageHeader>`` / ``<Card>`` / ``<Section>`` / ``<Field>`` /
//      ``<Input>`` / ``<Select>`` / ``<Button>`` / ``<FormActions>``.
//   2. State + validation — ``react-hook-form`` + ``zod`` (P2 #10,
//      this PR). One ``useForm()`` per page; validation lives in
//      a Zod schema co-located with the route. Fields register via
//      ``register("field")``; complex inputs (autocomplete, …) wrap
//      in ``<Controller>``. Submit handler receives the parsed
//      payload — no manual coercion, no manual `disabled={...}`
//      guards.
//
// Other forms (BatchForm, EditTransfer, EditMonthly, Settings, …)
// migrate on-touch following this pattern.

const COMPANIES = [
  "Intermex", "Maxi", "Barri", "Sigue", "Vigo", "Western Union",
  "MoneyGram", "Cibao", "RIA", "Other",
] as const;
const SERVICES = [
  "Money Transfer", "Bill Payment", "Top Up", "Recharge",
] as const;
const COUNTRIES = [
  "United States", "Mexico", "Guatemala", "El Salvador", "Honduras",
  "Dominican Republic", "Colombia", "Ecuador", "Peru", "Other",
] as const;
const STATUSES = ["Sent", "Pending", "Cancelled", "Returned"] as const;

function todayIso() {
  const d = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// ── Validation schema ──────────────────────────────────────────
//
// Mirrors ``api/Modules/Transfers/Requests/CreateTransferRequest``.
// Server-side is still the source of truth — Zod here is for
// instant client feedback + type narrowing through the form. When
// the OpenAPI → Zod generator lands (BACKLOG P1 #6 v2), this
// hand-written schema is the first to retire.

const transferSchema = z.object({
  send_date: z.string().min(1, "Date is required"),
  company: z.enum(COMPANIES),
  service_type: z.enum(SERVICES),
  status: z.enum(STATUSES),

  sender_name: z.string().min(1, "Sender name is required"),
  sender_phone_country: z.string(),
  sender_phone: z.string(),
  sender_address: z.string(),
  sender_dob: z.string(),
  customer_id: z.number().int().positive().nullable(),

  country: z.enum(COUNTRIES),
  recipient_name: z.string(),
  recipient_phone: z.string(),

  // ``z.coerce.number()`` parses the <input type="number"> string
  // payload — no more ``Number(form.send_amount) || 0`` after the
  // resolver.
  send_amount: z.coerce.number().positive("Send amount must be > 0"),
  fee: z.coerce.number().min(0, "Fee must be ≥ 0"),
  confirm_number: z.string(),

  // Employee is required — surfaces as a field-level error if the
  // operator submits with the default ``— Select —`` option.
  employee_id: z
    .number({ message: "Pick an employee" })
    .int()
    .positive(),
});

type TransferFormValues = z.infer<typeof transferSchema>;

// ``defaultValues`` is the RHF-side counterpart to the schema —
// shapes the form's initial state. Zod doesn't see this; it only
// validates whatever lands in ``handleSubmit``.
const defaultValues = {
  send_date: todayIso(),
  company: "Intermex" as const,
  service_type: "Money Transfer" as const,
  status: "Sent" as const,
  sender_name: "",
  sender_phone_country: "+1",
  sender_phone: "",
  sender_address: "",
  sender_dob: "",
  customer_id: null as number | null,
  country: "Mexico" as const,
  recipient_name: "",
  recipient_phone: "",
  send_amount: 0,
  fee: 0,
  confirm_number: "",
  employee_id: undefined as unknown as number,  // forces validator to fire
};


export default function NewTransfer() {
  const navigate = useNavigate();
  const identity = getCurrentIdentity();
  const roster = useEmployees();
  const storeInfo = useStoreInfo();

  const {
    register, handleSubmit, control, setValue, setError, clearErrors,
    formState: { errors, isSubmitting },
  } = useForm<TransferFormValues>({
    resolver: zodResolver(transferSchema),
    defaultValues,
    mode: "onSubmit",  // surface field errors on submit, not as the user types
  });

  // ``useWatch`` (vs ``watch``) gets us a stable subscription to
  // just these fields, so the rest of the form doesn't re-render
  // on every keystroke. Used by the federal-tax preview + the
  // "linked to customer #N" notice.
  const sendAmount = useWatch({ control, name: "send_amount" });
  const serviceType = useWatch({ control, name: "service_type" });
  const country = useWatch({ control, name: "country" });
  const customerId = useWatch({ control, name: "customer_id" });

  async function onSubmit(values: TransferFormValues) {
    clearErrors("root");
    try {
      const result = await createTransfer(values);
      navigate(`/transfers/${result.transfer.id}`, { replace: true });
    } catch (err) {
      setError("root", {
        message: err instanceof ApiError
          ? err.message
          : "Could not save the transfer. Please try again.",
      });
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell>
        <PageHeader title="New transfer" />
        <p style={{ color: tokens.textMuted, textAlign: "center", padding: "1.5rem 0" }}>
          Sign in as a store admin to create transfers. Owners + the
          store-picker land in a follow-up PR.
        </p>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <Breadcrumbs crumbs={[
        { label: "Transfers", to: "/transfers" },
        { label: "New transfer" },
      ]} />
      <PageHeader
        title="New transfer"
        subtitle={
          "Federal tax preview updates as you type; the server "
          + "recomputes the final value on save."
        }
      />

      <OutOfHoursNotice
        hours={storeInfo.data?.store?.store_hours}
        storeTimezone={storeInfo.data?.store?.timezone}
      />

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="ds-form"
      >
        <Card>
          <Section title="When + how">
            <Grid>
              <Field label="Date" highlight={!!errors.send_date}>
                <Controller
                  name="send_date"
                  control={control}
                  rules={{ required: true }}
                  render={({ field }) => (
                    <DateInput
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(e.target.value)}
                      required
                    />
                  )}
                />
              </Field>
              <Field label="Company">
                <Select {...register("company")}>
                  {COMPANIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Service">
                <Select {...register("service_type")}>
                  {SERVICES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Status">
                <Select {...register("status")}>
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </Select>
              </Field>
            </Grid>
          </Section>
        </Card>

        <Card>
          <Section title="Sender">
            <Grid>
              <Field label="Full name" highlight={!!errors.sender_name}>
                <Controller
                  control={control}
                  name="sender_name"
                  render={({ field }) => (
                    <SenderAutocomplete
                      value={field.value}
                      onChange={field.onChange}
                      onPick={(row) => {
                        // Autofill the rest of the sender block + pin
                        // ``customer_id`` so the upsert reuses the row.
                        setValue("sender_name", row.full_name);
                        setValue("sender_phone_country",
                          row.phone_country || "+1");
                        setValue("sender_phone", row.phone_number);
                        setValue("sender_address", row.address);
                        setValue("sender_dob", row.dob || "");
                        setValue("customer_id", row.id);
                      }}
                      onClearPickedId={() =>
                        setValue("customer_id", null)
                      }
                      required
                    />
                  )}
                />
              </Field>
              <Field label="Phone country">
                <Input
                  type="text"
                  placeholder="+1"
                  {...register("sender_phone_country")}
                />
              </Field>
              <Field label="Phone">
                <Input type="tel" {...register("sender_phone")} />
              </Field>
              <Field label="Address">
                <Input type="text" {...register("sender_address")} />
              </Field>
            </Grid>
            {customerId != null && (
              <p style={{
                margin: "0.5rem 0 0",
                fontSize: "0.85rem",
                color: tokens.textMuted,
              }}>
                Linked to customer #{customerId} — edits sync back to
                the customer directory.
              </p>
            )}
          </Section>
        </Card>

        <Card>
          <Section title="Recipient">
            {/* Chip row of recent recipients for the picked sender.
                Hidden when no sender is picked or the sender has no
                history; otherwise one tap fills name / country /
                phone in one go. */}
            <RecipientSuggestions
              customerId={customerId}
              storeId={identity.store_id}
              onPick={(row) => {
                setValue("recipient_name", row.name);
                // Only apply the country if it's in the dropdown's
                // canonical list — past transfers may have free-text
                // values that no longer match the curated options.
                if (
                  row.country
                  && (COUNTRIES as readonly string[]).includes(row.country)
                ) {
                  setValue(
                    "country",
                    row.country as (typeof COUNTRIES)[number],
                  );
                }
                setValue("recipient_phone", row.phone);
              }}
            />
            <Grid>
              <Field label="Country">
                <Select {...register("country")}>
                  {COUNTRIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Recipient name">
                <Input type="text" {...register("recipient_name")} />
              </Field>
              <Field label="Recipient phone">
                <Input type="tel" {...register("recipient_phone")} />
              </Field>
            </Grid>
          </Section>
        </Card>

        <Card>
          <Section title="Amounts">
            <Grid>
              <Controller
                control={control}
                name="send_amount"
                render={({ field }) => (
                  <MoneyInput
                    label="Send amount (USD)"
                    value={field.value ?? 0}
                    onChange={field.onChange}
                    error={errors.send_amount?.message}
                  />
                )}
              />
              <Controller
                control={control}
                name="fee"
                render={({ field }) => (
                  <MoneyInput
                    label="Fee (USD)"
                    value={field.value ?? 0}
                    onChange={field.onChange}
                    error={errors.fee?.message}
                  />
                )}
              />
              <FederalTaxPreview
                sendAmount={sendAmount}
                serviceType={serviceType}
                country={country ?? ""}
                rate={storeInfo.data?.store.federal_tax_rate ?? 0}
              />
              <Field label="Confirm #">
                <Input type="text" {...register("confirm_number")} />
              </Field>
            </Grid>
          </Section>
        </Card>

        <Card>
          <Section title="Processed by">
            <Grid>
              <Field label="Employee" highlight={!!errors.employee_id}>
                <Select
                  {...register("employee_id", {
                    setValueAs: (v) => v === "" ? null : Number(v),
                  })}
                  required
                  disabled={roster.isLoading}
                >
                  <option value="">— Select —</option>
                  {roster.data?.employees.map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.name}
                    </option>
                  ))}
                </Select>
                {errors.employee_id && (
                  <FieldError>{errors.employee_id.message}</FieldError>
                )}
              </Field>
            </Grid>
            {roster.isError && (
              <p style={{
                margin: "0.5rem 0 0",
                fontSize: "0.85rem",
                color: tokens.negative,
              }}>
                Couldn't load roster. Add cashiers via Settings → Team
                on the legacy admin page.
              </p>
            )}
            {!roster.isLoading &&
              !roster.isError &&
              roster.data &&
              roster.data.employees.length === 0 && (
                <p style={{
                  margin: "0.5rem 0 0",
                  fontSize: "0.85rem",
                  color: tokens.textMuted,
                }}>
                  No active employees on this store's roster yet. Add
                  them via Settings → Team on the legacy admin page.
                </p>
              )}
          </Section>
        </Card>

        {errors.root && (
          <p role="alert" style={{
            color: tokens.negative,
            textAlign: "center",
            padding: "0.5rem 0",
          }}>
            {errors.root.message}
          </p>
        )}

        <FormActions>
          <Button
            tone="secondary"
            onClick={() => navigate("/transfers")}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button type="submit" busy={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save transfer"}
          </Button>
        </FormActions>
      </form>
    </PageShell>
  );
}


// ── Local helpers ──────────────────────────────────────────────


function Grid({ children }: { children: React.ReactNode }) {
  // Auto-fit grid for form rows — repeated several times above
  // so it pays its keep as a local helper, not yet generic enough
  // for the kit.
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(13rem, 1fr))",
      gap: "0.75rem",
    }}>
      {children}
    </div>
  );
}


function FieldError({ children }: { children: React.ReactNode }) {
  // Field-scoped validation message. Slot under a ``<Field>``
  // input to surface the Zod issue inline.
  return (
    <span style={{
      display: "block",
      marginTop: "0.3rem",
      fontSize: "0.78rem",
      color: tokens.negative,
    }}>
      {children}
    </span>
  );
}


// Read-only client-side preview of the federal tax the server is
// about to compute. Mirrors the rule in
// `api/Modules/Transfers/Services/tax.py` so the cashier can
// sanity-check the number before submit; the actual value still
// comes from the server (CLAUDE.md invariant #9).
function FederalTaxPreview({
  sendAmount, serviceType, country, rate,
}: {
  sendAmount: number | string;
  serviceType: string;
  country: string;
  rate: number;
}) {
  const tax = previewFederalTax({
    sendAmount, serviceType, country, rate,
  });
  const exempt = tax === 0 && (Number(sendAmount) || 0) > 0;
  const pct = (rate * 100).toFixed(rate < 0.01 ? 2 : 0);
  return (
    <Field
      label={
        rate > 0
          ? `Federal tax preview (${pct}%, server recomputes)`
          : "Federal tax preview"
      }
    >
      <Input
        type="text"
        readOnly
        tabIndex={-1}
        value={`$${tax.toFixed(2)}`}
        style={{
          background: tokens.surface2,
          color: tokens.textMuted,
          cursor: "default",
          fontFamily: tokens.fontMono,
        }}
      />
      {exempt && (
        <span style={{
          display: "block",
          marginTop: space.xs,
          fontSize: "0.75rem",
          color: tokens.textMuted,
        }}>
          Exempt — {country === "United States"
            ? "domestic recipient"
            : `${serviceType} service`}
        </span>
      )}
    </Field>
  );
}


// Soft warning above the New Transfer form when the operator is
// logging outside the store's configured business hours. Not a
// gate — the save endpoint still accepts the entry. Hidden when
// store_hours is missing (no opinion to express) or when we're
// currently inside the open window.
function OutOfHoursNotice({
  hours, storeTimezone,
}: {
  hours: NonNullable<ReturnType<typeof useStoreInfo>["data"]>["store"]["store_hours"] | undefined;
  storeTimezone: string | undefined;
}) {
  const status = getOpenStatus(hours, storeTimezone);
  if (!status || status.open) return null;
  return (
    <Alert tone="warning">
      Heads up — you're logging this outside the store's usual
      business hours
      ({status.todayLabel
        ? `${status.dayLabel}: ${status.todayLabel}`
        : `closed all day ${status.dayLabel}`}).
      The transfer will still save normally.
    </Alert>
  );
}
