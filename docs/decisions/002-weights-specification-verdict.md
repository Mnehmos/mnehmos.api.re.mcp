# 002. Weights / specification / verdict worksheet

- **Status:** accepted
- **Date:** 2026-09-12

Per the bible: for each runtime capability, name what the model's output draws
on. "A rule that lives only in the weights is a hope. A rule that lives only
in the specification is a request. A rule that lives in the verdict is a law."

| Capability | Weights (model knows) | Specification (we supply) | Verdict (we enforce) |
| ---------- | --------------------- | ------------------------- | -------------------- |
| Capture session | how apps expose HTTP/WS/pipes | transport enum, authorization statement, filter grammar | listener health warnings; refused start without statement; frames hashed on write |
| Redaction | what credentials look like | denylists + shape patterns + key-name rules (the spec, not the model's judgment, decides) | stored-bytes assertion tests; redaction report per frame |
| Differential analysis | plausible cause-effect stories | canonical-key definition, exclusivity/ordering/periodicity formulas | recompute-from-store verifiers; heartbeat exclusion |
| Semantic naming | API naming conventions, domain vocabularies | proposal schema, evidence_refs requirements | `llm_proposal` cap 0.0; corroboration rule; verification record |
| Experiment proposals | what discriminating observations look like | experiments schema (tied to open questions) | proposals never execute; human performs |
| Export | spec-format fluency (OpenAPI/AsyncAPI) | projection rules, min_level floor, speculative section | parse-validity tests; no-secret-in-export tests |

Standing rule: whenever a defect is caused by relying on weights ("the model
should have known that"), move the rule into specification or verdict instead
of prompt-blaming the model. Track these moves in ADRs.
