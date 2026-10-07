# OMEGA Governance Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production slice of the approved OMEGA architecture: a typed, validated, traceable ecosystem registry and capability graph with bounded-cycle enforcement, read-only CLI inspection, canonical logs, and regression tests.

**Architecture:** Add a focused `vortex/ecosystem/` package that owns Pydantic v2 domain models, artifact loading/validation, and loop-cycle invariants. Keep the existing Typer CLI as the shell and attach a thin `ecosystem` sub-application. Root JSON/Markdown artifacts remain the canonical human- and machine-readable state; upstream runtimes are not integrated in this slice.

**Tech Stack:** Python >=3.9, Pydantic >=2.5, Typer >=0.9, pytest >=7.4, stdlib `json`, `pathlib`, `enum`, `urllib.parse`.

**Spec:** `docs/superpowers/specs/2026-10-07-omega-ecosystem-design.md`

## Global Constraints

- Preserve every user-supplied URL exactly; never normalize or rewrite the stored source URL.
- Unknown metadata stays explicitly unknown/null; do not fabricate licenses, scores, maintenance data, capabilities, or evidence.
- No upstream repository is trusted by default.
- No cloning, installation, network execution, live trading, wallet action, prediction-market order, messaging mutation, deployment, or credential use in this slice.
- Candidate decisions are one of `integrate`, `adapt`, `replace`, `reference-only`, `reject`, or remain undecided/discovered until evidence exists.
- Each bounded execution cycle must define objective, capability area, time budget, token budget, repository budget, implementation budget, verification budget, and measurable success metric.
- A completed cycle is valid only when at least one qualifying outcome exists: production code, removed complexity, improved benchmark, closed security issue, reduced cost, improved reliability, better documented architecture, or an evidence-backed rejection/replacement.
- A capability discovery branch terminates after three consecutive passes find no superior implementation with measurable advantage.
- Canonical root artifacts: `ecosystem_manifest.json`, `capability_graph.json`, `decision_log.md`, `rejection_log.md`, `integration_log.md`, `benchmark_log.md`, `security_log.md`, `roadmap.md`.
- Python compatibility floor remains 3.9; do not introduce syntax requiring 3.10+.
- Existing project-wide test threshold remains `--cov-fail-under=90`.

## Review Focus

1. Duplicate candidate URLs or IDs must fail validation instead of silently shadowing one another.
2. Non-repository URLs (websites, npm pages, documentation, badge assets) must remain traceable without being treated as cloneable repositories.
3. Stored URLs must remain byte-for-byte equal to the approved input inventory, including trailing slashes and legacy documentation URLs.
4. Capability graph edges referencing unknown candidates or unknown capabilities must fail validation before use.
5. A cycle with zero qualifying outcomes, non-positive budgets, or fewer than three consecutive no-improvement discovery passes must not be marked terminated/successful.

---

## File Structure

### New package

- `vortex/ecosystem/__init__.py` — public exports only.
- `vortex/ecosystem/models.py` — Pydantic enums/models for candidates, manifests, capabilities, graph edges, and evidence.
- `vortex/ecosystem/loader.py` — JSON loading plus cross-artifact validation.
- `vortex/ecosystem/cycle.py` — bounded-cycle and discovery-termination invariants.
- `vortex/cli/ecosystem.py` — read-only Typer subcommands.

### Canonical configuration/state

- `ecosystem_manifest.json` — complete seed inventory from Appendix A.
- `capability_graph.json` — initial canonical capability taxonomy plus candidate edges only where the input itself supports the association.
- `config/ecosystem/ecosystem_manifest.schema.json` — generated Pydantic JSON schema snapshot.
- `config/ecosystem/capability_graph.schema.json` — generated Pydantic JSON schema snapshot.
- `decision_log.md`
- `rejection_log.md`
- `integration_log.md`
- `benchmark_log.md`
- `security_log.md`
- `roadmap.md`

### Tests

- `tests/test_ecosystem_models.py`
- `tests/test_ecosystem_loader.py`
- `tests/test_ecosystem_cycle.py`
- `tests/test_ecosystem_cli.py`
- `tests/test_ecosystem_artifacts.py`
- `tests/fixtures/ecosystem_expected_urls.txt`

