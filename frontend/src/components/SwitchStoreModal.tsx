import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  favoriteStoreIds, returnToOwnerView, switchStore, toggleFavoriteStore,
  useMyStores,
} from "../api/switchStore";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Alert, Button, EmptyState, Input, Loading, Modal, Pill, useToast,
} from "./ui";
import styles from "./SwitchStoreModal.module.css";

// The owner's Switch Store modal (U-2 — single-dashboard
// principle, patterned on the competitor's picker): search by
// name or address, favorites (per-device), active-store radio.
// Picking a store swaps the whole session into that store's
// admin view; "Owner overview" returns to the umbrella surfaces.

export default function SwitchStoreModal({
  open, onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title="Switch store">
      {open && <SwitchStoreBody onClose={onClose} />}
    </Modal>
  );
}

function SwitchStoreBody({ onClose }: { onClose: () => void }) {
  const identity = getCurrentIdentity();
  const stores = useMyStores(true);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<"all" | "favorites">("all");
  const [favs, setFavs] = useState(favoriteStoreIds);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rows = (stores.data?.stores ?? []).filter((s) => {
    if (tab === "favorites" && !favs.has(s.store_id)) return false;
    const needle = q.trim().toLowerCase();
    if (!needle) return true;
    return s.name.toLowerCase().includes(needle)
      || s.address.toLowerCase().includes(needle);
  });
  const favCount = (stores.data?.stores ?? [])
    .filter((s) => favs.has(s.store_id)).length;

  async function enter(storeId: number) {
    setBusy(true);
    setError(null);
    try {
      const result = await switchStore(storeId);
      qc.clear();  // every cached query belonged to the old scope
      toast({ message: `Now viewing ${result.store_name}.`, tone: "success" });
      onClose();
      navigate("/dashboard");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not switch store.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function toOwnerView() {
    setBusy(true);
    setError(null);
    try {
      await returnToOwnerView();
      qc.clear();
      onClose();
      navigate("/owner/dashboard");
    } catch {
      setError("Could not return to the owner overview.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.body}>
      {error && <Alert tone="error">{error}</Alert>}
      <Input
        type="search"
        placeholder="Search stores by name or address…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className={styles.tabsRow}>
        <Button
          size="sm"
          tone={tab === "all" ? "primary" : "secondary"}
          onClick={() => setTab("all")}
        >
          All stores ({stores.data?.stores.length ?? 0})
        </Button>
        <Button
          size="sm"
          tone={tab === "favorites" ? "primary" : "secondary"}
          onClick={() => setTab("favorites")}
        >
          ★ Favorites ({favCount})
        </Button>
      </div>
      {stores.isLoading && <Loading />}
      {stores.isError && (
        <Alert tone="error">Could not load your stores.</Alert>
      )}
      {stores.data && rows.length === 0 && (
        <EmptyState
          title={tab === "favorites" ? "No favorites yet" : "No stores match"}
          body={
            tab === "favorites"
              ? "Star a store to pin it here."
              : "Try a different search."
          }
        />
      )}
      <div className={styles.list}>
        {rows.map((s) => (
          <div
            key={s.store_id}
            className={s.is_current
              ? `${styles.row} ${styles.rowCurrent}` : styles.row}
          >
            <button
              type="button"
              className={styles.rowMain}
              disabled={busy || s.is_current}
              onClick={() => { void enter(s.store_id); }}
            >
              <span className={styles.rowName}>
                {s.name}
                {s.is_current && <Pill tone="success">current</Pill>}
              </span>
              {s.address && (
                <span className={styles.rowAddress}>{s.address}</span>
              )}
            </button>
            <button
              type="button"
              className={favs.has(s.store_id)
                ? `${styles.star} ${styles.starOn}` : styles.star}
              aria-label={favs.has(s.store_id)
                ? `Unfavorite ${s.name}` : `Favorite ${s.name}`}
              onClick={() =>
                setFavs(new Set(toggleFavoriteStore(s.store_id)))
              }
            >
              ★
            </button>
            <span
              aria-hidden="true"
              className={s.is_current
                ? `${styles.radio} ${styles.radioOn}` : styles.radio}
            />
          </div>
        ))}
      </div>
      {identity?.owner_id != null && identity.role === "admin" && (
        <div className={styles.footer}>
          <Button
            tone="secondary" size="sm" disabled={busy}
            onClick={() => { void toOwnerView(); }}
          >
            ← Owner overview
          </Button>
        </div>
      )}
    </div>
  );
}
