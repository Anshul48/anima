# Physical development and embodied collaborators

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

**Status:** architecture and research proposal, 2026-10-05. This dossier selects no body, actuator, hardware platform, purchase, staffing arrangement, or experiment. It concerns the construction ecosystem and its research questions; product implementation remains outside this round.

## What this round adds

The current [substrate brief](../../../context/tracks/SUBSTRATE.md) already includes physical participants and organizational transformation. The [hardware roadmap](../../../../../components/substrate/docs/HARDWARE-AND-RESEARCH-ACCELERATION.md) already allows hardware preparation alongside software delivery, with specialists realizing designs while the user concentrates on direction and consequential judgment. Neither document establishes hardware readiness.

The new emphasis is more concrete: develop a hardware analogue of ANIMA/STC; investigate capable hands as the first demanding body function; start biomimetic morphology and artificial-muscle research now; and eventually support embodied workplace collaborators. These are connected ambitions with separate evidence requirements. Cooking supplies demanding examples rather than the programme boundary. Mobility is desirable without selecting bipedal locomotion.

The construction ecosystem must help capable people and systems turn conceptual architecture into physical realizations. That is broader than a simulator, component catalogue, agent roster, or robot control stack. Its useful outcome would be reliable engineering progress with retained knowledge and less repetitive reconstruction or user micromanagement. Existing mechanisms should supply the foundation where useful; a universal substrate is not an entry prerequisite.

## Proposed development machinery

A reusable development loop would connect requirements, candidate designs, simulation, engineering realization, measurement, and selected revisions. Its records should preserve design lineage, actual configurations, assumptions, failures, interventions, and costs. Software and hardware specialists could form temporary or persistent teams around a subsystem, later transferring responsibility or inheriting usable results.

The user supplies conceptual architecture, research priorities, and judgment over consequential alternatives. Engineers supply manufacturing, electrical, mechanical, controls, and measurement competence. Models and tools assist with literature, candidate generation, simulation, firmware, analysis, and evidence organization. Delegation must be assessed against total engineering effort and delivered capability, including the effort shifted to specialists.

