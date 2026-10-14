import type bundle from "../generated/fiona.schema.json";

/** The name of any contract definition, e.g. "Proposal", "Verdict", "Figure". */
export type ContractName = keyof (typeof bundle)["$defs"];
