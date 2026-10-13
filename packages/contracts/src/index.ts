// Placeholder until A2 (Wed 14 Oct): the JSON Schemas, the generated types, Zod schemas and
// the typed client land here. Every response in the system carries this version (R5).
export const API_VERSION = "v1" as const;
export type ApiVersion = typeof API_VERSION;
