# The Ant Mill as a Model of Multi-Agent Experiential Collapse

Working notes for the SEC project: framing multi-agent shared-experience collapse as an
"AI ant mill", with a paper-ready draft and a formal control-parameter / phase-transition
correspondence that yields falsifiable predictions wired to the experiment matrix.

---

## Part A. Introduction / Related Work draft (English, with citations)

### A.1 Motivating framing (Introduction opener)

> When a detachment of army ants loses contact with the main raiding column, the workers
> default to following the nearest neighbor and the local pheromone gradient. Lacking any
> external reference to the true location of nest or prey, the chemical trail they lay closes
> on itself: each ant reinforces a signal that is produced entirely by the other ants. The
> resulting *circular mill*, or *death spiral*, is a self-sustaining absorbing state in which
> the colony rotates until it dies of exhaustion (Schneirla, 1944). Strikingly, the very trait
> that makes army ants efficient collective foragers — strong fidelity to a self-organized
> pheromone trail — is what dooms a severed detachment (Delsuc, 2003). The death spiral is not
> a malfunction of any individual ant; it is an emergent failure mode of a stigmergic system
> driven by positive feedback once its external anchor is removed.
>
> We argue that cooperative LLM multi-agent systems with shared experiential memory are prone
> to a structurally identical failure. When several agents learn from a *shared* memory and use
> their own *mutual agreement* — rather than external ground truth — as the signal that decides
> which experiences to keep, the shared memory becomes a digital pheromone trail. Consensus
> reinforces memory, memory homogenizes the agents, and the agents in turn manufacture more
> consensus. We call this **Shared-Experience Collapse (SEC)**: a regime in which group
> consensus stays high or rises while held-out accuracy degrades and behavioral diversity
> collapses — agents that are confidently, collectively wrong. We show that SEC is governed by a
> single assimilation control parameter, exhibits a sharp tipping point with measurable
> early-warning signals, and is prevented precisely by restoring an external anchor — the AI
> analogue of an intact trail to the nest.

### A.2 Related work paragraph

> **Stigmergy and self-organized collective failure.** Social-insect coordination is the
> canonical example of stigmergy, in which individuals couple indirectly by modifying a shared
> environment rather than by direct communication (Grassé, 1959). Such positive-feedback
> systems readily produce large-scale order from local rules (Sumpter, 2006), including
> symmetry-breaking lock-in onto a single, possibly suboptimal, path (Deneubourg et al., 1990)
> and self-organized lane formation in army-ant traffic (Couzin & Franks, 2003). The same
> dynamics also produce pathological absorbing states: the army-ant circular mill (Schneirla,
> 1944; Delsuc, 2003). Couzin et al. (2002) show that a single control parameter — the strength
> or radius of inter-individual alignment — drives an abrupt transition into a rotating "torus"
> (milling) state, placing the death spiral within the theory of collective phase transitions.
> **Critical transitions and early-warning signals.** Systems approaching such a tipping point
> exhibit critical slowing down, detectable as rising variance and lag-1 autocorrelation in an
> order parameter (Scheffer et al., 2009). **Model collapse.** In the learning literature, the
> analogous recursion — training on a system's own generated outputs without fresh ground signal
> — degrades models over generations (Shumailov et al., 2024). **Multi-agent LLMs and shared
> memory.** Multi-agent debate improves reasoning by letting agents revise toward consensus
> (Du et al., 2023), but consensus can also entrench errors through conformity. Experiential
> agents such as ExpeL extract reusable natural-language insights and recall them at inference
> (Zhao et al., 2024); recent work extends experiential memory to multi-agent collaboration
> (MAEL; Cross-Task Experiential Learning, 2025). These methods are designed to *improve*
> performance through accumulated, shared experience. We instead treat the shared experiential
> memory as a stigmergic positive-feedback channel and ask when it *collapses* the system.

### A.3 Contribution paragraph

> **Contributions.** (1) We formalize Shared-Experience Collapse as a stigmergic phase
> transition isomorphic to the army-ant circular mill, identifying the assimilation pressure as
> the order-tuning control parameter and the loss of external anchoring as the triggering
> perturbation. (2) On a multi-agent-debate substrate with a cross-task shared insight memory,
> we demonstrate a dose-response tipping point: past a critical assimilation pressure the system
> enters an absorbing high-consensus / low-accuracy / low-diversity state. (3) We show that the
> collapse is preceded by critical-slowing-down early-warning signals, and is prevented by a
> minimal dose of external ground-truth anchoring — the AI analogue of an intact pheromone trail
> to the nest. (4) We document an efficiency-fragility trade-off mirroring the army-ant case:
> the coupling that maximizes early collaborative accuracy gains is the same coupling that
> maximizes collapse risk.

---

## Part B. Control parameter -> phase transition: formal correspondence and predictions

### B.1 State (order) variables, measured per round t

- `A_t`  held-out accuracy against gold labels (evaluation only; isolated from the training signal).
- `C_t`  consensus = fraction of agents in the majority cluster.
- `D_t`  behavioral diversity: entropy of the agent answer distribution + embedding dispersion of
         trajectories + effective rank of the shared memory.
- `G_t = C_t - A_t`  hallucinated-consensus gap (confident-but-wrong).

**SEC (collapse) state, joint definition:** relative to a `memory = none` baseline, a sustained
regime with `A drop >= delta`, `C >= c_high`, and `D <= D_low`, persisting >= k rounds.

### B.2 Control parameters

- **Assimilation pressure `alpha`** (order-tuning knob, increases coupling/homogenization):
  composed of memory sharing (none < private < shared), dissent pruning strength (mu),
  late-round temperature (lower = stronger), and whole-library vs per-agent-retrieval injection.
