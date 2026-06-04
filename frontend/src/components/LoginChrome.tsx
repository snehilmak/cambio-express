import type { ReactNode } from "react";

import styles from "./LoginChrome.module.css";

/** Split-screen chrome for the brand-pane auth routes (Login,
 *  TwoFactor Verify/Recover/Enroll). Centered-card routes use
 *  AuthChrome instead.
 *
 *  The left pane holds whatever brand content the route wants
 *  (iso-illustration + testimonial for Login, simple logo block
 *  for TwoFactor); the right pane is a slot for form content
 *  built from kit primitives. */
export function LoginChrome({
  brandPane,
  variant = "fixed",
  brandCentered = false,
  children,
}: {
  brandPane: ReactNode;
  /** ``fixed``: 520px right pane, scrollable (TwoFactor flow —
   *  longer content like QR + recovery codes).
   *  ``flex``: equal-width right pane (Login — short form). */
  variant?: "fixed" | "flex";
  /** Vertically + horizontally center the brand content inside
   *  the left pane (TwoFactor — small logo block). Login spreads
   *  brand content top-to-bottom so leave false. */
  brandCentered?: boolean;
  children: ReactNode;
}) {
  const leftCls = [styles.leftPane];
  if (variant === "flex") leftCls.push(styles.leftPaneWide);
  if (brandCentered) leftCls.push(styles.leftPaneCenter);

  const rightCls = [styles.rightPane];
  if (variant === "fixed") rightCls.push(styles.rightPaneFixed);

  return (
    <div className={styles.shell}>
      <aside className={leftCls.join(" ")}>
        <div className={styles.bgGrid} aria-hidden="true" />
        <div className={styles.bgGlow} aria-hidden="true" />
        {brandPane}
      </aside>
      <div className={rightCls.join(" ")}>
        <div className={styles.card}>{children}</div>
      </div>
    </div>
  );
}

