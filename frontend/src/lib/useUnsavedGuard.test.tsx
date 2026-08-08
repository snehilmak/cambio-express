import { describe, it, expect, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useUnsavedGuard } from "./useUnsavedGuard";

describe("useUnsavedGuard", () => {
  it("runs proceed immediately when clean (no dialog)", () => {
    const proceed = vi.fn();
    const { result } = renderHook(() => useUnsavedGuard(false));
    act(() => result.current.confirmLeave(proceed));
    expect(proceed).toHaveBeenCalledTimes(1);
    expect(result.current.dialogProps.open).toBe(false);
  });

  it("stages the dialog when dirty and defers proceed until confirmed", () => {
    const proceed = vi.fn();
    const { result } = renderHook(() => useUnsavedGuard(true));

    act(() => result.current.confirmLeave(proceed));
    expect(proceed).not.toHaveBeenCalled();
    expect(result.current.dialogProps.open).toBe(true);

    act(() => result.current.dialogProps.onConfirm());
    expect(proceed).toHaveBeenCalledTimes(1);
    expect(result.current.dialogProps.open).toBe(false);
  });

  it("cancelling the dialog does not proceed and closes it", () => {
    const proceed = vi.fn();
    const { result } = renderHook(() => useUnsavedGuard(true));

    act(() => result.current.confirmLeave(proceed));
    expect(result.current.dialogProps.open).toBe(true);

    act(() => result.current.dialogProps.onCancel());
    expect(proceed).not.toHaveBeenCalled();
    expect(result.current.dialogProps.open).toBe(false);
  });

  it("honors custom title/message overrides", () => {
    const { result } = renderHook(() =>
      useUnsavedGuard(true, { title: "T", message: "M" }),
    );
    expect(result.current.dialogProps.title).toBe("T");
    expect(result.current.dialogProps.message).toBe("M");
  });
});
