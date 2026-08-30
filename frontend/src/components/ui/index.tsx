// Shared design-system primitives. Barrel re-export.
//
// Why these exist
// ---------------
// Every route file was redeclaring `cardStyle`, `inputStyle`,
// `pageStyle`, `pagerBtn`, etc. — about 200 lines of token
// boilerplate per route. That made changes to the design system
// (e.g. tweaking the card border radius or pill colors) require
// touching every file. These primitives consolidate the patterns
// so each route file is mostly app logic, not styling.
//
// Add new primitives in a new ``./X.tsx`` and re-export from here.
//
// Layout                  Form                Tables/data
//   <PageShell>             <Field>             <Table>
//   <PageHeader>            <Input>             <TableSkeleton>
//   <Card>                  <Select>            <KpiCard> / <KpiGrid>
//   <Section>               <Textarea>          <Pager>
//   <SectionTitle>          <FormActions>
//                                              Feedback
// Inline + states                                <Empty>
//   <Button>                                     <EmptyState>
//   <ButtonLink>                                 <ErrorState>
//   <Pill>                                       <Loading>
//   <Alert>
//
// Motion: classNames in ui.css. Honors prefers-reduced-motion via
// the global rule at the bottom of static/content.css.
//
// Tokens (colors / spacing / type / monoStyle / inputStyle / th/tdStyle)
// live in `./tokens.ts` — kept separate so Vite fast-refresh isn't
// blocked by non-component exports. Re-exported below for callers
// that grab everything from `components/ui` directly.

import "./ui.css";

// Re-export non-component values from `./tokens` so consumers have
// a single `components/ui` import path. Fast-refresh complains
// because non-component exports on a barrel that also re-exports
// components would prevent HMR for THIS file — but the actual
// values live in `./tokens.ts` (a non-component file that HMR
// handles fine), so the only practical downside is that this
// barrel module won't hot-reload its own re-exports. Acceptable
// trade-off for the simpler import surface.
/* eslint-disable react-refresh/only-export-components -- public DS surface: re-export tokens from this barrel so consumers don't learn two import paths */
export {
  fontSize, inputStyle, monoStyle, space, tdStyle, tdStyleRight,
  thStyle, thStyleRight, tokens,
} from "./tokens";
/* eslint-enable react-refresh/only-export-components */

export { PageShell } from "./PageShell";
export { PageHeader } from "./PageHeader";
export { Breadcrumbs } from "./Breadcrumbs";
export { Card } from "./Card";
export { Section, SectionTitle } from "./Section";
export { Field } from "./Field";
export { Input } from "./Input";
export { DateInput } from "./DateInput";
export { MoneyInput } from "./MoneyInput";
export { PhoneField, type PhoneFieldProps } from "./PhoneField";
export { Select } from "./Select";
export { Textarea } from "./Textarea";
export { KpiCard, KpiGrid, type KpiTone } from "./KpiCard";
export { Table, TableSkeleton } from "./Table";
export { TableStates } from "./TableStates";
export { Empty, EmptyState } from "./Empty";
export { ErrorState } from "./ErrorState";
export { Loading } from "./Loading";
export { Pager } from "./Pager";
export { Pill, type PillTone } from "./Pill";
export { Alert, type AlertTone } from "./Alert";
export { Button, ButtonLink, type ButtonTone } from "./Button";
export { Modal, ConfirmDialog } from "./Modal";
export {
  IconButton,
  type IconButtonSize,
  type IconButtonTone,
} from "./IconButton";
export {
  RowActions,
  type RowActionItem,
  type RowActionTone,
} from "./RowActions";
export { FormActions } from "./FormActions";
export { TabsBar, TabsLink, TabsButton } from "./Tabs";
export { Checkbox } from "./Checkbox";
export { Switch } from "./Switch";
export { Tooltip } from "./Tooltip";
export { InfoTip } from "./InfoTip";
/* eslint-disable react-refresh/only-export-components -- public DS surface: re-export `useToast` from this barrel so consumers don't learn two import paths.  Same trade-off as the tokens block above. */
export {
  ToastProvider,
  useToast,
  type ToastInput,
  type ToastTone,
} from "./Toast";
/* eslint-enable react-refresh/only-export-components */
