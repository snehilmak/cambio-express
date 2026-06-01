/**
 * useApiErrorToast — toast-an-API-error helper.
 *
 * Standardises the ~60 call sites across the SPA that all write:
 *
 *   toast({
 *     message: err instanceof ApiError ? err.message : "Generic fallback",
 *     tone: "error",
 *   });
 *
 * After this hook:
 *
 *   const toast = useToast();
 *   const toastApiError = useApiErrorToast();
 *   try {
 *     await api.save();
 *     toast({ message: "Saved.", tone: "success" });
 *   } catch (err) {
 *     toastApiError(err, "Couldn't save the form.");
 *   }
 *
 * The hook returns a function (not the toast object) because it
 * keeps the call site self-documenting — "this toast is for an
 * error from an API call" reads better than threading an extra
 * argument through `useToast()`.
 */
import { useToast } from "../components/ui";
import { ApiError } from "./api";

export function useApiErrorToast(): (err: unknown, fallback: string) => void {
  const toast = useToast();
  return (err: unknown, fallback: string) => {
    toast({
      message: err instanceof ApiError ? err.message : fallback,
      tone: "error",
    });
  };
}