- **External anchoring `rho`** in [0,1]: probability that gold labels correct the experiences
  entering memory each round. `rho = 0` = pure consensus (severed trail); `rho = 1` = fully
  ground-truth anchored (intact trail).

### B.3 The isomorphism (state it explicitly in the paper)

| Army-ant circular mill | SEC in a multi-agent LLM system |
|---|---|
| Pheromone trail (shared stigmergic medium) | Shared experience / insight library ("digital pheromone") |
| Trail-following positive feedback | consensus -> memory -> agent homogenization -> consensus |
| Severed trail to nest/food (perturbation) | `rho -> 0`: removal of external ground-truth anchor |
| Slow evaporation, no error correction | weak memory decay, no external reward signal |
| Alignment strength / radius (Couzin 2002) | assimilation pressure `alpha` |
| Torus / milling absorbing state | high-`C`, low-`A`, low-`D` collapsed consensus |
| Trail fidelity = efficiency AND cause of death | consensus/assimilation = collaborative gain AND cause of collapse |

### B.4 Falsifiable predictions (each maps to a condition in the matrix)

- **P1 - Tipping point (not gradual).** There exists a critical `alpha_c` such that for
  `alpha > alpha_c` the system enters the SEC absorbing state. The `A_final` vs `alpha` curve is
  sigmoidal/discontinuous, not linear. *Test:* sweep `alpha`, locate the knee; compare a
  threshold model vs a linear fit (the threshold model should win).

- **P2 - Critical slowing down / EWS.** As `alpha -> alpha_c^-`, and within a collapsing run as
  `t -> t*`, rolling variance and lag-1 autocorrelation of `D_t` and `G_t` rise. *Test:* the
  existing `ews()` applied to `D_t`/`G_t`; EWS should rise pre-collapse in SEC runs and stay flat
  in anchored controls.

- **P3 - External anchor is necessary (severed-trail condition).** Collapse requires `rho ~ 0`;
  there is a minimal anchoring dose `rho*` above which SEC does not occur. *Test:* dose-response
  over `rho in {0, 0.25, 0.5, 1.0}`; `A_final` recovers and `D` is preserved past `rho*`.

- **P4 - Efficiency-fragility trade-off (Delsuc).** Across the `alpha` sweep, the coupling that
  yields the largest early `A_peak` gain over the single-agent baseline also yields the largest
  subsequent `A_drop`. *Test:* plot `A_peak gain` vs `A_drop`; predict a positive correlation —
  i.e., you cannot tune for max collaborative gain without buying collapse risk.

- **P5 - Absorbing state / hysteresis (optional, strong if it holds).** After collapse, restoring
  `rho` to a high value does not immediately recover `A`; the system is bistable, mirroring the
  fact that ants do not spontaneously leave the mill. *Test:* a within-run protocol that flips
  `rho` 0 -> 1 at `t*`; recovery should lag (hysteresis loop).

- **P6 - Stigmergic mediation is necessary, not mere interaction.** At matched `alpha` and
  matched interaction, `memory = shared` collapses but `memory = private` does not. *Test:* the
  shared-vs-private memory ablation; isolates the shared substrate (the pheromone) as the
  collapse channel, distinct from debate/interaction per se.

### B.5 Headline figure

x-axis = assimilation pressure `alpha` (or, inversely, anchoring `rho`); plot `A_final`,
`C_final`, and `D_final` together. The predicted signature is a **crossover**: as `alpha` rises
past `alpha_c`, `C` stays high while `A` and `D` fall — the AI ant mill.

---

## References

- Schneirla, T. C. (1944). *A unique case of circular milling in ants, considered in relation to
  trail following and the general problem of orientation.* American Museum Novitates, 1253.
- Delsuc, F. (2003). *Army ants trapped by their evolutionary history.* PLoS Biology, 1(2), e37.
- Couzin, I. D., Krause, J., James, R., Ruxton, G. D., & Franks, N. R. (2002). *Collective memory
  and spatial sorting in animal groups.* Journal of Theoretical Biology, 218(1), 1-11.
- Couzin, I. D., & Franks, N. R. (2003). *Self-organized lane formation and optimized traffic flow
  in army ants.* Proceedings of the Royal Society B, 270(1511), 139-146.
- Deneubourg, J.-L., Aron, S., Goss, S., & Pasteels, J. M. (1990). *The self-organizing exploratory
  pattern of the Argentine ant.* Journal of Insect Behavior, 3(2), 159-168.
- Grasse, P.-P. (1959). *La reconstruction du nid et les coordinations interindividuelles... La
  theorie de la stigmergie.* Insectes Sociaux, 6, 41-80.
- Sumpter, D. J. T. (2006). *The principles of collective animal behaviour.* Philosophical
  Transactions of the Royal Society B, 361(1465), 5-22.
- Scheffer, M., et al. (2009). *Early-warning signals for critical transitions.* Nature, 461, 53-59.
- Shumailov, I., Shumaylov, Z., Zhao, Y., Papernot, N., Anderson, R., & Gal, Y. (2024). *AI models
  collapse when trained on recursively generated data.* Nature, 631, 755-759. (See also: *The Curse
  of Recursion*, arXiv:2305.17493, 2023.)
- Du, Y., Li, S., Torralba, A., Tenenbaum, J. B., & Mordatch, I. (2023). *Improving factuality and
  reasoning in language models through multiagent debate.* arXiv:2305.14325.
- Zhao, A., Huang, D., Xu, Q., Lin, M., Liu, Y.-J., & Huang, G. (2024). *ExpeL: LLM agents are
  experiential learners.* AAAI-24. arXiv:2308.10144.
- *Cross-Task Experiential Learning on LLM-based Multi-Agent Collaboration (MAEL).* (2025).
  arXiv:2505.23187.
