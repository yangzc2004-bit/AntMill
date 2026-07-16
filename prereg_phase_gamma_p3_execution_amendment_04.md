# Phase Gamma P3 execution amendment 04: immutable browser runtime and cross-run environment gate

Status: frozen on 2026-07-15 before generating any P3e smoke or formal outcome data.

## Trigger

The authorized P3 formal launch in `runs_miniwob_gamma_p3b` used the
system-managed Chrome path frozen in amendment 03. An outcome-blind provenance
refresh after 16 of 54 results had completed found that Chrome had updated
during the matrix: 11 completed manifests recorded `150.0.7871.115` and five
recorded `150.0.7871.124`. The MiniWoB++ commit, package versions, task
registration, local task URL, and independent-environment count remained
unchanged.

This violates the base appendix requirement that the package/browser
configuration not change between smoke and formal data. The partial P3b formal
artifacts are retained for infrastructure audit only. They are excluded from
all behavioral estimates, pooled gates, task-family effects, and manuscript
claims. No pooled or arm-comparative P3b behavioral result was calculated
before this amendment.

## Immutable browser runtime

P3e uses a workspace-local copy of the complete Chrome application directory:

`D:/antmill/tmp/pinned_chrome_150.0.7871.124/Application/chrome.exe`

The frozen runtime identifiers are:

- browser version: `150.0.7871.124`;
- executable SHA-256:
  `40ad3d87ea81270f36137e6f84fb36e9a2236aedd835696dd663ac1a27dd1b13`;
- deterministic 273-file application-tree SHA-256:
  `aa89fed38bda67c473a1db216cb54d99ed55ee613317de248634e2cabffc9680`;
- application-tree byte count: `501388593`.

The tree digest is computed by sorting every forward-slash relative path in
ascending Unicode code-point order, encoding each record as
`relative_path<TAB>length<TAB>sha256`, joining records with LF, and hashing the
resulting UTF-8 bytes. The local per-file record is
`tmp/pinned_chrome_150.0.7871.124/files.json`.

Before this freeze, engineering-only probes opened eight independent
`click-button` environments at reset seeds 0--7 and executed one `noop()` in
each. All eight resets and steps completed without infrastructure errors. The
first probe caused Chrome to install one `en-US` dictionary inside the copied
application tree; the tree was rehashed, and a second four-environment probe
left the 273-file tree byte-for-byte unchanged. The probes made no LLM calls
and produced no arm-comparative or behavioral outcome.

For the entire P3e smoke and formal sequence, set:

```powershell
$env:MINIWOB_URL = "file:///D:/antmill/tmp/miniwob-plusplus/miniwob/html/miniwob/"
$env:MINIWOB_BROWSER_EXECUTABLE = "D:/antmill/tmp/pinned_chrome_150.0.7871.124/Application/chrome.exe"
```

The runner records the browser executable hash in every manifest. Before each
smoke or formal launch, the executable version and SHA-256 must match the
values above. Any mismatch stops the launch.

## Frozen P3e execution

Rerun the unchanged complete 18-result smoke matrix in fresh directories:

- `runs_miniwob_gamma_p3e_smoke`
- `cache_miniwob_gamma_p3e_smoke`

Only a complete pass of all base-appendix and amendments 01--03 smoke checks
authorizes the unchanged 54-result formal matrix in:

- `runs_miniwob_gamma_p3e`
- `cache_miniwob_gamma_p3e`

P3e smoke is engineering-only and is excluded from formal analysis. P3d smoke
is not combined with P3e smoke because it used the auto-updating system Chrome
path.

## Cross-run environment consistency gate

Formal quality is clear only if all 54 completed manifests agree exactly on:

- MiniWoB++ commit, primary/replacement task lists, and local MiniWoB URL;
- Python version;
- browser executable path, version, and executable SHA-256;
- BrowserGym, Gymnasium, and Playwright package versions;
- task-validation status, registered-task count, and missing-task list;
- independent BrowserGym environments per task.

This exact cross-run environment check is a hard formal-quality gate. Any
disagreement withholds all P3 behavioral estimates and yields a formal quality
warning requiring review.

## What remains unchanged

This amendment changes no model, task family, replacement policy, arm,
prompt, action schema, cache policy, metric, threshold, formal sample size,
paired analysis, outcome rule, or stopping rule. It adds an immutable browser
runtime and a provenance gate only. It grants no tuning, rescue, extra-seed,
or outcome-dependent rerun freedom.
