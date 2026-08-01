import type { NormalizedRect } from "@/lib/api";

export interface ViewportRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function normalizedRectToViewport(
  rect: NormalizedRect,
  viewportWidth: number,
  viewportHeight: number,
): ViewportRect {
  return {
    x: rect.x0 * viewportWidth,
    y: rect.y0 * viewportHeight,
    width: (rect.x1 - rect.x0) * viewportWidth,
    height: (rect.y1 - rect.y0) * viewportHeight,
  };
}
