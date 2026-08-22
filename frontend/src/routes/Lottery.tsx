import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  activateLotteryPack, createLotteryGame, receiveLotteryPack,
  recordLotteryCount, returnLotteryPack, settleLotteryPack,
  updateLotteryGame, useLotteryDay, useLotteryGames, useLotteryPacks,
  type LotteryDayRow, type LotteryGame, type LotteryPack,
} from "../api/lottery";
import { ApiError } from "../lib/api";
import { fmtMoney2 } from "../lib/formatters";
import {
  Alert, Breadcrumbs, Button, Card, DateInput, EmptyState, ErrorState,
  Field, InfoTip, Input, KpiCard, KpiGrid, Loading, Modal, PageHeader,
  PageShell, Pill, RowActions, Section, Select, TabsBar, TabsButton,
  Table, tdStyle, thStyle, useToast, type PillTone,
} from "../components/ui";
import styles from "./Lottery.module.css";

const PACK_TONES: Record<string, PillTone> = {
  received: "neutral",
  active:   "accent",
  settled:  "success",
  returned: "warning",
};

function localToday(): string {
  // en-CA formats as YYYY-MM-DD in the browser's local timezone —
  // the store counts packs at ITS closing time, not UTC's.
  return new Date().toLocaleDateString("en-CA");
}

export default function Lottery() {
  const [tab, setTab] = useState<"day" | "packs" | "games">("day");
  return (
    <PageShell maxWidth="64rem">
      <Breadcrumbs crumbs={[{ label: "Lottery" }]} />
      <PageHeader
        title={
          <>
            Lottery
            <InfoTip text="Track scratch-off games, pack activations, and day-close ticket counts. Sold tickets and dollar totals compute automatically from the count deltas." />
          </>
        }
        subtitle="Games, packs, and day-close counts."
      />
      <TabsBar>
        <TabsButton active={tab === "day"} onClick={() => setTab("day")}>
          Day close
        </TabsButton>
        <TabsButton active={tab === "packs"} onClick={() => setTab("packs")}>
          Packs
        </TabsButton>
        <TabsButton active={tab === "games"} onClick={() => setTab("games")}>
          Games
        </TabsButton>
      </TabsBar>
      {tab === "day" && <DayCloseTab />}
      {tab === "packs" && <PacksTab />}
      {tab === "games" && <GamesTab />}
    </PageShell>
  );
}

// ── Day close ────────────────────────────────────────────────

function DayCloseTab() {
  const [day, setDay] = useState(localToday());
  const summary = useLotteryDay(day);
  const qc = useQueryClient();
  const toast = useToast();

  async function saveCount(packId: number, closing: number) {
    try {
      await recordLotteryCount(day, {
        pack_id: packId, closing_ticket: closing,
      });
      void qc.invalidateQueries({ queryKey: ["lottery", "day"] });
      toast({ message: "Count saved.", tone: "success" });
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not save the count.",
        tone: "error",
      });
    }
  }

  const data = summary.data;
  return (
    <Section
      title="Day close"
      actions={
        <DateInput
          aria-label="Count date"
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
      }
    >
      {summary.isLoading && <Loading />}
      {summary.isError && (
        <ErrorState
          message="Could not load the day summary."
          onRetry={() => { void summary.refetch(); }}
        />
      )}
      {data && data.rows.length === 0 && (
        <EmptyState
          title="No active packs"
          body="Activate a pack on the Packs tab to start counting."
        />
      )}
      {data && data.rows.length > 0 && (
        <>
          <KpiGrid>
            <KpiCard label="Tickets sold" value={String(data.total_sold)} />
            <KpiCard label="Lottery total" value={fmtMoney2(data.total_value)} />
            <KpiCard
              label="Uncounted packs"
              value={String(data.uncounted_active_packs)}
              tone={data.uncounted_active_packs > 0 ? "negative" : "positive"}
            />
          </KpiGrid>
          <Card>
            <div style={{ overflowX: "auto" }}>
              <Table>
                <thead>
                  <tr>
                    {["Bin", "Game", "Pack", "Price", "Previous",
                      "Closing count", "Sold", "Value", ""].map((h) => (
                      <th key={h} style={thStyle}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => (
                    <CountRow key={r.pack_id} row={r} onSave={saveCount} />
                  ))}
                </tbody>
              </Table>
            </div>
          </Card>
        </>
      )}
    </Section>
  );
}

