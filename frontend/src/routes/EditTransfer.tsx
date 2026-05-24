import { useEffect } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useParams } from "react-router-dom";

import SenderAutocomplete from "../components/SenderAutocomplete";
import RecipientSuggestions from "../components/RecipientSuggestions";
import {
  Alert, Button, Card, ErrorState, Field, FormActions, Input,
  Loading, MoneyInput, PageHeader, PageShell, Section, Select,
} from "../components/ui";
import {
  previewFederalTax,
  updateTransfer,
  useEmployees,
  useTransfer,
} from "../api/transfers";
import { useStoreInfo } from "../api/account";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import styles from "./EditTransfer.module.css";

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


// ── Validation schema ──────────────────────────────────────────
//
// Mirrors NewTransfer's schema + batch_id for edit. Server-side
// is still the source of truth — Zod here is for instant client
// feedback + type narrowing.

const editSchema = z.object({
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

  send_amount: z.coerce.number().positive("Send amount must be > 0"),
  fee: z.coerce.number().min(0, "Fee must be ≥ 0"),
  confirm_number: z.string(),

  employee_id: z
    .number({ message: "Pick an employee" })
    .int()
    .positive(),

  batch_id: z.string(),
});

type EditFormValues = z.infer<typeof editSchema>;

const defaultValues: EditFormValues = {
  send_date: "",
  company: "Intermex",
  service_type: "Money Transfer",
  status: "Sent",
  sender_name: "",
  sender_phone_country: "+1",
  sender_phone: "",
  sender_address: "",
  sender_dob: "",
  customer_id: null,
  country: "Mexico",
  recipient_name: "",
  recipient_phone: "",
  send_amount: 0,
  fee: 0,
  confirm_number: "",
  employee_id: undefined as unknown as number,
  batch_id: "",
};


