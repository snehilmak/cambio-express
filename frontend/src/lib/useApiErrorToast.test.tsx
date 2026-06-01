import { describe, it, expect } from "vitest";
import { renderHook, act, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import { useApiErrorToast } from "./useApiErrorToast";
import { ApiError } from "./api";
import { ToastProvider } from "../components/ui";

function Wrapper({ children }: { children: ReactNode }) {
  return <ToastProvider>{children}</ToastProvider>;
}

describe("useApiErrorToast", () => {
  it("returns a function", () => {
    const { result } = renderHook(() => useApiErrorToast(), { wrapper: Wrapper });
    expect(typeof result.current).toBe("function");
  });

  it("does not throw when called with an ApiError", () => {
    const { result } = renderHook(() => useApiErrorToast(), { wrapper: Wrapper });
    expect(() => {
      act(() => {
        result.current(new ApiError("API said no", 422), "fallback");
      });
    }).not.toThrow();
  });

  it("does not throw when called with a plain Error", () => {
    const { result } = renderHook(() => useApiErrorToast(), { wrapper: Wrapper });
    expect(() => {
      act(() => {
        result.current(new Error("oops"), "fallback");
      });
    }).not.toThrow();
  });

  it("does not throw when called with non-Error values", () => {
    const { result } = renderHook(() => useApiErrorToast(), { wrapper: Wrapper });
    expect(() => {
      act(() => {
        result.current("string error", "fallback");
        result.current(null, "fallback");
        result.current(undefined, "fallback");
        result.current({ shape: "object" }, "fallback");
      });
    }).not.toThrow();
  });

  it("renders an error-tone toast on call", () => {
    function Trigger() {
      const toastApiError = useApiErrorToast();
      return (
        <button
          onClick={() => toastApiError(new ApiError("API failure detail", 422), "fallback")}
        >
          go
        </button>
      );
    }
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    // Region exists but should be empty before the click
    expect(screen.getByRole("region", { name: /notification/i })).toBeInTheDocument();
    act(() => {
      screen.getByRole("button", { name: "go" }).click();
    });
    // After the click, an alert role appears (toast item)
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
