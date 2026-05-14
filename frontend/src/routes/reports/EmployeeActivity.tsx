import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function EmployeeActivity() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="employee-activity"
      title="Employee Activity"
      resultUnit={["employee", "employees"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/employee-activity.csv`}
      kpis={[
        { label: "Transfers Logged", tone: "primary",
          value: t => Number(t.count ?? 0).toLocaleString() },
        { label: "Total Sent",       tone: "neon",
          value: t => fmtMoney(Number(t.sent ?? 0)) },
        { label: "Employees Active", tone: "muted",
          value: t => Number(t.employees ?? 0).toLocaleString() },
      ]}
      columns={[
        { label: "Employee",   field: "employee" },
        { label: "Transfers",  field: r => Number(r.count ?? 0).toLocaleString(), align: "right", mono: true },
        { label: "Total Sent", field: r => fmtMoney(Number(r.sent ?? 0)),         align: "right", mono: true },
        { label: "First Logged", field: r => (r.first_logged as string) || "—" },
        { label: "Last Logged",  field: r => (r.last_logged as string) || "—"  },
      ]}
    />
  );
}