export default function EditTransfer() {
  const { id } = useParams<{ id: string }>();
  const transferId = id ? Number(id) : NaN;
  const navigate = useNavigate();
  const identity = getCurrentIdentity();
  const detail = useTransfer(Number.isFinite(transferId) ? transferId : undefined);
  const roster = useEmployees();
  const storeInfo = useStoreInfo();

  const {
    register, handleSubmit, control, setValue, setError, clearErrors,
    reset, formState: { errors, isSubmitting },
  } = useForm<EditFormValues>({
    resolver: zodResolver(editSchema),
    defaultValues,
    mode: "onSubmit",
  });

  // Hydrate form from the server-fetched transfer. `reset()`
  // replaces every field at once so the form doesn't flicker
  // through intermediate states.
  useEffect(() => {
    if (!detail.data) return;
    const t = detail.data.transfer;
    reset({
      send_date: t.send_date,
      company: (COMPANIES as readonly string[]).includes(t.company)
        ? (t.company as (typeof COMPANIES)[number])
        : "Other",
      service_type: (SERVICES as readonly string[]).includes(t.service_type)
        ? (t.service_type as (typeof SERVICES)[number])
        : "Money Transfer",
      status: (STATUSES as readonly string[]).includes(t.status)
        ? (t.status as (typeof STATUSES)[number])
        : "Sent",
      sender_name: "",
      sender_phone_country: "+1",
      sender_phone: "",
      sender_address: "",
      sender_dob: "",
      customer_id: null,
      country: (COUNTRIES as readonly string[]).includes(t.country)
        ? (t.country as (typeof COUNTRIES)[number])
        : "Mexico",
      recipient_name: t.recipient_name || "",
      recipient_phone: "",
      send_amount: t.send_amount,
      fee: t.fee,
      confirm_number: t.confirm_number || "",
      employee_id: undefined as unknown as number,
      batch_id: t.batch_id || "",
    });
  }, [detail.data, reset]);

  const sendAmount = useWatch({ control, name: "send_amount" });
  const serviceType = useWatch({ control, name: "service_type" });
  const country = useWatch({ control, name: "country" });
  const customerId = useWatch({ control, name: "customer_id" });

  async function onSubmit(values: EditFormValues) {
    clearErrors("root");
    try {
      const result = await updateTransfer(transferId, values);
      navigate(`/transfers/${result.transfer.id}`, { replace: true });
    } catch (err) {
      setError("root", {
        message: err instanceof ApiError
          ? err.message
          : "Could not save the changes. Please try again.",
      });
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="62rem">
        <PageHeader title="Edit transfer" />
        <p>Sign in as a store admin to edit transfers.</p>
      </PageShell>
    );
  }

  if (!Number.isFinite(transferId)) {
    return (
      <PageShell maxWidth="62rem">
        <p>Invalid transfer ID.</p>
      </PageShell>
    );
  }

  if (detail.isLoading) {
    return (
      <PageShell maxWidth="62rem">
        <Loading />
      </PageShell>
    );
  }

  if (detail.isError) {
    return (
      <PageShell maxWidth="62rem">
        <ErrorState
          message={
            detail.error instanceof Error
              ? detail.error.message
              : "Could not load this transfer."
          }
          onRetry={() => { void detail.refetch(); }}
        />
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="62rem">
      <PageHeader
        title={`Edit transfer #${transferId}`}
        subtitle="Federal tax is recomputed server-side on save."
      />

      <form
        onSubmit={handleSubmit(onSubmit)}
        style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
      >
        <Card>
          <Section title="When + how">
            <div className={styles.grid}>
              <Field label="Date" highlight={!!errors.send_date}>
                <Input type="date" {...register("send_date")} required />
              </Field>
              <Field label="Company">
                <Select {...register("company")}>
                  {COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </Field>
              <Field label="Service">
                <Select {...register("service_type")}>
                  {SERVICES.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </Field>
              <Field label="Status">
                <Select {...register("status")}>
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </Field>
            </div>
          </Section>
        </Card>

        <Card>
          <Section title="Sender">
            <div className={styles.grid}>
              <Field label="Full name" highlight={!!errors.sender_name}>
                <Controller
                  control={control}
                  name="sender_name"
                  render={({ field }) => (
                    <SenderAutocomplete
                      value={field.value}
                      onChange={field.onChange}
                      onPick={(row) => {
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
            </div>
            {customerId != null && (
              <p className={styles.note}>
                Linked to customer #{customerId} — edits sync
                back to the customer directory.
              </p>
            )}
          </Section>
        </Card>

        <Card>
          <Section title="Recipient">
            <RecipientSuggestions
              customerId={customerId ?? null}
              storeId={identity.store_id}
              onPick={(row) => {
                setValue("recipient_name", row.name);
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
            <div className={styles.grid}>
              <Field label="Country">
                <Select {...register("country")}>
                  {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </Select>
              </Field>
              <Field label="Recipient name">
                <Input type="text" {...register("recipient_name")} />
              </Field>
              <Field label="Recipient phone">
                <Input type="tel" {...register("recipient_phone")} />
              </Field>
            </div>
          </Section>
        </Card>

        <Card>
          <Section title="Amounts">
            <div className={styles.grid}>
              <Controller
                control={control}
                name="send_amount"
                render={({ field }) => (
                  <MoneyInput
                    label="Send amount"
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
                    label="Fee"
                    value={field.value ?? 0}
                    onChange={field.onChange}
                    error={errors.fee?.message}
                  />
                )}
              />
              <Field
                label={
                  (storeInfo.data?.store.federal_tax_rate ?? 0) > 0
                    ? `Federal tax preview (${((storeInfo.data!.store.federal_tax_rate) * 100).toFixed(0)}%, server recomputes)`
                    : "Federal tax preview"
                }
              >
                <Input
                  type="text"
                  readOnly
                  tabIndex={-1}
                  value={`$${previewFederalTax({
                    sendAmount,
                    serviceType,
                    country: country ?? "",
                    rate: storeInfo.data?.store.federal_tax_rate ?? 0,
                  }).toFixed(2)}`}
                  className={styles.taxPreview}
                />
              </Field>
              <Field label="Confirm #">
                <Input type="text" {...register("confirm_number")} />
              </Field>
            </div>
          </Section>
        </Card>

        <Card>
          <Section title="Processed by">
            <div className={styles.grid}>
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
                    <option key={emp.id} value={emp.id}>{emp.name}</option>
                  ))}
                </Select>
                {errors.employee_id && (
                  <span className={styles.fieldError}>
                    {errors.employee_id.message}
                  </span>
                )}
              </Field>
            </div>
            <p className={styles.note}>
              Required: who made this edit.
            </p>
          </Section>
        </Card>

        {errors.root && <Alert tone="error">{errors.root.message}</Alert>}

        <FormActions>
          <Button
            tone="secondary"
            onClick={() => navigate(`/transfers/${transferId}`)}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button type="submit" busy={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save changes"}
          </Button>
        </FormActions>
      </form>
    </PageShell>
  );
}
