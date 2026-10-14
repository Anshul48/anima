# Vector 4 evidence note: installed actuation and physical feedback

**Status:** independently prepared, bounded primary-source check, 2026-10-06. Companion to [Vector 4: physical construction](VECTOR-04-PHYSICAL-CONSTRUCTION.md) and the earlier [physical-development dossier](PHYSICAL-DEVELOPMENT.md). Architectural implications remain proposals. No construction, experiment, platform selection, purchase, recruitment, or implementation is initiated by this note.

## Question and scope

The main question is the hardware analogue of ANIMA/STC: how conceptual architecture can lead to actual realization and reusable experimental capability through engineers, AI systems, instruments, and robots. This note examines three connected mechanisms: installed artificial-muscle systems; morphological co-design; and tractable simulation tied to physical calibration and feedback.

Capable hands remain a demanding early ambition, including cooking and other human work. Muscle/tendon and biomimetic research can proceed alongside software development. Mobility remains optional, and none of the leg evidence below selects a locomotion programme. Motor actuation is disfavored by the user's direction; a comparison or bootstrap needs its own justification rather than becoming the default. No universal substrate is a prerequisite.

The sources deliberately sample one artificial-muscle family with inspectable construction and control evidence. HASEL is not selected as the answer, and this is not an actuator survey. Autonomous-laboratory evidence and broader experiment semantics belong to the root's complementary treatment.

## 1. Installed actuation: a muscle needs a surrounding system

