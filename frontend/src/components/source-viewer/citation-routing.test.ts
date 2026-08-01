import { describe, expect, it } from "vitest";

import type { Citation } from "@/lib/api";
import {
  findCitationForInlineRef,
  INLINE_CITATION_PATTERN,
} from "@/components/source-viewer/citation-routing";

const citations: Citation[] = [
  {
    citation_id: "C1",
    node_id: "node-a",
    doc_id: "doc-1",
    page_no: 14,
    label: "Table 2",
  },
  {
    citation_id: "C2",
    node_id: "node-b",
    doc_id: "doc-1",
    page_no: 14,
  },
];

describe("stable citation routing", () => {
  it("routes a stable citation ID to exactly one evidence record", () => {
    expect(findCitationForInlineRef(citations, "C2")?.node_id).toBe("node-b");
  });

  it("supports exact legacy labels without suffix guessing", () => {
    expect(findCitationForInlineRef(citations, "Table 2")?.node_id).toBe("node-a");
    expect(findCitationForInlineRef(citations, "2")).toBeUndefined();
  });

  it("never substitutes the first citation on a matching page", () => {
    expect(findCitationForInlineRef(citations, "page:14")).toBeUndefined();
    expect(findCitationForInlineRef(citations, "seed:14")).toBeUndefined();
  });

  it("recognizes V2 and legacy inline tokens", () => {
    const answer = "Claim [C1]. Legacy [page: 14].";
    expect([...answer.matchAll(INLINE_CITATION_PATTERN)].map((m) => m[1])).toEqual([
      "C1",
      "page: 14",
    ]);
  });
});
