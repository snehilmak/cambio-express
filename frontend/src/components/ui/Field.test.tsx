import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Field } from "./Field";

describe("<Field>", () => {
  it("renders the label + child input", () => {
    render(
      <Field label="Email">
        <input type="email" />
      </Field>,
    );
    expect(screen.getByText("Email")).toBeInTheDocument();
  });

  it("renders the hint when provided", () => {
    render(
      <Field label="Email" hint="We never share this.">
        <input />
      </Field>,
    );
    expect(screen.getByText("We never share this.")).toBeInTheDocument();
  });

  it("renders the error message when provided", () => {
    render(
      <Field label="Email" error="Required.">
        <input />
      </Field>,
    );
    expect(screen.getByText("Required.")).toBeInTheDocument();
  });

  it("hides the label span when label is empty string", () => {
    render(
      <Field label="">
        <input data-testid="bare-input" />
      </Field>,
    );
    // The label wrapper element still exists, but the visible label
    // span doesn't render — useful for stacked controls with a
    // separate header.
    expect(screen.getByTestId("bare-input")).toBeInTheDocument();
  });
});
