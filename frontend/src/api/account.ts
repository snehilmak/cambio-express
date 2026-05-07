// Account-side API helpers (password change, future profile,
// preferences, etc.).

import { api } from "./../lib/api";

export interface ChangePasswordBody {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export async function changePassword(
  body: ChangePasswordBody,
): Promise<{ status: string }> {
  return api<{ status: string }>(
    "/api/v2/auth/change-password",
    { method: "POST", json: body },
  );
}
