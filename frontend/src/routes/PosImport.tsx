import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useDepartments } from "../api/dayclose";
import {
  commitNaxml, commitStagedDay, fileToBase64, issueAgentKey,
  previewNaxml, revokeAgentKey, saveMappings, useAgentKeys,
  useStagedDays,
  type ImportRegisterRow, type NaxmlPreview,
} from "../api/posimport";
import { ApiError } from "../lib/api";
import { fmtMoney2 } from "../lib/formatters";
import { formatDate } from "../lib/datetime";
import {
  Alert, Breadcrumbs, Button, Card, EmptyState, Field, InfoTip,
  Input, KpiCard, KpiGrid, PageHeader, PageShell, Pill, Section,
  Select, Table, tdStyle, thStyle, useToast,
} from "../components/ui";
import styles from "./PosImport.module.css";

/**
 * Gilbarco register import (P1-9): upload a day's (or a whole
 * folder's zip of) NAXML journal files, review the per-register
 * aggregates, map the register's numeric department codes onto
 * this store's own departments, and book one business day into
 * Day close. Until the site agent ships, the operator grabs the
 * files from the register's back-office share.
 */
export default function PosImport() {
  const qc = useQueryClient();
  const toast = useToast();
  const departments = useDepartments();
  const fileRef = useRef<HTMLInputElement>(null);

  const [fileName, setFileName] = useState("");
  const [payload, setPayload] = useState("");   // base64, reused for commit
  const [preview, setPreview] = useState<NaxmlPreview | null>(null);
  const [selectedDay, setSelectedDay] = useState("");
  const [draftMap, setDraftMap] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<"" | "preview" | "map" | "commit">("");
  const [error, setError] = useState<string | null>(null);
  const [committed, setCommitted] = useState<string | null>(null);

  async function runPreview(b64: string) {
    setBusy("preview");
    setError(null);
    try {
      const data = await previewNaxml(b64);
      setPreview(data);
      setSelectedDay((prev) =>
        data.business_dates.includes(prev)
          ? prev
          : data.business_dates[data.business_dates.length - 1] ?? "",
      );
      setDraftMap({});
    } catch (err) {
      setPreview(null);
      setError(err instanceof ApiError ? err.message : "Could not parse the upload.");
    } finally {
      setBusy("");
    }
  }

  async function onPickFile(file: File | undefined) {
    if (!file) return;
    setFileName(file.name);
    setCommitted(null);
    const b64 = await fileToBase64(file);
    setPayload(b64);
    await runPreview(b64);
  }

  async function onSaveMappings() {
    const rows = Object.entries(draftMap)
      .filter(([, deptId]) => deptId !== "")
      .map(([code, deptId]) => ({
        merchandise_code: code, department_id: Number(deptId),
      }));
    if (rows.length === 0) return;
    setBusy("map");
    setError(null);
    try {
      await saveMappings(rows);
      toast({ message: "Mappings saved.", tone: "success" });
      await runPreview(payload);   // refresh mapped/unmapped state
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save mappings.");
    } finally {
      setBusy("");
    }
  }

  async function onCommit() {
    if (!selectedDay) return;
    setBusy("commit");
    setError(null);
    try {
      const result = await commitNaxml(payload, selectedDay);
      setCommitted(
        `${result.day}: ${result.closes_written} register close(s) booked `
        + `(${result.registers.join(", ")}).`,
      );
      void qc.invalidateQueries({ queryKey: ["dayclose"] });
      toast({ message: "Day imported into Day close.", tone: "success" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not import the day.");
    } finally {
      setBusy("");
    }
  }

  const dayRegisters: ImportRegisterRow[] = useMemo(
    () => (preview?.registers ?? []).filter(
      (r) => r.business_date === selectedDay,
    ),
    [preview, selectedDay],
  );
  const dayTotals = useMemo(() => {
    let net = 0, tax = 0, fuelGallons = 0;
    for (const r of dayRegisters) {
      net += r.net_sales;
      tax += r.sales_tax;
      for (const f of r.fuel) fuelGallons += f.gallons;
    }
    return { net, tax, fuelGallons };
  }, [dayRegisters]);

  const unmapped = preview?.unmapped_codes ?? [];

  return (
    <PageShell maxWidth="64rem">
      <Breadcrumbs crumbs={[
        { label: "Day close", to: "/day-close" },
        { label: "Register import" },
      ]} />
      <PageHeader
        title={
          <>
            Register import
            <InfoTip text="Upload the XML journal files your Gilbarco register writes to its back-office folder — one file or a ZIP of many. Review the totals, map the register's department codes to your departments once, then book the day into Day close." />
          </>
        }
        subtitle="Import a Gilbarco day close from the register's journal files."
      />

      <Section title="1 · Upload">
        <div className={styles.uploadRow}>
          <input
            ref={fileRef}
            type="file"
            accept=".xml,.zip"
            hidden
            onChange={(e) => { void onPickFile(e.target.files?.[0]); }}
          />
          <Button
            busy={busy === "preview"} disabled={busy !== ""}
            onClick={() => fileRef.current?.click()}
          >
            Choose file…
          </Button>
          {fileName && <span className={styles.fileName}>{fileName}</span>}
          {preview && (
            <Pill tone="neutral">
              {preview.event_count} transactions
              in {preview.file_count} file(s)
            </Pill>
          )}
        </div>
        {error && <Alert tone="error">{error}</Alert>}
        {preview && preview.parse_errors.length > 0 && (
          <Alert tone="warning">
            {preview.parse_errors.length} file(s) could not be parsed and
            were skipped.
            <div className={styles.parseErrors}>
              {preview.parse_errors.map((e) => <div key={e}>{e}</div>)}
            </div>
          </Alert>
        )}
      </Section>

      {preview && (
        <Section
          title="2 · Map departments"
          actions={
            unmapped.length > 0 ? (
              <Button
                size="sm" busy={busy === "map"}
                disabled={busy !== "" || Object.values(draftMap)
                  .filter(Boolean).length === 0}
                onClick={() => { void onSaveMappings(); }}
              >
                Save mappings
              </Button>
            ) : undefined
          }
        >
          {unmapped.length === 0 ? (
            <Alert tone="success">
              Every department code in this upload is mapped.
            </Alert>
          ) : (
            <Card>
              <div className={styles.mapList}>
                {unmapped.map((code) => (
                  <div key={code} className={styles.mapRow}>
                    <span className={styles.mapCode}>
                      Code {code}
                      {code === "1024" ? " (fuel)" : ""}
                    </span>
                    <Select
                      className={styles.mapSelect}
                      aria-label={`Department for code ${code}`}
                      value={draftMap[code] ?? ""}
                      onChange={(e) =>
                        setDraftMap((prev) => ({
                          ...prev, [code]: e.target.value,
                        }))
                      }
                    >
                      <option value="">Pick a department…</option>
                      {(departments.data?.departments ?? []).map((d) => (
                        <option key={d.id} value={d.id}>{d.name}</option>
                      ))}
                    </Select>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {unmapped.length > 0
            && (departments.data?.departments ?? []).length === 0 && (
            <EmptyState
              title="No departments yet"
              body={
                <>
                  Set up your departments first on the{" "}
                  <Link to="/day-close">Day close page</Link> — the
                  starter set takes one click.
                </>
              }
            />
          )}
        </Section>
      )}

      {preview && (
        <Section
          title="3 · Review & import"
          actions={
            <div className={styles.commitRow}>
              <Field label="Business day">
                <Select
                  value={selectedDay}
                  onChange={(e) => setSelectedDay(e.target.value)}
                >
                  {preview.business_dates.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </Select>
              </Field>
              <Button
                busy={busy === "commit"}
                disabled={busy !== "" || !selectedDay || unmapped.length > 0}
                onClick={() => { void onCommit(); }}
              >
                Import this day
              </Button>
            </div>
          }
        >
          {committed && (
            <Alert tone="success">
              {committed} <Link to="/day-close">Open Day close</Link>
            </Alert>
          )}
          {unmapped.length > 0 && (
            <Alert tone="warning">
              Map every department code above before importing.
            </Alert>
          )}
          {dayRegisters.length > 0 && (
            <>
              <KpiGrid>
                <KpiCard label="Net sales" value={fmtMoney2(dayTotals.net)} />
                <KpiCard label="Sales tax" value={fmtMoney2(dayTotals.tax)} />
                <KpiCard
                  label="Fuel gallons"
                  value={dayTotals.fuelGallons.toLocaleString(undefined, {
                    maximumFractionDigits: 1,
                  })}
                />
                <KpiCard
                  label="Registers"
                  value={String(dayRegisters.length)}
                />
              </KpiGrid>
              <Card>
                <div style={{ overflowX: "auto" }}>
                  <Table>
                    <thead>
                      <tr>
                        {["Register", "Net sales", "Tax", "Cash", "Card",
                          "Other", "Sales", "Refunds"].map((h) => (
                          <th key={h} style={thStyle}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {dayRegisters.map((r) => (
                        <tr key={r.register_label}>
                          <td style={tdStyle}>{r.register_label}</td>
                          <td style={tdStyle}>{fmtMoney2(r.net_sales)}</td>
                          <td style={tdStyle}>{fmtMoney2(r.sales_tax)}</td>
                          <td style={tdStyle}>{fmtMoney2(r.cash_total)}</td>
                          <td style={tdStyle}>{fmtMoney2(r.card_total)}</td>
                          <td style={tdStyle}>{fmtMoney2(r.other_total)}</td>
                          <td style={tdStyle}>{r.sale_count}</td>
                          <td style={tdStyle}>{r.refund_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
              </Card>
            </>
          )}
        </Section>
      )}

      <AgentSection />
    </PageShell>
  );
}

// ── Site agent (automatic uploads) ───────────────────────────

function AgentSection() {
  const qc = useQueryClient();
  const toast = useToast();
  const staged = useStagedDays();
  const keys = useAgentKeys();
  const [newLabel, setNewLabel] = useState("");
  const [freshKey, setFreshKey] = useState<string | null>(null);
  const [busyDay, setBusyDay] = useState("");
  const [keyBusy, setKeyBusy] = useState(false);

  async function bookDay(day: string) {
    setBusyDay(day);
    try {
      const result = await commitStagedDay(day);
      toast({
        message: `${result.day} booked — ${result.closes_written} register close(s).`,
        tone: "success",
      });
      void qc.invalidateQueries({ queryKey: ["dayclose"] });
      void qc.invalidateQueries({ queryKey: ["posimport", "staged"] });
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not book the day.",
        tone: "error",
      });
    } finally {
      setBusyDay("");
    }
  }

  async function onIssueKey() {
    setKeyBusy(true);
    try {
      const issued = await issueAgentKey(newLabel.trim());
      setFreshKey(issued.key);
      setNewLabel("");
      void qc.invalidateQueries({ queryKey: ["posimport", "agent-keys"] });
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not create the key.",
        tone: "error",
      });
    } finally {
      setKeyBusy(false);
    }
  }

  async function onRevoke(id: number) {
    try {
      await revokeAgentKey(id);
      void qc.invalidateQueries({ queryKey: ["posimport", "agent-keys"] });
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not revoke the key.",
        tone: "error",
      });
    }
  }

  const stagedRows = staged.data?.days ?? [];
  const keyRows = keys.data?.keys ?? [];

  return (
    <Section
      title={
        <>
          Automatic uploads
          <InfoTip text="Install the DineroBook site agent on the store's back-office PC and it pushes every journal file here the moment the register writes it. Issue an agent key below — it's shown exactly once. Once your merchandise codes are mapped, each business day books itself automatically as soon as the register's day rolls; days with unmapped codes (or older backlog) wait here for you to book manually." />
        </>
      }
    >
      {stagedRows.length > 0 && (
        <Card>
          <div style={{ overflowX: "auto" }}>
            <Table>
              <thead>
                <tr>
                  {["Business day", "Files", "Errors", "Status", ""].map(
                    (h) => <th key={h} style={thStyle}>{h}</th>,
                  )}
                </tr>
              </thead>
              <tbody>
                {stagedRows.map((d) => (
                  <tr key={d.business_date}>
                    <td style={tdStyle}>{d.business_date}</td>
                    <td style={tdStyle}>{d.file_count}</td>
                    <td style={tdStyle}>{d.error_count || "—"}</td>
                    <td style={tdStyle}>
                      <Pill tone={d.committed ? "success" : "neutral"}>
                        {d.committed ? "booked" : "ready"}
                      </Pill>
                    </td>
                    <td style={tdStyle}>
                      <Button
                        size="sm"
                        busy={busyDay === d.business_date}
                        disabled={busyDay !== ""}
                        tone={d.committed ? "secondary" : "primary"}
                        onClick={() => { void bookDay(d.business_date); }}
                      >
                        {d.committed ? "Re-book" : "Book day"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </Card>
      )}
      {staged.data && stagedRows.length === 0 && (
        <EmptyState
          title="No agent uploads yet"
          body="Once the site agent is running, days appear here as the register writes its journal."
        />
      )}

      {freshKey && (
        <Alert tone="success">
          Agent key created — copy it now, it will not be shown again:
          {" "}<code className={styles.mapCode}>{freshKey}</code>
        </Alert>
      )}
      <Card>
        <div className={styles.uploadRow}>
          <Input
            type="text" value={newLabel} maxLength={80}
            placeholder="Key label (e.g. Back office PC)"
            onChange={(e) => setNewLabel(e.target.value)}
          />
          <Button
            size="sm" busy={keyBusy} disabled={keyBusy}
            onClick={() => { void onIssueKey(); }}
          >
            New agent key
          </Button>
        </div>
        {keyRows.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <Table>
              <thead>
                <tr>
                  {["Label", "Created", "Last seen", "Status", ""].map(
                    (h) => <th key={h} style={thStyle}>{h}</th>,
                  )}
                </tr>
              </thead>
              <tbody>
                {keyRows.map((k) => (
                  <tr key={k.id}>
                    <td style={tdStyle}>{k.label || "—"}</td>
                    <td style={tdStyle}>{formatDate(k.created_at)}</td>
                    <td style={tdStyle}>
                      {k.last_used_at
                        ? k.last_used_at.slice(0, 16).replace("T", " ")
                        : "never"}
                    </td>
                    <td style={tdStyle}>
                      <Pill tone={k.revoked ? "neutral" : "accent"}>
                        {k.revoked ? "Revoked" : "Active"}
                      </Pill>
                    </td>
                    <td style={tdStyle}>
                      {!k.revoked && (
                        <Button
                          size="sm" tone="secondary"
                          onClick={() => { void onRevoke(k.id); }}
                        >
                          Revoke
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        )}
      </Card>
    </Section>
  );
}