### Existing files modified

- `vortex/cli/app.py` — register `ecosystem_app`; no ecosystem business logic here.

---

### Task 1: Typed ecosystem domain models

**Files:**
- Create: `vortex/ecosystem/__init__.py`
- Create: `vortex/ecosystem/models.py`
- Test: `tests/test_ecosystem_models.py`

**Interfaces:**
- Consumes: Pydantic v2 only.
- Produces:
  - `CandidateKind`
  - `CandidateStatus`
  - `IntegrationMode`
  - `DecisionDisposition`
  - `EvidenceRef`
  - `MaintenanceSignals`
  - `CandidateScores`
  - `EcosystemCandidate`
  - `EcosystemManifest`
  - `CapabilityDefinition`
  - `CapabilityEdge`
  - `CapabilityGraph`

- [ ] **Step 1: Write failing model tests**

Create tests asserting:

```python
def test_manifest_rejects_duplicate_ids(): ...
def test_manifest_rejects_duplicate_urls(): ...
def test_candidate_preserves_exact_https_url(): ...
def test_candidate_rejects_non_https_url(): ...
def test_candidate_kind_supports_repository_website_package_docs_and_badge_asset(): ...
def test_scores_allow_unknown_values_without_inventing_defaults(): ...
```

Exact semantics:
- `EcosystemManifest.schema_version == "1.0"`.
- `EcosystemCandidate.url` is a plain `str` validated with `urllib.parse.urlsplit`; return the original string unchanged.
- Scheme must equal `https`; hostname must be non-empty.
- `license`, `language`, and every score default to `None`.
- `CandidateScores` fields are `capability_fit`, `production_readiness`, `security`, `maintenance`, `interop`, `complexity`, `cost`, `replacement_value`; each is `Optional[float]` constrained to `[0.0, 100.0]` when present.
- Duplicate `id` or exact `url` values raise `pydantic.ValidationError`.

- [ ] **Step 2: Run model tests and verify failure**

Run: `pytest tests/test_ecosystem_models.py -q`
Expected: FAIL because `vortex.ecosystem.models` does not exist.

- [ ] **Step 3: Implement domain models**

Required enum values:

```text
CandidateKind: repository, website, package, docs, badge_asset
CandidateStatus: discovered, evaluating, selected, integrated, replaced, rejected, reference_only
IntegrationMode: undecided, native, adapter, service, reference_only, rejected
DecisionDisposition: integrate, adapt, replace, reference-only, reject
```

Required core signatures:

```python
class EcosystemCandidate(BaseModel): ...
class EcosystemManifest(BaseModel): ...
class CapabilityDefinition(BaseModel): ...
class CapabilityEdge(BaseModel): ...
class CapabilityGraph(BaseModel): ...
```

`EcosystemCandidate` fields:

```text
id: str
name: str
url: str
kind: CandidateKind
category: str
source_label: Optional[str]
capabilities: list[str]
status: CandidateStatus = discovered
integration_mode: IntegrationMode = undecided
license: Optional[str] = None
language: Optional[str] = None
maintenance: MaintenanceSignals
scores: CandidateScores
evidence: list[EvidenceRef]
last_reviewed_at: Optional[datetime] = None
```

`CapabilityDefinition` fields: `id`, `name`, `description`, `risk_level` where risk is one of `low`, `medium`, `high`, `privileged`.

`CapabilityEdge` fields: `candidate_id`, `capability_id`, `evidence` default empty list.

- [ ] **Step 4: Run model tests**

Run: `pytest tests/test_ecosystem_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add vortex/ecosystem/__init__.py vortex/ecosystem/models.py tests/test_ecosystem_models.py
git commit -m "feat: add ecosystem domain models"
```

---

### Task 2: Artifact loader, graph referential integrity, and schema snapshots

**Files:**
- Create: `vortex/ecosystem/loader.py`
- Create: `config/ecosystem/ecosystem_manifest.schema.json`
- Create: `config/ecosystem/capability_graph.schema.json`
- Test: `tests/test_ecosystem_loader.py`
- Test: `tests/test_ecosystem_artifacts.py`

