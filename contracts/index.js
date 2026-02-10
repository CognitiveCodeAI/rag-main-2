/**
 * @npr/contracts - JSON Schema exports for NPR RAG system
 * 
 * Usage:
 *   import { schemas } from '@npr/contracts';
 *   const retrievalPlanSchema = schemas.retrievalPlan;
 */

const fs = require('fs');
const path = require('path');

const SCHEMA_DIR = path.join(__dirname, 'schemas', 'v1');

function loadSchema(name) {
  const filepath = path.join(SCHEMA_DIR, `${name}.schema.json`);
  return JSON.parse(fs.readFileSync(filepath, 'utf-8'));
}

module.exports = {
  schemas: {
    retrievalPlan: loadSchema('retrieval-plan'),
    trace: loadSchema('trace'),
    goldenRecord: loadSchema('golden-record'),
    embedding: loadSchema('embedding'),
  },
  schemaDir: SCHEMA_DIR,
  loadSchema,
};
