# Reflex: User Intent & Architectural Ambition

> "Reflex is meant to work alongside LLMs as their eyes / System 1 vision and perception."

> "Does Reflex use OCR engines and etc like YOLO too? For harder tasks it can use a ladder of escalation, if things fail it calls a VLM (like H-Company Holo / Holo 4; we can test it later ig; or test cloud with a cheap VLM). But here's the catch: it doesn't send the entire page to the VLM. It uses YOLO or others to extract the bounded boxes, cheaply classify if they're relevant, and only sends those parts to the VLM, perhaps with a cheaply generated description and question. Turning O(N*N) to O(N) right? We have cheap models like typesafe JEV which can act as the cheap decision body for escalation, etc., although deep research cycles are needed to decide JEV's true and correct use."

## Architectural Summary
- **Role**: System 1 sensory/perceptual foundation for System 2 LLMs.
- **Ladder of Escalation**: DOM/Cache (L0/L1) -> YOLO + OCR (L2) -> Feature Grounding (L3) -> Targeted VLM (L4/L5).
- **O(N) Crop & Route**: Never send full-screen frames to high-level VLMs. Use YOLO/OCR to isolate bounding boxes, filter relevance cheaply, and route only localized high-resolution crops (`CropPacket`) to turn full-frame visual attention from O(N^2) into O(N) linear processing.
- **Decision & Gating Body**: Research lightweight, typesafe models (such as JEV) to serve as deterministic, low-latency arbitration engines governing when and where to escalate.