function CountRow({
  row, onSave,
}: {
  row: LotteryDayRow;
  onSave: (packId: number, closing: number) => Promise<void>;
}) {
  const [draft, setDraft] = useState(
    row.closing_ticket != null ? String(row.closing_ticket) : "",
  );
  const [busy, setBusy] = useState(false);
  const parsed = Number.parseInt(draft, 10);
  const valid = Number.isInteger(parsed) && parsed >= 0;
  const dirty = valid && parsed !== row.closing_ticket;
  return (
    <tr className={row.counted ? "" : styles.uncountedRow}>
      <td style={tdStyle}>{row.bin_number || "—"}</td>
      <td style={tdStyle}>#{row.game_number} {row.game_name}</td>
      <td style={tdStyle}>{row.pack_number}</td>
      <td style={tdStyle}>{fmtMoney2(row.ticket_price)}</td>
      <td style={tdStyle}>{row.previous_reference}</td>
      <td style={tdStyle}>
        <Input
          type="number" min={0} value={draft}
          aria-label={`Closing count for pack ${row.pack_number}`}
          onChange={(e) => setDraft(e.target.value)}
          className={styles.countInput}
        />
      </td>
      <td style={tdStyle}>{row.counted ? row.sold : "—"}</td>
      <td style={tdStyle}>{row.counted ? fmtMoney2(row.value) : "—"}</td>
      <td style={tdStyle}>
        <Button
          size="sm" busy={busy} disabled={!dirty || busy}
          onClick={() => {
            setBusy(true);
            void onSave(row.pack_id, parsed).finally(() => setBusy(false));
          }}
        >
          Save
        </Button>
      </td>
    </tr>
  );
}

// ── Packs ────────────────────────────────────────────────────