**Interfaces:**
- Consumes: `EcosystemManifest`, `CapabilityGraph` from Task 1.
- Produces:

```python
def load_manifest(path: Path) -> EcosystemManifest: ...
def load_capability_graph(path: Path, *, manifest: EcosystemManifest) -> CapabilityGraph: ...
def validate_graph_references(graph: CapabilityGraph, manifest: EcosystemManifest) -> None: ...
```

- [ ] **Step 1: Write failing loader tests**

Create tests asserting:

```python
def test_load_manifest_rejects_malformed_json(tmp_path): ...
def test_load_manifest_rejects_schema_invalid_json(tmp_path): ...
def test_graph_rejects_unknown_candidate_reference(tmp_path): ...
def test_graph_rejects_unknown_capability_reference(tmp_path): ...
def test_schema_snapshots_match_pydantic_models(): ...
```

`load_manifest` must surface malformed JSON as a domain-facing `ValueError` whose message includes the source path; it must preserve the original exception as `__cause__`.

`validate_graph_references` must aggregate all unknown candidate IDs and capability IDs into one deterministic sorted error message rather than failing on the first edge.

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_ecosystem_loader.py tests/test_ecosystem_artifacts.py -q`
Expected: FAIL because loader/schema files do not exist.

- [ ] **Step 3: Implement loader and validation**

Use `json.loads(path.read_text(encoding="utf-8"))` followed by `model_validate`.

Do not fetch network metadata and do not mutate files while loading.

- [ ] **Step 4: Generate committed schema snapshots**

Generate JSON with:

```python
EcosystemManifest.model_json_schema()
CapabilityGraph.model_json_schema()
```

Write sorted, indented UTF-8 JSON with a final newline. The artifact test must compare parsed JSON structures, not whitespace.

- [ ] **Step 5: Run loader/artifact tests**

Run: `pytest tests/test_ecosystem_loader.py tests/test_ecosystem_artifacts.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add vortex/ecosystem/loader.py config/ecosystem tests/test_ecosystem_loader.py tests/test_ecosystem_artifacts.py
git commit -m "feat: validate ecosystem artifacts"
```

---

### Task 3: Bounded loop-cycle invariants

**Files:**
- Create: `vortex/ecosystem/cycle.py`
- Test: `tests/test_ecosystem_cycle.py`

**Interfaces:**
- Produces:

```python
class CycleBudget(BaseModel): ...
class CycleOutcome(BaseModel): ...
class DiscoveryPass(BaseModel): ...
def should_terminate_branch(passes: Sequence[DiscoveryPass]) -> bool: ...
```

- [ ] **Step 1: Write failing cycle tests**

Required tests:

```python
def test_cycle_budget_rejects_non_positive_numeric_budgets(): ...
def test_cycle_budget_requires_all_textual_budget_fields(): ...
def test_cycle_outcome_requires_at_least_one_qualifying_result(): ...
def test_discovery_does_not_terminate_after_two_no_improvement_passes(): ...
def test_discovery_terminates_after_three_consecutive_no_improvement_passes(): ...
def test_improvement_resets_consecutive_termination_window(): ...
```

`CycleBudget` fields:

```text
objective: non-empty str
capability_area: non-empty str
time_budget_minutes: positive int
token_budget: positive int
repository_budget: positive int
implementation_budget: non-empty str
verification_budget: non-empty str
success_metric: non-empty str
```

`CycleOutcome.qualifying_outcomes` is a non-empty set whose allowed values are exactly:

```text
integrated_production_code
removed_complexity
improved_benchmark
closed_security_issue
reduced_cost
improved_reliability
better_documented_architecture
rejected_or_replaced_component
```

`DiscoveryPass` fields: `pass_number: positive int`, `superior_implementation_found: bool`, `evidence: list[str]`.

`should_terminate_branch` returns `True` only when the final three passes all have `superior_implementation_found == False`.

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_ecosystem_cycle.py -q`
Expected: FAIL because cycle module does not exist.

- [ ] **Step 3: Implement cycle models/invariant**

Use Pydantic validators for non-empty strings and set cardinality. Keep the termination function pure and deterministic.

