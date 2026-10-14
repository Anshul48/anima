**Hardware participation and research acceleration — proposed roadmap, 2026-10-03**

**User direction**

The programme operates across timescales and levels of organization. TRACE has its own operating world, participates in a broader cognitive architecture, and that architecture belongs within hardware/software co-design. Coordinators and architects should make progress on their current assignments while the broader programme deliberately prepares and enters hardware research.

A → C → B → D remains the relative priority map. It does not require completing A, C, B, TRACE, STC, or the whole substrate before beginning hardware work. Hardware competence and preparation can start now. Concrete hardware experiments should begin once a small useful software path can accelerate them, while the larger system continues developing. Many further steps may precede mature physical co-design.

The user also proposes competent hardware engineers and robots as participants in accelerating physical research, especially outside software. Attention, context capacity, fatigue, and other human constraints should be included when allocating work.

This document proposes sequencing and entry criteria. It does not select hardware purchases, recruit anyone, launch robotic operations, or assign new coordinator tasks.

**Overlapping horizons**

| Horizon | Main work | Connection to the other horizons |
|---|---|---|
| Current delivery | Continue TRACE/TL obligations, STC/SST development, usable execution and feedback, selected substrate transitions | Provide useful tools, records, and real workloads |
| Near-term hardware entry | Build task-linked hardware competence, define a first prototype, establish measurement and an engineer-reviewed experimental path | Expose physical and implementation constraints before software architecture becomes unnecessarily rigid |
| Physical research acceleration | Combine engineering judgment, simulation, instruments, test fixtures, and robotic operations where justified | Produce evidence and reusable procedures from work outside software |
| Deeper co-design | Revise computational representations and organization together with physical implementation | Investigate new primitives, locality, learning dynamics, reconfiguration, and integration |

These are concurrent programmes with dependencies, not a mandatory sequence of completed products. Each programme can contain its own delivery and research worlds.

**Smallest useful software foundation**

The entry criterion is a repeatable experimental path:

`question/specification → candidate design → execute or simulate → measure/check → retain evidence → select the next action`

It should carry identified designs, tasks, configurations and versions; a baseline and outcome criteria; execution tools or instrument adapters; results, failures and costs; and recoverable experiment state appropriate to the activity.

Existing tools, scripts, and supervised operation can establish this path. It need not wait for a universal world API, complete memory system, polished workspace, autonomous learner, or full hardware automation. Later substrate work can consolidate the useful path.

For physical experiments, declared methods and device state matter alongside files and code. A model's predicted result is distinct from simulation output, and both are distinct from a measured physical result. Retain these distinctions when learning from episodes.

**Hardware competence through work**

Choose an initial hardware area from a real research question and the resources available. Develop depth there while maintaining a map of adjacent fields. Avoid making mastery of all hardware a prerequisite to useful participation.

Relevant foundations include digital architecture and timing; memory and communication; embedded control and interfaces; simulation, verification, and measurement; and power, thermal, signal, and physical constraints where they affect the chosen experiment.

The user's strategic competence and the team's implementation competence are distinct needs. Expert collaboration can accelerate both. The user should be able to frame the research question, assess evidence and tradeoffs, and challenge key assumptions; qualified engineers can provide depth in detailed design, calibration, debugging, and physical implementation.

A first task may favour a programmable accelerator, an embedded prototype, an instrumented electronic subsystem, or a laboratory test fixture. Select it by the mechanism to investigate rather than by a biological analogy or a technology ladder.

AMD's documented HLS workflow provides one example of moving a C/C++ function into RTL with simulation and architecture exploration. It is an available kind of entry path, not a selected vendor or proof that hardware acceleration benefits our workload. [Vitis HLS](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/vitis/vitis-hls.html)

**First entry packets**

Prepare a small number of hardware experiment proposals. Each should identify:

- The cognitive or research bottleneck and its current evidence.
- The specific physical or implementation mechanism that could help.
- A software baseline, simulation plan, and physical measurement path.
- Required engineering expertise, equipment access, integration effort, and expected costs.
- A result that would justify continuing, and one that would redirect the work.

Possible starting questions include whether local state and event updates improve a useful computation; whether representation and precision choices change achievable cost/quality; or whether an instrumented fixture materially increases experimental throughput. These are examples, not chosen tasks.

