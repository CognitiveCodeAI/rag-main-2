import type { Citation } from "@/lib/api";

export const INLINE_CITATION_PATTERN = /\[(C\d+|(?:seed|adjacent|page):\s*\d+)\]/gi;

export function normalizeInlineRef(value: string): string {
  return value.toLowerCase().replace(/[\[\]\s]+/g, "");
}

export function findCitationForInlineRef(
  citations: Citation[] | undefined,
  rawRef: string,
): Citation | undefined {
  if (!citations?.length) return undefined;

  const normalizedRef = normalizeInlineRef(rawRef);
  const byStableId = citations.find(
    (citation) => citation.citation_id?.toLowerCase() === normalizedRef,
  );
  if (byStableId) return byStableId;

  // Legacy labels are accepted only on an exact normalized match. Page-number
  // guessing is intentionally forbidden because multiple nodes may share a page.
  return citations.find(
    (citation) =>
      Boolean(citation.label)
      && normalizeInlineRef(citation.label as string) === normalizedRef,
  );
}