There is pertinent prior art. MYOROBOTICS describes engineered bones, muscles, and joints with standardized connections, accompanied by design, simulation, and operation tools. Its implementation includes a motor-driven tendon with series elasticity. This supports investigating existing primitives and development tools. It establishes neither a general autonomous engineering ecosystem nor artificial-muscle superiority. [MYOROBOTICS overview](https://publica-rest.fraunhofer.de/server/api/core/bitstreams/b94d38c6-ecc2-40e9-8938-73b798f431a4/content), [implementation and neural-control study](https://mediatum.ub.tum.de/doc/1521948/k5vwk50oc5jzklg9fdxv1x0o2.ScalabilityInNeural.pdf)

The proposed reusable unit is an evidence-bearing realization: a design together with compatible control, sensing, calibration, manufacturing assumptions, and measured limits. Its engineering package could include CAD/drawings, a bill of materials, firmware, assembly instructions, and test procedures, with expert ownership and revision history. A component library alone loses the knowledge explaining where a component worked. Reuse may mean assembling unchanged parts, adapting a subsystem, or transforming several parts and their responsibilities together. Those outcomes should remain distinguishable.

## Where abstraction helps and where it conceals co-design

Keep morphology, transmission, force generation, sensing, and control distinguishable so competing hypotheses can be studied. Distinguishability does not imply physical independence. Changing tendon routing alters joint leverage and friction; changing stiffness affects sensing and controller bandwidth; changing force generation can alter packaging, cooling, power delivery, and attainable motion.

A boundary that exposes only target position and achieved position can conceal the mechanism under investigation. Equally, an actuator model that treats every candidate as an ideal force source can erase the benefits and penalties of muscle-like actuation. The architecture should expose the properties relevant to the current question while permitting coupled revisions.

Stable high-level obligations can reduce disruptive rewrites without freezing internal machinery. For example, retain task evidence and experiment identity while revising the hand, tendon arrangement, sensing, and controller together. Compatibility should be a supported relationship between particular versions and conditions. It should not be inferred from matching interface names.

Morphological computation is a hypothesis about useful work performed by body dynamics, compliance, and geometry. It earns support when those properties improve task capability, robustness, energy, or controller demands. Complexity moved into difficult fabrication or calibration still counts as system cost. Biological resemblance alone provides no such evidence.

## Software worlds and physical artifacts

A software world can often be copied, branched, replayed, or restored cheaply. A physical artifact has a particular location, wear history, calibration, material condition, and finite availability. Two specimens made from the same design can differ. A simulation branch does not create another physical specimen.

Physical operations can consume material, deform parts, contaminate surfaces, or change the surroundings. Restoring a software checkpoint cannot reverse those changes. Consequently the development system must represent restoration capabilities and artifact state explicitly, including uncertainty about what actually happened.

Design versions, physical instances, simulations, controller versions, and measurements need linked but distinct identities. Measured evidence belongs to an actual configuration under stated conditions. A digital twin is an estimate of an artifact and environment. Disagreement between model and measurement is evidence that should survive subsequent revisions.

Organizational transformation remains relevant: teams can merge responsibilities, subsystems can be redesigned, and successful design knowledge can be inherited. Physical fusion, replacement, and reuse nevertheless incur material and engineering consequences. Software coordination semantics cannot simply be carried over and assumed to govern those consequences adequately.

## Simulation and biological actuation

Simulation can explore workspace, tendon leverage, approximate contact, compliance, actuator limits, and controller interactions. MuJoCo explicitly separates transmission, activation dynamics, and force generation, and supports tendon forces and abstract muscle activation. That provides an existing mechanism for useful biological surrogates without microscopic biological simulation. [MuJoCo actuation documentation](https://mujoco.readthedocs.io/en/stable/computation/index.html#actuation-model)

The proposed fidelity policy is question-dependent. Begin with tractable geometry and actuator/contact models; refine deformation, thermal, or material behavior where it changes rankings or failure predictions. Calibrate uncertain parameters and test sensitivity. A biological muscle model can explore a desired principle but does not automatically represent the artificial actuator intended to realize it. Manipulation success in that model also cannot establish cooking-process quality or useful human interaction.

Dynamics randomization has demonstrated transfer for a bounded robotic manipulation task. That supports investigating robustness to modeled uncertainty; it does not establish transfer for arbitrary contacts, embodiments, or workplaces. [Dynamics-randomization experiment](https://arxiv.org/abs/1710.06537)

A musculoskeletal humanoid study reports incomplete correspondence between its learned body model and actual robot, then investigates learning a direct task controller for pedal operation. This supports keeping learned surrogates and physical feedback in view. It also exposes a real modeling limitation rather than establishing general workplace competence. The paper was accepted at IROS 2019 and uploaded to arXiv in 2024. [Task-specific controller study](https://arxiv.org/abs/2412.08270)

Artificial muscles deserve a parallel research branch. HASEL work reports electrically driven soft actuation, delicate grasping, and a robotic-arm demonstration; a later toolkit provides fabrication and untethered-drive approaches using high-voltage electronics. These are bounded device results. Suitability for capable hands depends on installed power delivery, force–stroke–speed behavior, controllability, cycle life, packaging, and maintenance. [HASEL experiments](https://is.mpg.de/rm/en/publications/keplinger18-s-hydraulically), [fabrication toolkit](https://is.mpg.de/rm/publications/keplinger19-as-softrobots)

Tendons are transmissions, whereas an artificial muscle supplies force through a particular energy-conversion mechanism. Motor-driven tendons can be a comparison baseline or bootstrap if needed. They should not silently become the selected permanent design. Conversely, commitment to a biological analogy should not suppress an alternative that better realizes the desired property.

## Strongest counterarguments

The ecosystem could become another coordination layer without materially improving engineering. Its claimed benefit must survive comparison with competent engineers using ordinary design tools and records. Reduced user involvement is insufficient if total intervention, rework, or verification costs increase.

Hands are an especially demanding entry function: grasping, dexterity, tactile inference, contact recovery, and tool use can expose different limitations. A successful grasp demonstration could mask weak manipulation. A broad task distribution could also become an unbounded ambition. Research therefore needs bounded questions while preserving transfer beyond cooking.

Softness and redundancy can enable desirable behavior while complicating precision, modeling, and maintenance. The useful properties must be isolated experimentally or analytically. Task-linked constraints such as cleaning, heat, fluids, and tool forces may change an otherwise attractive design. A motor–tendon result does not settle the case for electrohydraulic or other artificial muscles.

Simulation could reward exploitative designs or controllers that exploit model errors. Candidate-ranking stability across plausible models matters alongside simulated task success. Manufacturing repeatability, installed efficiency, wear, and reliable workplace operation ultimately require physical evidence.

Finally, understanding a business and improving it is a further capability beyond manipulation. Observations, inferred intentions, proposed interventions, operational authority, and measured outcomes should remain distinct. A mobile conversational robot does not thereby demonstrate beneficial organizational change.

## Decisions needed now and choices that remain open

The architecture discussion should now distinguish the construction ecosystem from the robot's eventual work capability; preserve hands as an early demanding research focus; and keep biomimetic actuation investigation concurrent with software progress. It should establish evidence identities, responsibility boundaries, and a way to count human attention, engineer intervention, and complete-system costs.

Representative task families and the consequences of design changes are needed before interfaces are hardened. Exact performance thresholds should follow domain and engineer input. The core development model must permit coupled evolution and preserve physical-state uncertainty.

Full body shape, number of fingers, locomotion, actuator family, simulator, manufacturing process, recruitment, equipment, and substrate host can remain open. Their dependency order is approximately: representative work demands → discriminating mechanisms and constraints → candidate co-designs and measurements → justified commitments. Investigations can overlap and feed back; this is not a waterfall or a requirement to finish all software first.

## Three bounded research briefs

**1. Capable-hand mechanism study.** Ask which combinations of tendon routing, compliance, sensing, and force generation can support a small representative manipulation set beyond simple grasping. Compare a few mechanically explicit candidates, with a motor–tendon baseline where useful and artificial-muscle candidates retained. Produce an engineer-reviewable tradeoff map with assumptions and missing measurements. Evaluate attainable capability, recovery, installed resources, and maintenance implications. Redirect if the apparent benefit disappears when packaging or power delivery is included.

**2. Minimal useful simulation study.** Ask what model fidelity preserves the ranking of two contrasting candidate mechanisms for one contact interaction. Define the physical quantities that would need identification, plausible uncertainty ranges, and held-out conditions. Compare simple and refined representations of the disputed mechanism. Produce a calibration and falsification plan rather than a claim of qualification. A ranking reversal under plausible assumptions identifies information worth obtaining; agreement alone does not establish physical correctness.

**3. Development reuse and workplace transfer study.** Walk a requirement change through the proposed machinery—for example, moving from utensil handling to a workplace tool task—and identify retained knowledge, necessary redesign, controller adaptation, and physical rework. Separately trace a workplace observation, such as repeated inventory reconciliation, into an opportunity hypothesis, proposed software/process change, and business outcome measure. Produce a responsibility and evidence map. Judge reuse by useful retained capability and reduced reconstruction, rather than unchanged APIs or activity volume.

These briefs are proposed decision instruments. The evidence base is bounded primary documentation, abstracts, and primary-host extracts; no experiments were reproduced and no comprehensive survey is claimed. Current verified workspace documents take precedence over historical memory. No Desktop genesis B review was used.

