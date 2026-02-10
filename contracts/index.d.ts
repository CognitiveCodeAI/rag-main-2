/**
 * @npr/contracts TypeScript definitions
 */

export interface JsonSchema {
  $schema: string;
  $id: string;
  title: string;
  type: string;
  [key: string]: unknown;
}

export interface Schemas {
  retrievalPlan: JsonSchema;
  trace: JsonSchema;
  goldenRecord: JsonSchema;
  embedding: JsonSchema;
}

export const schemas: Schemas;
export const schemaDir: string;
export function loadSchema(name: string): JsonSchema;
