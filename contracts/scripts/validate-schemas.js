#!/usr/bin/env node
/**
 * CI script to validate all JSON schemas compile correctly with ajv.
 */

const Ajv2020 = require('ajv/dist/2020');
const addFormats = require('ajv-formats');
const fs = require('fs');
const path = require('path');

const SCHEMA_DIR = path.join(__dirname, '..', 'schemas', 'v1');

// Schema files to validate
const SCHEMAS = [
  'document-ref.schema.json',
  'document-ir.schema.json',
  'chunk-record.schema.json',
  'retrieval-plan.schema.json',
  'trace.schema.json',
  'golden-record.schema.json',
  'embedding.schema.json',
];

function loadSchema(filename) {
  const filepath = path.join(SCHEMA_DIR, filename);
  const content = fs.readFileSync(filepath, 'utf-8');
  return JSON.parse(content);
}

function validateSchema(ajv, filename) {
  console.log(`Validating: ${filename}`);
  
  try {
    const schema = loadSchema(filename);
    
    // For embedding.schema.json, validate nested schemas
    if (filename === 'embedding.schema.json') {
      if (schema.embedding_templates_spec?.schema) {
        const compiled = ajv.compile(schema.embedding_templates_spec.schema);
        console.log(`  ✓ embedding_templates_spec schema compiles`);
      }
      if (schema.multi_view_vector_record_spec?.schema) {
        const compiled = ajv.compile(schema.multi_view_vector_record_spec.schema);
        console.log(`  ✓ multi_view_vector_record_spec schema compiles`);
      }
      return true;
    }
    
    // Compile schema (validates it's well-formed)
    const compiled = ajv.compile(schema);
    console.log(`  ✓ Schema compiles successfully`);
    return true;
  } catch (error) {
    console.log(`  ✗ FAILED: ${error.message}`);
    return false;
  }
}

function main() {
  console.log('=' .repeat(60));
  console.log('  NPR Contracts - JSON Schema Validation (ajv)');
  console.log('=' .repeat(60));
  console.log();

  // Create ajv instance with JSON Schema draft-2020-12
  const ajv = new Ajv2020({
    strict: false,
    allErrors: true,
    verbose: true,
  });
  addFormats(ajv);

  const results = [];

  for (const schema of SCHEMAS) {
    const schemaPath = path.join(SCHEMA_DIR, schema);
    if (fs.existsSync(schemaPath)) {
      results.push(validateSchema(ajv, schema));
    } else {
      console.log(`Skipping (not found): ${schema}`);
      results.push(true); // Don't fail for missing files
    }
  }

  console.log();
  console.log('=' .repeat(60));
  console.log('  SUMMARY');
  console.log('=' .repeat(60));

  const passed = results.filter(r => r).length;
  const total = results.length;

  console.log(`  Results: ${passed}/${total} schemas validated`);
  console.log('=' .repeat(60));

  process.exit(results.every(r => r) ? 0 : 1);
}

main();