function PacksTab() {
  const packs = useLotteryPacks();
  const games = useLotteryGames();
  const qc = useQueryClient();
  const toast = useToast();
  const [receiving, setReceiving] = useState(false);
  const [activating, setActivating] = useState<LotteryPack | null>(null);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["lottery"] });
  }

  async function transition(
    fn: (id: number, on: string) => Promise<unknown>, pack: LotteryPack,
  ) {
    try {
      await fn(pack.id, localToday());
      refresh();
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not update the pack.",
        tone: "error",
      });
    }
  }

  return (
    <Section
      title="Packs"
      actions={
        <Button size="sm" onClick={() => setReceiving(true)}>
          + Receive pack
        </Button>
      }
    >
      {packs.isLoading && <Loading />}
      {packs.isError && (
        <ErrorState
          message="Could not load packs."
          onRetry={() => { void packs.refetch(); }}
        />
      )}
      {packs.data && packs.data.packs.length === 0 && (
        <EmptyState
          title="No packs yet"
          body='Click "+ Receive pack" when a delivery arrives.'
        />
      )}
      {packs.data && packs.data.packs.length > 0 && (
        <Card>
          <div style={{ overflowX: "auto" }}>
            <Table>
              <thead>
                <tr>
                  {["Game", "Pack", "Status", "Bin", "Opening", "Actions"]
                    .map((h) => <th key={h} style={thStyle}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {packs.data.packs.map((p) => (
                  <tr key={p.id}>
                    <td style={tdStyle}>#{p.game_number} {p.game_name}</td>
                    <td style={tdStyle}>{p.pack_number}</td>
                    <td style={tdStyle}>
                      <Pill tone={PACK_TONES[p.status] ?? "neutral"}>
                        {p.status}
                      </Pill>
                    </td>
                    <td style={tdStyle}>{p.bin_number || "—"}</td>
                    <td style={tdStyle}>{p.opening_ticket}</td>
                    <td style={tdStyle}>
                      <RowActions
                        title={`Pack ${p.pack_number}`}
                        actions={[
                          {
                            label: "Activate",
                            tone: "primary",
                            hidden: p.status !== "received",
                            onClick: () => setActivating(p),
                          },
                          {
                            label: "Settle",
                            hidden: p.status !== "active",
                            onClick: () => transition(settleLotteryPack, p),
                          },
                          {
                            label: "Return to state",
                            tone: "warning",
                            hidden: !["received", "active"].includes(p.status),
                            onClick: () => transition(returnLotteryPack, p),
                          },
                        ]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </Card>
      )}
      <ReceivePackModal
        open={receiving}
        games={games.data?.games ?? []}
        onClose={() => setReceiving(false)}
        onDone={() => { setReceiving(false); refresh(); }}
      />
      <ActivatePackModal
        pack={activating}
        onClose={() => setActivating(null)}
        onDone={() => { setActivating(null); refresh(); }}
      />
    </Section>
  );
}

function ReceivePackModal({
  open, games, onClose, onDone,
}: {
  open: boolean;
  games: LotteryGame[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [gameId, setGameId] = useState("");
  const [packNumber, setPackNumber] = useState("");
  const [on, setOn] = useState(localToday());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await receiveLotteryPack({
        game_id: Number(gameId), pack_number: packNumber.trim(),
        received_on: on,
      });
      setPackNumber("");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Receive a pack">
      <form onSubmit={onSubmit} className={styles.modalForm}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Game">
          <Select
            value={gameId} required
            onChange={(e) => setGameId(e.target.value)}
          >
            <option value="" disabled>Pick a game…</option>
            {games.map((g) => (
              <option key={g.id} value={g.id}>
                #{g.game_number} {g.name} ({fmtMoney2(g.ticket_price)})
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Pack number">
          <Input
            type="text" value={packNumber} required maxLength={40}
            onChange={(e) => setPackNumber(e.target.value)}
          />
        </Field>
        <Field label="Received on">
          <DateInput value={on} onChange={(e) => setOn(e.target.value)} />
        </Field>
        <div className={styles.modalActions}>
          <Button tone="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={busy || !gameId}>
            Receive
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function ActivatePackModal({
  pack, onClose, onDone,
}: {
  pack: LotteryPack | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [bin, setBin] = useState("");
  const [opening, setOpening] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!pack) return;
    setBusy(true);
    setError(null);
    try {
      await activateLotteryPack(pack.id, {
        activated_on: localToday(),
        opening_ticket: Number.parseInt(opening, 10) || 0,
        bin_number: bin.trim(),
      });
      setBin("");
      setOpening("0");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={pack != null}
      onClose={onClose}
      title={
        <>
          Activate pack {pack?.pack_number ?? ""}
          <InfoTip text="Puts the pack on sale. The opening ticket is the first sellable number — 0 for a fresh pack; today's counts measure against it." />
        </>
      }
    >
      <form onSubmit={onSubmit} className={styles.modalForm}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Display bin">
          <Input
            type="text" value={bin} maxLength={10} placeholder="e.g. 3"
            onChange={(e) => setBin(e.target.value)}
          />
        </Field>
        <Field label="Opening ticket #">
          <Input
            type="number" min={0} value={opening}
            onChange={(e) => setOpening(e.target.value)}
          />
        </Field>
        <div className={styles.modalActions}>
          <Button tone="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={busy}>
            Activate
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Games ────────────────────────────────────────────────────

function GamesTab() {
  const [showInactive, setShowInactive] = useState(false);
  const games = useLotteryGames(showInactive);
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["lottery"] });
  }

  async function toggleActive(g: LotteryGame) {
    try {
      await updateLotteryGame(g.id, { is_active: !g.is_active });
      refresh();
    } catch (err) {
      toast({
        message: err instanceof ApiError
          ? err.message : "Could not update the game.",
        tone: "error",
      });
    }
  }

  return (
    <Section
      title="Games"
      actions={
        <div className={styles.gamesActions}>
          <Button
            size="sm" tone="secondary"
            onClick={() => setShowInactive((v) => !v)}
          >
            {showInactive ? "Hide inactive" : "Show inactive"}
          </Button>
          <Button size="sm" onClick={() => setAdding(true)}>
            + Add game
          </Button>
        </div>
      }
    >
      {games.isLoading && <Loading />}
      {games.isError && (
        <ErrorState
          message="Could not load games."
          onRetry={() => { void games.refetch(); }}
        />
      )}
      {games.data && games.data.games.length === 0 && (
        <EmptyState
          title="No games yet"
          body='Click "+ Add game" to set up your first scratch-off game.'
        />
      )}
      {games.data && games.data.games.length > 0 && (
        <Card>
          <div style={{ overflowX: "auto" }}>
            <Table>
              <thead>
                <tr>
                  {["Game #", "Name", "Ticket price", "Tickets / pack",
                    "Status", "Actions"].map((h) => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {games.data.games.map((g) => (
                  <tr key={g.id}>
                    <td style={tdStyle}>{g.game_number}</td>
                    <td style={tdStyle}>{g.name}</td>
                    <td style={tdStyle}>{fmtMoney2(g.ticket_price)}</td>
                    <td style={tdStyle}>{g.tickets_per_pack}</td>
                    <td style={tdStyle}>
                      <Pill tone={g.is_active ? "success" : "neutral"}>
                        {g.is_active ? "active" : "inactive"}
                      </Pill>
                    </td>
                    <td style={tdStyle}>
                      <RowActions
                        title={`Game #${g.game_number}`}
                        actions={[{
                          label: g.is_active ? "Deactivate" : "Reactivate",
                          tone: g.is_active ? "warning" : "primary",
                          onClick: () => toggleActive(g),
                        }]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </Card>
      )}
      <AddGameModal
        open={adding}
        onClose={() => setAdding(false)}
        onDone={() => { setAdding(false); refresh(); }}
      />
    </Section>
  );
}

function AddGameModal({
  open, onClose, onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [gameNumber, setGameNumber] = useState("");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [perPack, setPerPack] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createLotteryGame({
        game_number: gameNumber.trim(), name: name.trim(),
        ticket_price: Number.parseFloat(price) || 0,
        tickets_per_pack: Number.parseInt(perPack, 10) || 0,
      });
      setGameNumber(""); setName(""); setPrice(""); setPerPack("");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add a game">
      <form onSubmit={onSubmit} className={styles.modalForm}>
        {error && <Alert tone="error">{error}</Alert>}
        <Field
          label={
            <>
              State game #
              <InfoTip text="The game number printed on the pack — how the state identifies the game (e.g. 2417)." />
            </>
          }
        >
          <Input
            type="text" value={gameNumber} required maxLength={20}
            onChange={(e) => setGameNumber(e.target.value)}
          />
        </Field>
        <Field label="Name">
          <Input
            type="text" value={name} required maxLength={120}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field label="Ticket price">
          <Input
            type="number" min={0} step="0.01" value={price} required
            onChange={(e) => setPrice(e.target.value)}
          />
        </Field>
        <Field label="Tickets per pack">
          <Input
            type="number" min={1} value={perPack} required
            onChange={(e) => setPerPack(e.target.value)}
          />
        </Field>
        <div className={styles.modalActions}>
          <Button tone="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" busy={busy} disabled={busy}>
            Add game
          </Button>
        </div>
      </form>
    </Modal>
  );
}