Measure complete operations: host/device communication, conversion, memory, setup, measurement, failure handling, and engineering/human effort. An isolated kernel or robot cycle time does not establish end-to-end research acceleration. Vendor profiling tools can expose host and device activity; assessment still belongs to the chosen experimental question. [AMD profiling documentation](https://docs.amd.com/r/en-US/ug1700-vitis-accelerated-data-center/Profiling-the-Application)

**Two physical workstreams**

Computational hardware co-design and automation of physical research can reinforce one another, but neither is a prerequisite for the other.

For computational hardware, start with a task-linked prototype and revise software representations or operations alongside placement, data movement, precision, scheduling, or circuit structure. Hardware requirements should feed back into architecture early, rather than appear only as late implementation details.

For physical research acceleration, begin with the operations that consume time or constrain throughput: instrument control, repeatable measurements, parameter sweeps, sample or component handling, assembly/test routines, and retained evidence. Some operations may need scripts or fixtures; others may warrant robots. Engineer and domain-expert judgment establish useful methods and interpret anomalies.

Robotic experimentation has bounded precedents. A mobile robotic chemistry study reported 688 experiments over eight days within a ten-variable search space. This supports investigating automated physical loops; it does not establish general hardware fabrication or unrestricted laboratory competence. [A mobile robotic chemist](https://www.nature.com/articles/s41586-020-2442-2)

Account for setup, calibration, maintenance, consumables, failed attempts, and expert intervention. Physical results require their actual measurement and assessment rather than being accepted because an autonomous system produced them.

**Roles in the broader system**

| Participant | Proposed role |
|---|---|
| User | Direction, consequential synthesis, research priorities, and architectural judgment |
| Architects/coordinators | Maintain local plans and interfaces, resolve ordinary work, and prepare consequential choices |
| Hardware/domain engineers | Design and review experiments, implement prototypes, establish measurements, and investigate physical anomalies |
| Software/model workers | Literature and design assistance, simulation, code/firmware, test generation, data processing, and attributable procedure learning |
| Instruments/robots | Perform specified physical operations and report observed status/results within an assessed operating envelope |
| Memory/substrate capabilities | Preserve evidence, uncertainty, revisions, lessons, ownership, and cross-world cooperation |

These are functional roles that can cooperate and later form composites. Hardware engineering should not automatically become the user's next individual implementation backlog. Hiring, equipment, and laboratory access decisions require concrete proposals when they become relevant; no such commitments have been made here.

**Attention and human capacity as system resources**

Keep resource estimates multidimensional. Relevant costs include money, elapsed time, compute/energy, physical throughput, engineering labour, maintenance, and the user's attention. The same action can consume little compute and substantial human review effort, or save human effort while making a physical resource the new bottleneck.

Useful observations include decision count, review time, context-reconstruction effort, interruptions, ambiguous handoffs, rework, and optional reports of fatigue or readiness. Estimate state-dependent capacity with uncertainty and update it from experience. A workload model need not pretend to be a precise physiological model or collect biometric data.

The allocation policy should:

- Preserve substantial early user control and time for synthesis.
- Resolve routine work within settled scope and prepare consequential decisions with evidence and alternatives.
- Batch independent decisions where doing so helps, while escalating a time-critical dependency promptly.
- Preserve context so re-entry into a programme requires little reconstruction.
- Delegate detailed implementation to competent participants rather than turning supervision into continuous micromanagement.
- Count coordination and measurement overhead when judging whether the optimization helped.

Attention is also a productive contribution. Optimize capability and research progress under sustainable constraints, with the user's control and preferences intact, rather than minimizing user participation indiscriminately.

**Immediate roadmap outputs**

The next architecture decision packet should include the minimal software path to support hardware experiments, the seams for physical execution and measured feedback, and which decisions benefit from early engineer input. Prepare candidate entry experiments alongside that packet. Software delivery continues while those choices are developed.

After an entry experiment is selected, build task-linked competence and the smallest relevant prototype with appropriate expertise. Use its evidence to choose the next hardware and automation steps. Deeper neuromorphic, reconfigurable, in-memory, or custom physical approaches remain candidate branches whose relevance depends on the mechanism being investigated.

No calendar, numeric experiment allowance, staffing arrangement, equipment list, or claim of hardware readiness is established by this roadmap.
