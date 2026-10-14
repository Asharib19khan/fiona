/** Every response in the system carries this version (R5). */
export const API_VERSION = "v1" as const;
export type ApiVersionString = typeof API_VERSION;