- [ ] **Step 4: Run cycle tests**

Run: `pytest tests/test_ecosystem_cycle.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add vortex/ecosystem/cycle.py tests/test_ecosystem_cycle.py vortex/ecosystem/__init__.py
git commit -m "feat: enforce bounded ecosystem cycles"
```

---

### Task 4: Seed the complete canonical inventory, capability taxonomy, and traceability logs

**Files:**
- Create: `ecosystem_manifest.json`
- Create: `capability_graph.json`
- Create: `decision_log.md`
- Create: `rejection_log.md`
- Create: `integration_log.md`
- Create: `benchmark_log.md`
- Create: `security_log.md`
- Create: `roadmap.md`
- Create: `tests/fixtures/ecosystem_expected_urls.txt`
- Modify: `tests/test_ecosystem_artifacts.py`

**Interfaces:**
- Consumes: loaders/models from Tasks 1-2.
- Produces: canonical seed state consumed by CLI and future evaluation cycles.

- [ ] **Step 1: Add failing seed-artifact acceptance tests**

Assertions:

```python
def test_seed_manifest_loads_and_contains_exact_approved_url_set(): ...
def test_every_seed_candidate_has_unique_stable_id(): ...
def test_non_repository_sources_are_not_marked_as_native_or_adapter_integrations(): ...
def test_seed_capability_graph_loads_against_manifest(): ...
def test_all_required_traceability_logs_exist(): ...
```

`ecosystem_expected_urls.txt` contains exactly one URL per line from Appendix A, in source order. The manifest test compares sets for equality and separately asserts `len(manifest.candidates) == len(expected_urls)` so duplicate URLs cannot hide missing records.

- [ ] **Step 2: Run acceptance tests and verify failure**

Run: `pytest tests/test_ecosystem_artifacts.py -q`
Expected: FAIL because canonical seed artifacts do not exist.

- [ ] **Step 3: Build `ecosystem_manifest.json`**

Rules:
- one candidate per unique Appendix A URL;
- preserve URL exactly;
- deterministic lowercase kebab/slash ID derived from the explicit project identity when known, otherwise from host/path; collisions receive a deterministic host/path suffix rather than a numeric random suffix;
- GitHub repository URLs use `kind="repository"`;
- `blockrun.ai`, DeFiLlama, Dune, and the Spraay gateway use `kind="website"`;
- npm package page uses `kind="package"`;
- Binance API docs use `kind="docs"`;
- `awesome.re/badge.svg`, `img.shields.io/...`, and `licensebuttons.net/...png` use `kind="badge_asset"`, `status="reference_only"`, `integration_mode="reference_only"`;
- all unverified metadata remains null/empty;
- do not infer licenses from badge text in this task;
- do not assign implementation scores.

- [ ] **Step 4: Build `capability_graph.json`**

Seed capability definitions for exactly these top-level domains:

```text
openclaw-runtime
agent-orchestration
memory-knowledge
browser-automation
mcp-tooling
quant-trading-research
crypto-defi-mev-research
prediction-market-research
scraping-lead-outreach
content-media-automation
workflow-automation
research-intelligence
market-data-analytics
```

Risk levels:
- `privileged`: quant-trading-research, crypto-defi-mev-research, prediction-market-research
- `high`: browser-automation, scraping-lead-outreach
- `medium`: openclaw-runtime, agent-orchestration, mcp-tooling, workflow-automation, content-media-automation
- `low`: memory-knowledge, research-intelligence, market-data-analytics

Only add an edge when the source label/category supplied by the user directly establishes the domain. Do not infer fine-grained capabilities yet.

- [ ] **Step 5: Initialize traceability logs**

Each log begins with purpose, append-only convention, record format, and Cycle 0 baseline. `roadmap.md` records Cycle 1 as the governance-substrate implementation and sets the next capability branch to OpenClaw/runtime evaluation after the substrate is green.

- [ ] **Step 6: Run seed-artifact tests**

Run: `pytest tests/test_ecosystem_artifacts.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add ecosystem_manifest.json capability_graph.json *_log.md roadmap.md tests/fixtures/ecosystem_expected_urls.txt tests/test_ecosystem_artifacts.py
git commit -m "feat: seed ecosystem registry and traceability logs"
```

