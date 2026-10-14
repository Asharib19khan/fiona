// Fiona contracts v1: the only surface shared across boxes (R1).
// Types are generated from schemas/*.yaml; run `pnpm gen` after editing a schema.
export type * from "../generated/ts/types";
export { API_VERSION, type ApiVersionString } from "./version";
export type { ContractName } from "./names";
export { check, validate, ContractError, type ContractIssue } from "./validate";
export { canonicalJson, verdictHash } from "./hash";
export {
  createEngineClient,
  contractGuard,
  FionaApiError,
  type ClientOptions,
  type EngineClient,
  type EnginePaths,
} from "./client";
