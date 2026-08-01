import { describe, expect, it } from "vitest";

import { normalizedRectToViewport } from "@/components/pdf-viewer/geometry";

describe("normalized evidence geometry", () => {
  it("maps normalized top-left coordinates directly to the rendered viewport", () => {
    const result = normalizedRectToViewport(
      { x0: 0.1, y0: 0.25, x1: 0.6, y1: 0.3 },
      1000,
      800,
    );
    expect(result.x).toBeCloseTo(100);
    expect(result.y).toBeCloseTo(200);
    expect(result.width).toBeCloseTo(500);
    expect(result.height).toBeCloseTo(40);
  });

  it("scales without drifting when the PDF is zoomed", () => {
    const rect = { x0: 0.125, y0: 0.2, x1: 0.5, y1: 0.24 };
    const at100 = normalizedRectToViewport(rect, 612, 792);
    const at200 = normalizedRectToViewport(rect, 1224, 1584);

    expect(at200.x).toBeCloseTo(at100.x * 2);
    expect(at200.y).toBeCloseTo(at100.y * 2);
    expect(at200.width).toBeCloseTo(at100.width * 2);
    expect(at200.height).toBeCloseTo(at100.height * 2);
  });
});