---

### Task 5: Read-only ecosystem CLI

**Files:**
- Create: `vortex/cli/ecosystem.py`
- Modify: `vortex/cli/app.py` near existing Typer sub-app declarations/registrations.
- Test: `tests/test_ecosystem_cli.py`

**Interfaces:**
- Consumes: Task 2 loader functions and root canonical artifacts.
- Produces: Typer sub-app `ecosystem_app` with `validate`, `list`, and `show` commands.

- [ ] **Step 1: Write failing CLI tests using `typer.testing.CliRunner`**

Required tests:

```python
def test_ecosystem_validate_reports_valid_artifacts(): ...
def test_ecosystem_list_filters_category(): ...
def test_ecosystem_list_filters_status(): ...
def test_ecosystem_list_filters_kind(): ...
def test_ecosystem_show_returns_candidate_by_id(): ...
def test_ecosystem_show_unknown_id_exits_nonzero(): ...
def test_ecosystem_validate_invalid_manifest_exits_nonzero(tmp_path): ...
```

CLI contracts:

```text
vortex ecosystem validate --manifest PATH --graph PATH
vortex ecosystem list --manifest PATH [--category TEXT] [--status TEXT] [--kind TEXT]
vortex ecosystem show CANDIDATE_ID --manifest PATH
```

Defaults: manifest `ecosystem_manifest.json`, graph `capability_graph.json`.

Output must be deterministic JSON to stdout so it is scriptable. Errors go through Typer with a non-zero exit code and include the failing path or candidate ID.

- [ ] **Step 2: Run CLI tests and verify failure**

Run: `pytest tests/test_ecosystem_cli.py -q`
Expected: FAIL because `vortex.cli.ecosystem` is absent.

- [ ] **Step 3: Implement CLI sub-app**

Public object:

```python
ecosystem_app = typer.Typer(help="Inspect and validate ecosystem governance artifacts")
```

Keep file/network mutation out of all three commands.

- [ ] **Step 4: Register the sub-app**

In `vortex/cli/app.py`, import `ecosystem_app` and add:

```python
app.add_typer(ecosystem_app, name="ecosystem")
```

Do not add ecosystem state to `RuntimeContext`; these commands are file-backed and read-only.

- [ ] **Step 5: Run CLI tests**

Run: `pytest tests/test_ecosystem_cli.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add vortex/cli/ecosystem.py vortex/cli/app.py tests/test_ecosystem_cli.py
git commit -m "feat: add ecosystem governance CLI"
```

---

### Task 6: Regression, quality, and cycle accounting

**Files:**
- Modify: `benchmark_log.md`
- Modify: `security_log.md`
- Modify: `integration_log.md`
- Modify: `decision_log.md`
- Modify: `roadmap.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified Cycle 1 closeout evidence and next bounded target.

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest tests/test_ecosystem_models.py tests/test_ecosystem_loader.py tests/test_ecosystem_cycle.py tests/test_ecosystem_artifacts.py tests/test_ecosystem_cli.py -q
```

Expected: all PASS.

- [ ] **Step 2: Run project static checks**

Run:

```bash
black --check vortex tests
isort --check-only vortex tests
flake8 vortex tests
mypy vortex
```

Expected: exit code 0 for each. If the current base has pre-existing failures, record the exact baseline failure and prove no new ecosystem-file failure before proceeding; do not weaken configuration.

- [ ] **Step 3: Run full regression suite**

Run: `pytest`
Expected: all tests pass and total coverage remains >=90%. If base already fails independently, record exact command/output and run `git diff main...HEAD --` plus focused tests to isolate the new slice; do not claim globally green.

- [ ] **Step 4: Verify artifact determinism**

Run the CLI twice and compare output:

```bash
vortex ecosystem validate
vortex ecosystem list --category openclaw
```

Expected: identical output for identical files; no file mutations.

- [ ] **Step 5: Record Cycle 1 deltas**

Append exact evidence to logs:

