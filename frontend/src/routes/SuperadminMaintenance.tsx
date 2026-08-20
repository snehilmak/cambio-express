import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Alert, Breadcrumbs, Button, Card, Field, Input,
  Loading, PageHeader, PageShell, SectionTitle, Switch, useToast,
} from "../components/ui";
import styles from "./SuperadminMaintenance.module.css";

interface MaintenanceState {
  enabled: boolean;
  message: string;
}

function useMaintenanceState() {
  const identity = getCurrentIdentity();
  return useQuery<MaintenanceState>({
    enabled: identity?.role === "superadmin",
    queryKey: ["superadmin", "maintenance"],
    queryFn: () => api<MaintenanceState>("/api/v2/superadmin/maintenance"),
  });
}

export default function SuperadminMaintenance() {
  const { data, isLoading } = useMaintenanceState();
  const qc = useQueryClient();
  const toast = useToast();
  const [enabled, setEnabled] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local toggle state from server-fetched maintenance config
      setEnabled(data.enabled);
      setMessage(data.message);
    }
  }, [data]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api("/api/v2/superadmin/maintenance", {
        method: "POST",
        json: { enabled, message: message.trim() },
      });
      qc.invalidateQueries({ queryKey: ["superadmin", "maintenance"] });
      toast({
        message: enabled
          ? "Maintenance mode ON — all users will see the banner."
          : "Maintenance mode OFF.",
        tone: enabled ? "warning" : "success",
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell maxWidth="48rem" gap="1.25rem">
      <Breadcrumbs crumbs={[
        { label: "Platform" },
        { label: "Maintenance mode" },
      ]} />

      <PageHeader
        title="Maintenance Mode"
        subtitle="Put the entire platform into maintenance with a single toggle"
      />

      {isLoading && <Loading />}

      {!isLoading && (
        <Card>
          <div className={styles.toggleCard}>
            <SectionTitle>Platform status</SectionTitle>

            <div className={styles.statusRow}>
              <div>
                <span className={enabled ? styles.dotOn : styles.dotOff} />
                <span className={styles.statusLabel}>
                  {enabled ? "Maintenance mode is ON" : "Platform is operational"}
                </span>
              </div>
              <Switch
                checked={enabled}
                onChange={setEnabled}
              >
                {enabled ? "On" : "Off"}
              </Switch>
            </div>

            <Field
              label="Maintenance message"
              hint="Shown to all logged-in users as a banner. Keep it short — e.g. 'Scheduled maintenance until 4 AM CST.'"
            >
              <Input
                type="text"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="We'll be back shortly…"
                maxLength={500}
                className={styles.messageInput}
              />
            </Field>

            {enabled && message && (
              <div className={styles.preview}>
                {message}
              </div>
            )}

            {error && <Alert tone="error">{error}</Alert>}

            <div className={styles.actions}>
              <Button onClick={() => { void save(); }} busy={busy} disabled={busy}>
                {busy ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        </Card>
      )}
    </PageShell>
  );
}
