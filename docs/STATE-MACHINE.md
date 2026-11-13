# RAD Pipeline — State Transition Rules v0.1

| From | To | Required evidence / guard |
|---|---|---|
| INTAKE | DESIGN_READY | scope, stakeholders, requirements source and acceptance intent identified |
| DESIGN_READY | IMPLEMENTATION_READY | architecture/interfaces reviewed; unresolved design decisions closed or explicitly non-blocking |
| IMPLEMENTATION_READY | BUILT | authorized build completed; source revision and build output identified |
| BUILT | BASELINED | immutable source/build/environment/deployment identity recorded |
| BASELINED | TESTED | authorized test plan executed; raw results captured; errors/timeouts visible |
| TESTED | TRIAGED | every failure/non-pass classified or marked inconclusive; finding IDs assigned |
| TRIAGED | RECONCILING | affected artifact audits launched; common baseline and finding IDs shared |
| RECONCILING | CORRECTED | approved decisions recorded; corrections linked to findings and artifact revisions |
| CORRECTED | REGRESSION_VERIFIED | affected tests and required regression set pass, or residual failures explicitly remain |
| REGRESSION_VERIFIED | ACCEPTANCE_READY | traceability, architecture, CEG, README, descriptions and evidence checks complete |
| ACCEPTANCE_READY | RELEASED | explicit release authority and all project policy gates satisfied |

## Side-state rules
- Any active state may move to WAITING_FOR_INPUT, BLOCKED, FAILED or CANCELLED with a reason and evidence.
- WAITING_FOR_INPUT returns only when the referenced decision is recorded.
- BLOCKED returns only when the prerequisite is independently verified.
- FAILED may retry as a new attempt; previous evidence remains immutable.
- SUPERSEDED requires a successor cycle reference and preserves prior lineage.

## Global transition guards
- No state advances because a timer elapsed.
- Unknown or missing policy evaluation means deny.
- No test pass substitutes for missing requirements or artifact review.
- No observed runtime behavior silently becomes intended behavior.
- No unresolved requirement ambiguity may be bypassed for dependent corrections.
- No semantic CEG changes or generation may bypass the project's CEG gate.
- No merge/deploy/release without explicit recorded authorization.
- Notifications never change pipeline state.
