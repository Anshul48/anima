# Reflex: Autonomous Predictive Computer-Use Architecture

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

> **Status and precedence:** This is an early research/seed architecture note.
> The current build authority is SUBAGENT_GLOBAL_CONTEXT.md and the
> docs/subagents planning package. Specific model names, latency figures, and
> complexity claims below are candidate hypotheses to measure, not dependencies
> or release commitments. Trace integration remains blocked until its actual
> API/SDK/CLI is supplied.

## System Overview

Reflex is a high-speed, predictive OS and web agent designed to operate at sub-15ms motor loop latency. It compiles slow System-2 reasoning into fast System-1 motor reflexes stored in a high-dimensional episodic and motor memory.

---

## Key Principles

### 1. Dual Visual Stream Processing
- **Dorsal Stream (Where/How)**: Fast, geometry-first spatial affordance (`YOLOv11-UI` / `SegFormer`). Operates colorblind and detail-blind in <15ms to yield `BoundingBox` and `NodeRole`.
- **Ventral Stream (What)**: Slow, semantic grounding (`RapidOCR` / `Surya` / `Accessibility Tree`). Extracts labels and text strings to bind semantic identity to spatial bounding boxes.

### 2. Active Inference & Saccadic Suppression
- Instead of re-embedding full screenshots on every frame, Reflex maintains a cached visual state $\hat{S}_t$.
- Frame $t$ is diffed against Frame $t-1$. Pixels outside the changed bounding boxes are suppressed.
- Only modified crops are passed down the fallback ladder.

### 3. $O(N^2) \to O(N)$ Crop-and-Route Bottleneck Bypass
- Vision Transformers (ViTs) scale quadratically $O(N^2)$ with image pixel area $N$.
- High-level VLMs (Holo 3.1 9B / Gemini) are NEVER fed full screenshots.
- Native-resolution image crops of bounding boxes ($K$ elements of fixed size $C$) are packaged into `CropPacket` objects.
- For bounded crop count and crop size, visual-token cost can be bounded around selected regions; actual end-to-end latency and complexity depend on detector cost, crop count, routing, and model behavior and must be benchmarked.

---

## Data Model & Interfaces

See STIGMERGY_CONTEXT.md (historical record `relfex/STIGMERGY_CONTEXT.md`, excluded from this public release) and Python schemas in [src/reflex/schemas/](src/reflex/schemas/).

```
Transition Tuple:
⟨ S_t (UIState), A_t (TypedAction), S_{t+1} (UIState), ∆S (StateDelta), Surprise (float), Outcome (OutcomeClass) ⟩
```

---

## Test Verification

Run all unit tests:
```powershell
$env:PYTHONPATH="src"; python -m unittest discover -s tests
```
