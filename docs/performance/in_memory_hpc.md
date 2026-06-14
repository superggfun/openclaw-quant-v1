# In‑Memory / HPC Data Layer

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  SQLitePriceStore                                       │
│  · Persistent source of truth                           │
│  · All price history lives here                         │
│  · Used by: serial_reference, sqlite_bulk, CLI import   │
└──────────────┬──────────────────────────────────────────┘
               │  bulk read via get_price_history_many()
               ▼
┌─────────────────────────────────────────────────────────┐
│  InMemoryResearchDataStore  (research high-speed layer) │
│  · Transient in-memory DataFrame cache                  │
│  · Populated from SQLite on first access                │
│  · Workers > 1 on Linux/WSL → COW fork (cow_memory)    │
│  · Workers = 1 or Windows/spawn → single_process_memory │
└─────────────────────────────────────────────────────────┘
```

## Provider Selection

| Condition | Provider Type | Strategy |
|-----------|--------------|----------|
| `prefer_in_memory=False` | `sqlite` | `sqlite_bulk_single_process` |
| `prefer_in_memory=True`, workers=1 | `in_memory` | `single_process_memory` |
| `prefer_in_memory=True`, workers>1, Linux/WSL fork | `cow_memory` | `fork_cow_readonly` |
| `prefer_in_memory=True`, workers>1, Windows/spawn | `in_memory` | `single_process_memory` (fallback) |

## Platform Behaviour

### Linux / WSL (fork)
- Workers > 1 → uses `fork` multiprocessing start method
- Parent preloads price data into module‑level cache
- Child processes inherit via **COW (Copy‑on‑Write)** — zero copy cost
- Each child reads price data from shared physical memory pages
- Provider type: `cow_memory`, strategy: `fork_cow_readonly`

### Windows (spawn)
- Only `spawn` start method is available
- Multiprocessing would require pickling the full data cache → impractical for large datasets
- Workers > 1 with `prefer_in_memory=True` degrades to **single‑process in‑memory**
- Pickle‑free path is planned via **memmap / shared_memory** (future)

## Benchmarking

### Smoke (CI / quick check)
```
python scripts/benchmark_hpc.py smoke
```
- 50 symbols × 250 days × 1 factor
- Output: `reports/performance/hpc_benchmark_smoke.{json,md}`

### Real (full comparison)
```
python scripts/benchmark_hpc.py real                     # default: serial only on first factor
python scripts/benchmark_hpc.py real --serial-mode all   # serial on every factor
python scripts/benchmark_hpc.py real --serial-mode none  # skip serial entirely
```
- 200 symbols × 500 days × N factors (default 5, override via `HPC_BENCH_FACTORS`)
- Compares: serial_reference, sqlite_bulk, in_memory_bulk_1w/4w/8w
- Output: `reports/performance/hpc_benchmark_real.{json,md}`
- Incremental partial: `hpc_benchmark_real_partial.json` (survives SIGKILL)

### Roles

| Path | Purpose |
|------|---------|
| `serial_reference` | Correctness baseline only — not for production |
| `sqlite_bulk` | Production path without in‑memory layer |
| `in_memory_bulk_*` | Production path with in‑memory cache |

- Speedup is computed **only** when a serial_reference row exists for that factor.
- IC consistency is checked with strict tolerance **1e‑12** against serial_reference.

### Key Findings (200 symbols × 500 days)

- sqlite_bulk achieves **18×** speedup over serial_reference (median)
- in_memory_bulk_8w achieves **20×** (marginal gain over sqlite_bulk)
- in_memory_bulk_1w / 4w / 8w differ by ~0.1–0.5s — **worker count is not the bottleneck at this scale**
- The dominant speedup comes from **bulk matrix vectorisation**, not multi‑process parallelism
- Multi‑process gains expected at ≥500 symbols, ≥1000 days

## Future

- **memmap**: zero‑copy shared memory across processes without fork requirement
- **shared_memory (Python 3.8+)**: explicit `multiprocessing.shared_memory` for Windows spawn
- Both are part of the FactorPhaseConfig flags (`memmap`, `shared_memory`)
- Will enable true multi‑process speedup on Windows and larger Linux datasets

## Files

| File | Role |
|------|------|
| `quant/factor_acceleration/price_factor_kernels.py` | Pure price factor computation (shared by Builder + Provider) |
| `quant/factor_acceleration/factor_matrix_builder.py` | Builds factor/value/future‑return matrices |
| `quant/factor_acceleration/in_memory_provider.py` | In‑memory price provider with COW cache |
| `scripts/benchmark_hpc.py` | Standalone benchmark runner |
| `reports/performance/` | Benchmark outputs |
