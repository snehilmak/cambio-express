import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { Separator } from "./Separator";

describe("<Separator>", () => {
  it("renders with role=separator + horizontal orientation by default", () => {
    const { getByRole } = render(<Separator />);
    const el = getByRole("separator");
    expect(el).toHaveAttribute("aria-orientation", "horizontal");
  });

  it("renders vertical when orientation='vertical'", () => {
    const { getByRole } = render(<Separator orientation="vertical" />);
    expect(getByRole("separator"))
      .toHaveAttribute("aria-orientation", "vertical");
  });

  it("hides from screen readers when decorative", () => {
    const { queryByRole } = render(<Separator decorative />);
    // role="none" strips the implicit separator role
    expect(queryByRole("separator")).toBeNull();
  });
});