```text
changed files
added components
removed components
benchmark delta
security delta
cost delta
reliability delta
remaining gaps
next loop target
commit SHA(s)
verification commands/results
```

Do not invent benchmark improvements. For this substrate cycle, expected measurable outcomes are `integrated_production_code`, `improved_reliability`, and `closed_security_issue` only if tests prove the corresponding invariant; otherwise record neutral/no measured delta.

- [ ] **Step 6: Commit closeout logs**

```bash
git add decision_log.md integration_log.md benchmark_log.md security_log.md roadmap.md
git commit -m "docs: close OMEGA governance substrate cycle"
```

- [ ] **Step 7: Compare branch to base**

Run:

```bash
git status --short
git diff --check main...HEAD
git diff --stat main...HEAD
```

Expected: clean working tree, `git diff --check` exit 0, only planned files changed.

---

## Appendix A — Authoritative seed URL inventory

The implementation must preserve every line below exactly in `tests/fixtures/ecosystem_expected_urls.txt` and exactly once in `ecosystem_manifest.json`.

```text
https://awesome.re/badge.svg
https://img.shields.io/github/stars/BlockRunAI/awesome-OpenClaw-Money-Maker?style=social
https://img.shields.io/badge/License-CC0_1.0-lightgrey.svg
https://github.com/openclaw/openclaw
https://github.com/BlockRunAI/ClawRouter
https://github.com/BlockRunAI/franklin
https://blockrun.ai
https://www.npmjs.com/package/@blockrun/franklin
https://github.com/freqtrade/freqtrade
https://github.com/hummingbot/hummingbot
https://github.com/AI4Finance-Foundation/FinRL
https://github.com/jesse-ai/jesse
https://github.com/Superalgos/Superalgos
https://github.com/Drakkar-Software/OctoBot
https://github.com/Open-Trader/opentrader
https://github.com/ctubio/Krypto-trading-bot
https://github.com/Haehnchen/crypto-trading-bot
https://github.com/nMaroulis/sibyl
https://github.com/OpenBB-finance/OpenBB
https://github.com/goat-sdk/goat
https://github.com/wfnuser/OpenNof1
https://github.com/Degenapetrader/EVClaw
https://github.com/195440/nof1.ai
https://github.com/Gajesh2007/ai-trading-agent
https://github.com/luffycodes/AgentTrade
https://github.com/TraderAlice/OpenAlice
https://github.com/virattt/dexter
https://github.com/TradingAgents-AI/TradingAgents
https://github.com/warp-id/solana-trading-bot
https://github.com/ChainBuff/open-sol-bot
https://github.com/henrytirla/Solana-Trading-Bot
https://github.com/radioman/Auto-solana-trading-bot
https://github.com/0xRustPro/solana-grpc-sniper-bundler-bot
https://github.com/paradigmxyz/artemis
https://github.com/jito-labs/mev-bot
https://github.com/degatchi/mev-template-rs
https://github.com/sOLarFLaMEPyL/Arbitrage_Mev_BOT
https://github.com/solidquant/mev-templates
https://github.com/SaoXuan/rust-mev-bot-shared
https://github.com/sambacha/q-evm
https://github.com/sorasuzukidev/ethereum-bnb-mev-bot
https://github.com/dexloom/loom
https://github.com/ExtropyIO/defi-bot
https://github.com/Polymarket/agents
https://github.com/Jon-Becker/prediction-market-analysis
https://github.com/warproxxx/poly-maker
https://github.com/RandyTas/polymarket-copytrading-bot
https://github.com/Polymarket/py-clob-client
https://github.com/yorkeccak/Polyseer
https://github.com/warproxxx/poly_data
https://github.com/pmxt-dev/pmxt
https://github.com/FrondEnt/PolymarketBTC15mAssistant
https://github.com/humanplane/cross-market-state-fusion
https://github.com/JerriyaAnderson/polymarket-copy-bot-ts
https://github.com/CraftyGeezer/Kalshi-Polymarket-Ai-bot
https://github.com/Polymarket/rs-clob-client
https://github.com/Daniel-Dias001/Polymarket-rsi-macd-index-trading-bot
https://github.com/Polymarket/clob-client
https://github.com/Trust412/Polymarket-spike-bot-v1
https://github.com/CarlosIbCu/polymarket-kalshi-btc-arbitrage-bot
https://github.com/realfishsam/prediction-market-arbitrage-bot
https://github.com/aarora4/Awesome-Prediction-Market-Tools
https://github.com/therumpshakingaction/DeFi-Yield-AutoFarming
https://github.com/corbinpage/yield-farmers-almanac
https://github.com/BankrBot/openclaw-skills
https://github.com/masterking32/MasterCryptoFarmBot
https://github.com/fabston/Telegram-Airdrop-Bot
https://github.com/dante4rt/t3rn-airdrop-bot
https://github.com/dante4rt/blum-airdrop-bot
https://github.com/dante4rt/nodepay-airdrop-bot
https://github.com/dante4rt/polyflow-airdrop-bot
https://github.com/eracle/OpenOutreach
https://github.com/linvo-io/linvo-scraper
https://github.com/ScrapeGraphAI/Scrapegraph-ai
https://github.com/brightdata/ai-lead-generator
https://github.com/kaymen99/ai-web-scraper
https://github.com/filip-michalsky/SalesGPT
https://github.com/omkarcloud/google-maps-scraper
https://github.com/oxylabs/chatgpt-scraper
https://github.com/harry0703/MoneyPrinterTurbo
https://github.com/FujiwaraChoki/MoneyPrinterV2
https://github.com/THUDM/CogVideo
https://github.com/all-in-aigc/sorafm
https://github.com/IgorShadurin/app.yumcut.com
https://github.com/davide97l/ai-video-generator
https://github.com/ChaituRajSagar/gemini-youtube-automation
https://github.com/darkzOGx/youtube-automation-agent
https://github.com/PatrykIA/Auto_Social_Media_Content_Generator
https://github.com/AJaySi/ALwrity
https://github.com/Shubhamsaboo/awesome-llm-apps
https://github.com/google-gemini/gemini-cli
https://github.com/Significant-Gravitas/AutoGPT
https://github.com/geekan/MetaGPT
https://github.com/openinterpreter/open-interpreter
https://github.com/Mintplex-Labs/anything-llm
https://github.com/microsoft/autogen
https://github.com/microsoft/ai-agents-for-beginners
https://github.com/FlowiseAI/Flowise
https://github.com/mem0ai/mem0
https://github.com/crewAIInc/crewAI
https://github.com/ToolJet/ToolJet
https://github.com/reworkd/AgentGPT
https://github.com/block/goose
https://github.com/langchain-ai/langchain
https://github.com/run-llama/llama_index
https://github.com/huggingface/smolagents
https://github.com/TransformerOptimus/SuperAGI
https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk
https://github.com/bytedance/UI-TARS-desktop
https://github.com/ComposioHQ/composio
https://github.com/simstudioai/sim
https://github.com/warpdotdev/Warp
https://github.com/getzep/graphiti
https://github.com/RooCodeInc/Roo-Code
https://github.com/activepieces/activepieces
https://github.com/NirDiamant/GenAI_Agents
https://github.com/coze-dev/coze-studio
https://github.com/kortix-ai/suna
https://github.com/QwenLM/qwen-code
https://github.com/elizaOS/eliza
https://github.com/QwenLM/Qwen-Agent
https://github.com/VoltAgent/voltagent
https://github.com/MervinPraison/PraisonAI
https://github.com/HKUDS/ClawWork
https://github.com/HKUDS/nanobot
https://github.com/qwibitai/nanoclaw
https://github.com/NevaMind-AI/memU
https://github.com/iOfficeAI/AionUi
https://github.com/AgentOps-AI/agentops
https://github.com/pydantic/pydantic-ai
https://github.com/CherryHQ/cherry-studio
https://github.com/Fosowl/agenticSeek
https://github.com/openai/openai-agents-python
https://github.com/eosphoros-ai/DB-GPT
https://github.com/plandex-ai/plandex
https://github.com/opencode-ai/opencode
https://github.com/microsoft/agent-framework
https://gateway.spraay.app
https://github.com/ValueCell-ai/ClawX
https://github.com/tugcantopaloglu/openclaw-dashboard
https://github.com/bfzli/clawhost
https://github.com/qingchencloud/clawapp
https://github.com/SeyZ/clawbands
https://github.com/openclaw-rocks/k8s-operator
https://github.com/Enriquefft/openclaw-kapso-whatsapp
https://github.com/vivekchand/clawmetry
https://github.com/serithemage/serverless-openclaw
https://github.com/nickzsche21/AirClaw
https://github.com/browser-use/browser-use
https://github.com/browserbase/stagehand
https://github.com/Skyvern-AI/skyvern
https://github.com/lavague-ai/LaVague
https://github.com/showlab/ShowUI
https://github.com/VoltAgent/awesome-openclaw-skills
https://github.com/openclaw/clawhub
https://github.com/clawdbot-ai/awesome-openclaw-skills-zh
https://github.com/sundial-org/awesome-openclaw-skills
https://github.com/zscole/model-hierarchy-skill
https://github.com/ythx-101/x-tweet-fetcher
https://github.com/sharbelxyz/x-bookmarks
https://github.com/BlockRunAI/socialclaw
https://github.com/solcanine/openclaw-ai-polymarket-trading-bot
https://github.com/team-telnyx/clawdtalk-client
https://github.com/makafeli/n8n-workflow-builder
https://github.com/haunchen/n8n-skills
https://github.com/DINAKAR-S/N8N-Workflows
https://github.com/lucaswalter/n8n-ai-automations
https://github.com/simealdana/ai-automation-jsons
https://github.com/punkpeye/awesome-mcp-servers
https://github.com/upstash/context7
https://github.com/jlowin/fastmcp
https://github.com/mcp-use/mcp-use
https://github.com/BlockRunAI/blockrun-mcp
https://github.com/BlockRunAI/blockrun-mcp-server
https://github.com/mindsdb/mindsdb
https://github.com/github/github-mcp-server
https://github.com/googleapis/genai-toolbox
https://github.com/idosal/git-mcp
https://github.com/microsoft/playwright-mcp
https://github.com/hangwin/mcp-chrome
https://github.com/GLips/Figma-Context-MCP
https://github.com/0x4m4/hexstrike-ai
https://github.com/oraios/serena
https://github.com/assafelovic/gpt-researcher
https://github.com/BlockRunAI/awesome-blockrun
https://github.com/e2b-dev/awesome-ai-agents
https://github.com/ashishpatel26/500-AI-Agents-Projects
https://github.com/slavakurilyak/awesome-ai-agents
https://github.com/jim-schwoebel/awesome_ai_agents
https://github.com/garylab/MakeMoneyWithAI
https://github.com/rembertdesigns/AI-Agent-Platforms-Automation-Tools
https://github.com/hesamsheikh/awesome-openclaw-usecases
https://github.com/AlexAnys/awesome-openclaw-usecases-zh
https://github.com/BlockRunAI/blockrun-llm
https://github.com/BlockRunAI/blockrun-llm-ts
https://github.com/BlockRunAI/blockrun-llm-go
https://github.com/BlockRunAI/blockrun-llm-xrpl
https://defillama.com/
https://dune.com/
https://binance-docs.github.io/apidocs/
https://licensebuttons.net/p/zero/1.0/88x31.png
```

## Self-Review Result

- **Spec coverage:** The first implementation slice in spec §13 is covered: typed schema/loader (Tasks 1-2), complete manifest and graph (Task 4), loop-cycle validation (Task 3), read-only CLI (Task 5), required logs/roadmap (Task 4), full verification (Task 6).
- **Step scan:** Every implementation task follows failing test -> implementation -> passing test -> commit. No upstream integration is smuggled into this plan.
- **Type consistency:** `EcosystemManifest` and `CapabilityGraph` originate in Task 1; Task 2 exposes loaders; Tasks 4-5 consume those exact interfaces.
- **Review Focus:** All five high-risk input/failure classes have explicit tests in Tasks 1-5.
- **Proportion:** The plan is longer than the narrow code slice primarily because Appendix A carries the authoritative source inventory required for deterministic implementation; executable code is not transcribed.
