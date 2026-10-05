/**
 * Copyright (c) Brand.Me, Inc. All rights reserved.
 *
 * Request-body validators compiled from the generated OpenAPI document in
 * @brandme/contracts (single source of API vocabulary; no hand-copied schemas).
 */

import { readFileSync } from 'node:fs';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';

const openapi = JSON.parse(readFileSync(require.resolve('@brandme/contracts/openapi.json'), 'utf8'));
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema({ $id: 'brandme-api', components: openapi.components }, 'brandme-api');

export function validator(schemaName: string) {
  if (!openapi.components.schemas[schemaName]) throw new Error(`unknown contract schema ${schemaName}`);
  const fn = ajv.getSchema(`brandme-api#/components/schemas/${schemaName}`);
  if (!fn) throw new Error(`could not compile ${schemaName}`);
  return fn;
}
