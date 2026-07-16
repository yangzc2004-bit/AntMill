# Phase Gamma amendment 01: equal-dose archive rescue

Status: corrective preregistration written after inspecting the completed additive-rescue implementation and outcomes, and before generating any P1b smoke or formal outcome data.

This document does not modify or replace `prereg_phase_gamma.md` or its freeze record. It records a protocol deviation in the completed P1 rescue and freezes one bounded corrective experiment.

## 1. Completed P1 deviation

The completed arm `gamma_p1_shared_consolidated_archive_rescue` implemented retrieval as active top-6 plus archive top-6. The resulting solver context could therefore contain up to 12 injected memories, whereas the E2 consolidated control used a total top-6.

`archive_retrieval_k=6` as a separate additive quota was not fixed in the prose preregistration. It changes both archive access and retrieval dose, so the completed arm cannot adjudicate the equal-dose question "does read-only archive access rescue consolidation degradation when total retrieval capacity is held fixed?"

The completed result remains a valid evaluation of a naive additive engineering fix. It will be labeled `additive_archive_rescue`, retained without modification, and reported separately. It will not be pooled with P1b for a primary confirmatory analysis.

## 2. P1b intervention

P1b arm name: `gamma_p1b_shared_consolidated_archive_joint_topk`.

The consolidated write protocol remains byte-for-byte/config-for-config identical to P1 and E2. Solver retrieval forms one candidate set from the live active pool and the read-only archive, computes one common ranking, and injects at most `retrieval_k=6` items in total. There is no reserved archive quota and no second retrieval pass.

Archive sources remain fixed to DOWNVOTE target text, EDIT pre-edit text, and similarity-merge discarded text. Archive items never change reviewer operations or active-pool membership.

The original additive protocol remains available only for reproducing the completed run. New P1b data must use `memory_read_protocol=archive_joint_topk`.

## 3. Audit and dose invariants

Every retrieval record must include:

- active and archive candidate counts;
- total injected count and active/archive injected counts;
- configured total retrieval limit;
- selected item id, source, rank, score, and relevance;
- a dose-compliance flag.

The formal invariant is `active_injected + archive_injected == total_injected <= retrieval_k`. Any violation invalidates the affected run and must stop P1b before gate evaluation.

Before formal data, run a development smoke with seed 9001, `T=2`, `heldout=2`, `train_batch=4`, four solvers, and the formal maze/model/retrieval settings. Smoke outcomes are engineering-only and are not included in formal analyses. Smoke passes only if:

1. every retrieval satisfies the dose invariant;
2. archive and active items use one joint ranking;
3. parse failure rate is below 5%;
4. after the archive becomes non-empty, at least one archive item can enter the joint top-6.

If condition 4 fails, report `archive_ranking_inaccessible_in_smoke`, stop P1, and do not tune similarity weights, reserve archive slots, or run P1b formal data.

## 4. Formal P1b design and manipulation check

If smoke passes, run seeds 0-2 with the original P1 formal settings: DeepSeek-V3, trap maze, `T=6`, `heldout=12`, four solvers, `retrieval_k=6`, `library_cap=80`, `max_steps=120`, and cached E2 consolidated controls allowed by the passed Gamma drift probe.

Before the behavioral rescue gate, evaluate the manipulation check at `t=5`:

- zero dose violations in every seed;
- at least one archive item injected in every seed after archive creation;
- in at least 2/3 seeds, total distinct injected items at `t=5` are at least 1.5 times the corresponding E2 consolidated active distinct-injected count.

If the manipulation check fails, label P1b `ranking_inaccessible_not_evaluable`, do not interpret it as evidence against archive rescue, do not run compression, and stop P1.

If the manipulation check passes, apply the original rescue behavioral gate without changes: success non-inferiority CI lower bound greater than -0.05; success-excess-steps or looped significantly improves; the other endpoint has a non-worse point estimate; failure-penalized cost has a non-worse point estimate; and at least 2/3 seeds have the favorable sign.

No seeds 3-4 will be added in P1b. This amendment replaces the original optional-seed branch for the corrective run to enforce a hard time limit.

## 5. Frozen interpretation and stopping rules

- Manipulation passes and behavioral gate passes: report equal-dose intervention-rescue evidence and permit the preregistered compression arm.
- Manipulation passes and behavioral gate fails: report additive and equal-dose rescue as two negative interventions; do not run compression.
- Manipulation fails: report archive ranking/access as insufficient under fixed retrieval capacity; do not run compression.
- The completed additive arm may be compared descriptively with P1b as an exploratory dose contrast, but this later comparison is not a randomized primary contrast.
- No archive-source ablations, reserved archive quotas, ranking-weight tuning, additional rescue variants, or additional P1 seeds will be run after P1b.

After the P1b decision, proceed to P2 cross-model replication and P3 task-family generalization. Cross-model or MiniWoB rescue is allowed only if P1b passes its equal-dose behavioral rescue gate and the corresponding phenomenon replication is positive.