**Primary source and revision:** [Mitchell et al., HASEL fabrication and untethered-device toolkit](https://advanced.onlinelibrary.wiley.com/doi/full/10.1002/advs.201900178), Advanced Science 6, 1900178; published 2019-06-11; DOI 10.1002/advs.201900178.

**Access scope:** publisher HTML accessed 2026-10-06. Inspected introduction, sections 2.1–2.2 and 2.6–2.7, and associated figure captions. Supporting files, movies, fabrication code, and apparatus were not inspected or reproduced.

**Source summary:** The paper connects actuator geometries, a repeatable fabrication method, modular stacking, and portable electrical drive. Its untethered module uses a battery, voltage conversion, switching, and a microcontroller; charging/discharging limits constrain the available drive. A continuum-device demonstration combines independently controlled modules with joystick input. This establishes a published construction path and a bounded portable realization, rather than merely a material-property claim. The surrounding electronics are part of the demonstrated capability. It does not establish capable hands, autonomous fabrication, extended workplace operation, or that increasing actuator count preserves the same performance and usability.

**Proposed architectural implication:** retain the construction recipe and installed configuration with the observed result. A nominal actuator specification cannot stand in for the power, control, fabrication, and measurement chain required to reproduce that result.

## 2. Morphological co-design: the transmission changes the realized capability

**Primary source and revision:** [Buchner et al., electrohydraulic musculoskeletal robotic leg](https://pmc.ncbi.nlm.nih.gov/articles/PMC11385520/), Nature Communications 15, 7634; version of record 2024-09-09; DOI [10.1038/s41467-024-51568-3](https://doi.org/10.1038/s41467-024-51568-3).

**Access scope:** primary article HTML in PMC accessed 2026-10-06. Inspected abstract, device/system description, energy-accounting results, discussion limitations, and methods for moment-arm design, test setups, and consumption accounting. Supplementary media, raw data, and software were not independently examined.

**Source summary:** PELE combines antagonistic artificial muscles, tendon routing, and deliberately nonlinear joint leverage. The authors use that leverage to reshape torque delivery despite the actuator's nonlinear force–strain behavior. The measured device is an isolated, supported leg with external high-voltage amplifiers and computer/DAQ equipment. Its reported net transport cost covers actuator consumption and excludes conversion losses; added portable-supply mass is emulated rather than demonstrated as installed autonomy. The motor energy comparison concerns squatting. The study therefore provides scoped morphology/control evidence, while expressly leaving untethered whole robots and broader operating conditions unresolved.

**Proposed architectural implication:** preserve the measurement boundary when carrying an efficiency or capability claim into another world. Shape, transmission, muscle behavior, drive, and controller can require joint revision; separate conceptual descriptions do not imply independently replaceable physical modules.

## 3. Useful abstraction needs a physical correction path

### A fixed documentation example

**Official source and revision:** MuJoCo **3.3.7** documentation: [actuation model](https://mujoco.readthedocs.io/en/3.3.7/computation/index.html#actuation-model) and [muscle modeling](https://mujoco.readthedocs.io/en/3.3.7/modeling.html#muscles). This fixed documentation revision is evidence about available abstractions, not a selected simulator or installed dependency.

**Access scope:** official HTML accessed 2026-10-06. Inspected transmission, stateful actuation, force-generation, and biological-muscle modeling sections, including stated simplifications and custom-model provisions. No simulator, model, or benchmark was run.

**Source summary:** This revision separates transmission geometry, activation dynamics, and force production. Its biological muscle model represents the force-generating mechanism abstractly and uses approximate force–length–velocity behavior. It assumes inelastic biological tendons and omits some geometric detail, while allowing custom models. The documentation also warns that uncertain operating ranges can matter more than refinement of the force curve. This supports economical, mechanism-relevant simulation without microscopic fidelity. It does not validate a model of a particular artificial muscle, real contact conditions, or a learned controller. Replacing defaults with measured assumptions remains a distinct task.

**Proposed architectural implication:** retain the question, model assumptions, and physical quantities that would discriminate candidates. Model refinement should follow consequential uncertainty; a realistic appearance or biological label cannot establish the missing mechanism.

### Calibration and feedback demonstrated on an artificial-muscle joint

**Primary source and revision:** [Christoph et al., electrohydraulic shoulder self-sensing and feedback](https://arxiv.org/html/2404.04079v1), **arXiv:2404.04079v1**, submitted 2024-04-05. The metadata identifies the related ICRA 2024 paper, DOI 10.1109/ICRA57147.2024.10610994; the inspected text is specifically arXiv v1, not an independently checked IEEE version.

**Access scope:** versioned HTML and submission metadata accessed 2026-10-06. Inspected system-design sections II-B–F, experimental results and procedures in III, and limitations in IV. No supplementary media or replication.

**Source summary:** The two-degree-of-freedom shoulder separates actuation and self-sensing electrodes and demonstrates feedback trajectory control. Its estimation mapping is trained using motion-capture ground truth. Physical controller tuning and filtering matter: noisy estimates destabilize the initial control approach, and the revised controller trades stabilization for lag. The experimental apparatus includes external drive and acquisition equipment. The authors identify torque limits and weaker estimation on unseen data. Thus reduced external sensing during feedback does not imply calibration-free development, general proprioception, portable embodiment, or manipulation competence beyond the tested trajectories.

**Proposed architectural implication:** a reusable learned estimator should travel with its calibration domain, reference-data provenance, signal-processing assumptions, and known failures. An interface exposing only a position estimate would conceal conditions needed to use it coherently.

## What these mechanisms imply for the construction environment

The following are architectural inferences from the selected evidence, not results established by the papers.

**Conceptual direction must connect to accountable realization.** The user can own purpose, constraints, desired properties, and consequential choices while specialists develop realizations and measurements. A plausible AI-generated design remains a candidate until its relevant engineering consequences are established. Moving detailed work away from the user still requires competent custodians of that work.

**Reuse concerns working arrangements.** A useful primitive can include a design, fabrication procedure, installed drive, sensing, calibrated model, controller, and evidence from stated conditions. Its different parts may have different owners or hosts. Inheritance should make clear what is reusable immediately, what needs new calibration, and what depends on a facility or specialist unavailable to the recipient.

**Coupling can be plastic.** Materials, geometry, actuation, estimation, control, and manufacturing can change together. The machinery should preserve useful continuity without demanding that every revision fit an original mechanical or semantic interface. A newly encountered task can expose a coupled assumption and motivate a new composite procedure or division of responsibility.

**Simulation is one participant in the evidence loop.** It can cheaply explore a mechanism and identify useful measurements. Physical observations can correct model parameters, expose omitted state, or invalidate a candidate explanation. Those outcomes should be retained as different evidence classes. Neither a simulated result nor successful calibration on familiar trajectories substitutes for later transfer.

**Robotic execution and engineering development remain distinct capabilities.** A feedback-controlled artificial-muscle apparatus shows a specified physical operation, not a robot capable of designing, constructing, or troubleshooting itself. Engineers, instruments, and software can establish a useful experimental path before robotic autonomy is adequate. Robots can later contribute where their observed capabilities make them useful.

**Hands should keep the architecture demanding.** The early ambition should expose dexterity, contact, coordination, and changing objects rather than becoming a convenient grasp-only demonstration. These sources neither define a hand design nor establish that their mechanisms meet those demands. Cooking also contains requirements beyond manipulation; success at joint control cannot qualify the wider workflow.

The proposed target is cumulative capability with preserved conditions: later work should benefit from earlier realization and investigation without confusing portability of documents, models, or procedures with portability of physical competence. The selected literature supports investigating the ingredients of that target. It does not establish the target system.

## Access and claim boundaries

Four sources were selected for this note, with MuJoCo's two pages treated as one documentation source. Source summaries are intentionally compact. No fixed benchmark, numeric acceptance threshold, hardware selection, staffing plan, or research launch follows from this review.

The initial PMC toolkit opening returned a browser challenge; its publisher HTML was then inspected. The direct Nature article opening returned an internal retrieval error; the primary PMC article was used successfully instead. These access changes did not convert an abstract-only reading into a claim of full-paper replication. The listed section scopes, rather than the existence of accessible links, define what was checked.

For local context, only the existing physical-development dossier was read and applicable instruction locations were checked. No memory registry, private chats, Desktop genesis B material, archived sessions, or older project implementation was accessed. This is documentary evidence gathering, not physical qualification or user acceptance.
