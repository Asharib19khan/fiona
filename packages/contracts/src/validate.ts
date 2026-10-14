import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import bundle from "../generated/fiona.schema.json" with { type: "json" };
import type { ContractName } from "./names";

/** Full JSON Schema validation, including cross-field rules the TypeScript types can't express. */
// strictTypes/strictRequired are off because the cross-field rules use if/not without repeating
// "type" and "properties"; unknown keywords are still rejected (strictSchema).
const ajv = new Ajv2020({ allErrors: true, strict: true, strictTypes: false, strictRequired: false, allowUnionTypes: true, discriminator: true });
addFormats(ajv);
ajv.addSchema(bundle);

const ID = bundle.$id;

export interface ContractIssue {
  path: string;
  message: string;
}

export class ContractError extends Error {
  constructor(
    readonly contract: ContractName,
    readonly issues: ContractIssue[],
  ) {
    super(`${contract} is invalid: ${issues.slice(0, 5).map((i) => `${i.path || "/"} ${i.message}`).join("; ")}`);
    this.name = "ContractError";
  }
}

function validatorFor(name: ContractName) {
  const v = ajv.getSchema(`${ID}#/$defs/${name}`);
  if (!v) throw new Error(`No contract named ${name}`);
  return v;
}

/** Issues found when checking `data` against contract `name`; empty when valid. */
export function check(name: ContractName, data: unknown): ContractIssue[] {
  const v = validatorFor(name);
  if (v(data)) return [];
  return (v.errors ?? []).map((e) => ({ path: e.instancePath, message: e.message ?? "invalid" }));
}

/** Throws ContractError when `data` does not satisfy contract `name`. */
export function validate(name: ContractName, data: unknown): void {
  const issues = check(name, data);
  if (issues.length) throw new ContractError(name, issues);
}
