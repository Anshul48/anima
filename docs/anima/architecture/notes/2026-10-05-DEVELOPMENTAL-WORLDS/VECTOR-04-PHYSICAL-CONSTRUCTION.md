# Vector 4 — The physical construction environment

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

Architecture discussion, 2026-10-06. This is the full fourth-vector treatment. It builds on [developmental change](VECTOR-01-DEVELOPMENTAL-CHANGE.md), [attention and commitments](VECTOR-02-ATTENTION-AND-COMMITMENTS.md), [expert individuality](VECTOR-03-EXPERT-INDIVIDUALITY.md), and the earlier [physical-development dossier](PHYSICAL-DEVELOPMENT.md). Recommendations remain proposals for the user's later input.

**My current bet:** build the ability to turn conceptual intent into an evidence-bearing physical realization, then improve that construction ability through experience. The resulting environment should let engineers, AI systems, robots and instruments perform progressively more of the detailed work.

Capable hands are a demanding early ambition. Artificial muscles, useful body dynamics and morphology deserve active investigation. Those priorities should influence the construction environment now, while the specific embodiment, actuation, facilities and runtime remain open.

The larger target is a world in which physical designs, computational models, procedures, instruments and cooperating participants can develop together. Useful hardware work can begin on a small software foundation while the rest of ANIMA continues.

## Three capabilities that need separate treatment

The construction ecosystem, the body it produces and the work that body eventually performs are different capabilities.

The ecosystem helps formulate requirements, investigate alternatives, realize artifacts, measure behavior and retain useful knowledge. The body provides physical abilities such as grasping, manipulation, sensing or movement. A workplace collaborator additionally needs to understand activity, identify opportunities, propose interventions and assess their consequences.

Each can advance without completing all the others. An instrumented fixture can accelerate a physical investigation before a humanoid exists. A hand can become useful before locomotion is solved. A situated system can help investigate a workflow while its physical action repertoire remains limited.

These separations help preserve the ambition. They prevent an attractive demonstration in one area from being treated as success in all three.

The hardware analogue of STC is therefore broader than a robot controller or design generator. Its front door is a desired capability and relevant tradeoffs. Its work includes resolving the engineering necessary to realize and assess that capability.

“Build anything” can describe the eventual interface ambition. Each demonstrated ability still needs its actual engineering and operating envelope.

## The user's role and the work that must happen somewhere

The user wants to work predominantly at the conceptual and architectural level. That should shape the allocation of labor.

Models can investigate literature, generate candidates, write software, analyze measurements and prepare comparisons. Engineers contribute mechanical, electrical, fabrication, controls and measurement competence. Robots and instruments can execute particular physical operations. Coordinators can preserve state and organize dependencies.

That allocation does not make detailed engineering disappear. Someone or something must establish tolerances, construct fixtures, identify uncertain behavior, calibrate measurements, diagnose anomalies and maintain the apparatus.

The environment should progressively retain the knowledge and procedures that make this work repeatable. It can automate a recurring operation, improve a diagnostic procedure or learn which expertise a changed design needs.

Reduced user intervention is a useful outcome, but it is not sufficient by itself. Work may have moved to engineers, preparation or maintenance. A genuine improvement can justify that investment through new capability or later reuse; its complete cost should remain visible.

Human attention is also a productive resource. Preserve space for direction and synthesis while resolving routine details within established responsibilities. The goal is stronger collective work under sustainable constraints, rather than eliminating valuable human judgment.

## The smallest useful software foundation

The [current hardware roadmap](../../../../../components/substrate/docs/HARDWARE-AND-RESEARCH-ACCELERATION.md) already identifies a repeatable experimental path:

\[
\text{question}
\rightarrow
\text{candidate}
\rightarrow
\text{execution}
\rightarrow
\text{measurement}
\rightarrow
\text{retained evidence}
\rightarrow
\text{next decision}.
\]

This is a dependency sketch, not a mandatory serial workflow. Investigation, preparation, modeling and analysis can overlap.

A small useful path needs to connect an actual question to identifiable candidates, a feasible realization or simulation, interpretable observations and a decision. It should preserve enough information for another competent participant to understand and continue the work.

Existing engineering tools, scripts, supervised operations and ordinary records can establish that path. A general world host, autonomous researcher or polished construction console need not be its entry dependency.

The discriminating test is a later demand. Does the retained work improve the next decision or reduce reconstruction? Can a participant identify which assumptions changed and what must be redone?

This gives software development a concrete caller. Shared machinery can emerge from recurring needs across experiments, rather than requiring the hardware effort to wait for a complete universal substrate.

## The reusable unit is an evidence-bearing realization

A component catalogue says what could be used. A design package says what could be made. The reusable unit we need is richer.

It connects the design with compatible control, sensing, fabrication, assembly, calibration and evidence of behavior under particular conditions.

That package might include drawings, CAD, a bill of materials, software, fabrication instructions, assembly conventions, measurement procedures and learned models. The appropriate contents depend on the mechanism.

It must also distinguish reusable design knowledge from a particular specimen. A recipe can be instantiated again. The new specimen's condition and calibration still need assessment.

Reuse can take several forms: assemble an unchanged design, adapt a subsystem, reuse a control procedure, inherit an experimental method or reconstruct a coupled arrangement. The environment should retain which form worked and what remained necessary.

This is the physical counterpart to reusable computational knowledge. Its value is the useful engineering already paid for, including the conditions under which that knowledge can be applied.

A successful realization might eventually become a primitive in the construction language. That would make future work easier, but the primitive still needs recoverable assumptions, limitations and revision paths.

## A world that connects several forms of work

One proposed logical view is:

~~~mermaid
flowchart LR
    I["Conceptual intent and tradeoffs"] --> D["Coupled design worlds"]
    D --> S["Models and simulation"]
    D --> R["Engineering and realization"]
    S --> E["Interpreted evidence and uncertainty"]
    R --> P["Physical operations and observations"]
    P --> E
    E --> D
    E --> I
    E --> K["Candidate records and scoped reusable capabilities"]
    K --> D
~~~

This view organizes responsibilities. Each area can contain further worlds, share facilities or form temporary and persistent composites.

Records retain their evidence class, assessment status and supported conditions, with specimen and configuration links where relevant. Simulation can support reusable models and procedures without by itself qualifying a physical realization. Keeping those distinctions visible does not require one universal promotion gate for every kind of work.

A design world can contain alternative embodiments and computational models. An experiment world can contain a specific question, configuration, method and evaluation. An execution world can coordinate instruments, robots and operators. An analysis world can retain competing explanations of the observations.

Containment does not automatically imply ownership of a facility or authority over its operation. A world may refer to evidence, borrow a capability or use an externally controlled instrument.

The common foundation needs enough identity, resource, lifecycle and operation semantics to make that cooperation coherent. Local worlds retain the meaning of their models, measurements and outcomes.

The shared substrate should accommodate changes to these arrangements. It need not provide one universal evaluator for mechanics, materials, business processes and cognition.

## A physical specimen has a partly observed history

A physical artifact is more than its latest design revision.

It has been fabricated, assembled, operated, modified and exposed to conditions. Wear, deformation, temperature, contamination and calibration can affect what happens next. Some of this state may be unobserved or uncertain.

The development environment should distinguish known configuration, last observation, estimated current condition and uncertainty. “Resume experiment” can otherwise mean applying an old procedure to a changed specimen.

A useful record connects at least the relevant design, specimen, controller, instrument configuration, preparation, calibration, environment and observed interventions. It retains failed attempts and discrepancies alongside results.

This does not require measuring everything. The question is which unobserved conditions could change the decision and how the remaining uncertainty affects interpretation.

A simulation checkpoint can restore a modeled state. A software checkpoint cannot restore consumed material or reverse every physical consequence. A new specimen made from the same recipe is another realization, not a perfect copy of the first.

An assessment applies to the specimen configuration and conditions it assessed. Wear, replacement or another changed condition can make an earlier assessment inapplicable. The appropriate response may be a new observation, a targeted check or a more conservative operation. Routine work can continue within its standing operational scope; consequential uncertainty narrows the affected operations while independent work continues.

The digital twin is therefore a maintained estimate with a relationship to physical observations. Its name does not establish fidelity.

## Prediction, measurement and interpretation remain distinct

A design model predicts behavior. A simulator computes behavior within its modeled assumptions. An instrument produces observations through a measurement process. Analysis interprets those observations.

Each can fail differently.

A simulator can omit a decisive phenomenon. An instrument can drift. A transformation can introduce a unit or timing error. An analysis can correctly process its inputs while answering the wrong physical question.

Retaining raw observations is valuable, but raw data does not interpret itself. The meaning of a result depends on preparation, measurement, assumptions and the evaluated condition.

The evidence path should preserve discrepancies rather than silently adjusting the model until past results look consistent. Several explanations may remain plausible. A targeted experiment can then distinguish them.

A successful repetition within one apparatus establishes a narrower claim than transfer across specimens, fabrication runs or operating environments. The environment should retain those scopes when promoting a realization into reusable knowledge.

## Capable hands define a work envelope

The user's minimum ambition is functional hands that can cook or perform other useful work. The architectural implication is a demanding manipulation envelope, rather than a requirement to select an entire humanoid first.

| Kind of work | Relevant abilities to investigate |
|---|---|
| Handling varied objects | Contact adaptation, force regulation, sensing and recovery |
| Reorienting and placing | Dexterity, pose control and reliable release |
| Using utensils or tools | Appropriate forces, stable contact and tool-relative state |
| Coordinating two hands | Shared task state and coupled manipulation |
| Working under changed conditions | Transfer, diagnosis and recovery when assumptions fail |
| Sustained practical operation | Maintenance, repeatability and integration with the surrounding workflow |

Cooking is a useful source of demands: object variability, liquids, heat, surfaces and sequential activity. A successful grasp or motion does not establish competence across the whole process.

A smaller test can isolate a mechanism while the larger work envelope guides design. For example, a component investigation might examine contact regulation across a few different objects, with later transfer asking whether the useful behavior survives another tool interaction.

Mobility should follow the access and work demands. A fixed setup, mobile base or bipedal body imposes different constraints. Bipedal locomotion remains a meaningful research branch; it is not selected by the word “humanoid.”

The initial body and the construction ecosystem can also differ. Existing constrained machines or fixtures may help build and test the more ambitious body.

## Preserve the actuation preference without hiding the question

The user's preference is for bio-inspired designs, artificial muscles and morphological computation, with motors admitted when a justified prototype or bootstrap makes them necessary.

That preference should create an active research branch. It should influence which mechanisms are investigated and what the environment can represent. It should not be reduced to a decorative future option after the main architecture becomes rigid.

Tendon routing, compliance and force generation are nevertheless different choices. Tendons transmit force. An artificial muscle produces force through a particular energy-conversion mechanism. Their integration changes the complete system.

A motor-driven tendon arrangement can be a justified comparison or bootstrap when it resolves a specific uncertainty or enables necessary engineering work. The reason should be explicit, and its use should not silently select the permanent design.

The artificial-muscle branch has its own discriminating questions: attainable force and stroke, speed, control, sensing, cycle life, fabrication, packaging and installed power delivery. The desired biological property should be clear.

This preserves ambition while making engineering evidence useful. A candidate is valuable because it realizes the needed property under relevant conditions, including the cost of making and maintaining it.

## Morphology can perform useful work

The body can influence the computation needed for a task through geometry, compliance, transmission and contact dynamics.

For example, a compliant contact surface might accommodate variation that would otherwise need more precise active control. A tendon arrangement might coordinate motion mechanically. Passive dynamics might help stabilize an interaction.

These are mechanism hypotheses to assess. The gain could appear in robustness, achievable behavior, energy, controller demands or sensing requirements.

Complexity can also move elsewhere. A passive arrangement may be difficult to fabricate, calibrate or adapt to another task. A softer mechanism may complicate precise inference and maintenance.

We should therefore ask what useful work the morphology performs and what costs it introduces. Biological appearance is insufficient evidence.

The user's remodeling analogy raises a related question: can local signals and constraints guide useful adaptation without micromanaging every component? An engineered system needs actual change mechanisms for that to happen—adjustable parameters, accessible geometry, material processes, replacement procedures or other physical affordances. A software instruction cannot supply a missing physical degree of freedom.

## Co-design changes several things together

Let \(d\) denote relevant physical design choices, \(\theta\) a controller or inference configuration, and \(\xi\) operating conditions. A task outcome can be described as:

\[
J(d,\theta;\xi).
\]

This notation makes the coupling explicit. It does not assume that every criterion can be reduced to one scalar or optimized by one algorithm.

Changing morphology can change what the controller observes and which actions it can realize. Changing force generation can change packaging, power delivery and thermal behavior. Changing sensing can change the achievable feedback policy.

Manufacturing and calibration choices belong in the same analysis where they affect the result. A design that works only under an unavailable fabrication tolerance has a different practical meaning from one that can be reproduced.

The environment should expose enough of these dependencies for the present question. It can permit a joint revision of design, model, control and measurement rather than forcing each through an immutable interface that conceals the important interaction.

A high-level capability can remain useful across internal change. Its compatibility should follow actual behavior and supported conditions, rather than matching an interface name.

## Simulation fidelity should follow the decision

Simulation can explore candidates before realization and make some comparisons much cheaper. Its useful abstraction depends on what could change the choice.

A contact question may need geometry and friction uncertainty. A control question may need actuator delay, hysteresis or saturation. A fabrication question may need variability the nominal model omits.

MuJoCo's version 3.3.7 documentation separates transmission, activation dynamics and force generation in its actuator model. That is one existing way to represent useful mechanical and activation abstractions without simulating microscopic biology. It supplies modeling machinery; it does not establish that its biological muscle model represents a proposed artificial actuator. [Official actuation documentation](https://mujoco.readthedocs.io/en/3.3.7/computation/index.html#actuation-model)

The user's suggestion to encode useful biological mechanics in the simulator can therefore be pursued as a surrogate-model question. Which simplified dynamics preserve the behavior or ranking relevant to the decision?

A cheap model can be valuable. A more elaborate model can remain misleading if its uncertain parameters dominate the outcome.

The useful result is a decision supported by an adequate model and an explicit account of what still needs physical evidence.

## Ranking stability and targeted measurements

Suppose candidate A appears better than candidate B in one simulator. That preference may reverse when plausible parameters or missing effects change.

The environment can compare the candidates across a justified family of models and conditions. Stability within that family is evidence about modeled robustness. It does not prove physical correctness or cover phenomena omitted from the family.

A ranking reversal can be useful. It identifies which uncertain property may deserve measurement before further search.

A real experiment may then update the surrogate, expose a missing mechanism or invalidate the comparison. Those outcomes should change the next question rather than being treated merely as unsuccessful execution.

Candidate search can also exploit a model's defects. Held-out modeled conditions and independent physical observations can help reveal that problem, within their actual coverage.

The allocation objective is to spend modeling and measurement effort where it changes a consequential decision. It should also preserve some capacity to discover an uncertainty the current model has not represented.

## Installed behavior matters more than an isolated mechanism

A promising actuator has to operate with its power delivery, sensing, controller, transmission, structure and maintenance.

The inspected electrohydraulic shoulder study illustrates this. Its self-sensing map was trained using motion-capture data; physical tuning and filtering affected closed-loop behavior, and the paper reports limits on unseen data. That makes calibration and applicability part of the reusable capability, rather than incidental setup. Selected primary methods and limitations were inspected. [Christoph et al., inspected v1](https://arxiv.org/html/2404.04079v1)

The [bounded physical-evidence note](VECTOR-04-EVIDENCE-NOTE.md) examines further installed-system and morphology questions. Its source scopes distinguish apparatus demonstrations, component measurements and complete autonomous operation.

This is why headline efficiency, force density or demonstrated motion should not settle a body choice. Complete-system capability and costs may change when the surrounding apparatus is included.

The engineering package should preserve what is actually necessary to reproduce the result, including external equipment and calibration. Dependencies can later be reduced or integrated; their current existence remains evidence.

## A worked developmental trajectory

Consider a hypothetical world investigating a tendon-driven hand component for varied contact. No actuator, hand design or physical experiment is selected by this example.

The initial candidate combines a geometry, force-generation model, controller and measurement procedure. Its useful envelope is limited: repeated work under known object and preparation conditions.

Suppose changed objects reveal an unreliable contact response. The first diagnosis might be a controller defect. Alternative explanations include friction, compliance, sensor interpretation or a model that omits loading history.

The world develops competing candidates and an experiment that can distinguish the consequential explanations. A mechanical expert proposes a revised tendon path and compliance. An actuation expert investigates an artificial-muscle candidate. Controls and measurement experts revise their models and tests accordingly.

The important transformation changes several things:

- The physical arrangement changes force transmission and contact behavior.
- The inference process changes which state it estimates.
- The controller changes its interventions.
- The measurement procedure changes how improved behavior is distinguished from different deformation.
- Calibration and maintenance responsibilities change with the mechanism.

If the evidence supports the new arrangement under declared conditions, the world can retain a coupled realization. The useful result includes how it was made, controlled, measured and interpreted.

The investigation might instead reveal that a cheaper revision solves the problem, or that the artificial-muscle candidate has a decisive installed limitation. Either result is useful evidence without changing the programme's broad ambition.

## The team and its machinery can reorganize too

The worked trajectory can also develop organizationally.

Initially, experts provide separate reports. Repeated work reveals that independent geometry, actuator and control updates invalidate one another's assumptions.

They form a joint realization world that takes custody of the integrated model, calibration procedure and continuing experiment queue. The old boundary between separately maintained subsystem updates is replaced by a coordinated update process.

The composite becomes responsible for the capability exported to callers. Specialist interpretations can remain attributable, including unresolved disagreements. Shared physical resources retain their actual availability and custodians.

A later task may justify extracting a subsystem or splitting the team. The successors need the relevant design state, procedures, evidence access and continuing responsibilities. Some joint machinery may remain shared because it does not decompose usefully.

A physical specimen cannot be duplicated merely because its world splits. Continuing work must allocate its use, or realize another specimen with the appropriate fabrication and calibration effort.

This makes the world-hosting ambition concrete. Development can change representations, tools, participants, custody, lifecycle and physical arrangements together. The records should preserve what actually changed and whether the resulting capability is useful elsewhere.

## Adaptation, reconstruction and physical change

There are several forms of adaptation, with different mechanisms and costs.

| Form | What changes | What must be available |
|---|---|---|
| Interpretation update | Estimated state, model or applicability | Relevant observations and a defensible update method |
| Operational adaptation | Control, calibration or procedure | An exposed adjustment surface and evidence of its effects |
| Reconfiguration | Routing, geometry, allocation or available configuration | A realizable mechanism and suitable resources |
| Replacement or reconstruction | Component, subsystem or specimen | Fabrication, assembly, calibration and responsibility for continuing work |
| Development of a new mechanism | The available design or construction repertoire | Investigation, realization and suitable outcome assessment |

These can interact. A state estimate may prompt recalibration. Repeated adaptation may motivate a redesigned component. A redesigned component may require new sensing and a different experiment.

The environment should know which kind of change it can actually perform. A parameter update, component replacement and new fabrication process are different operations.

The biological inspiration is useful when it produces mechanisms for diagnosis, local response and cumulative improvement. It does not make every engineered material capable of remodeling or every failure recoverable.

Future physical plasticity can expand the available changes. The present architecture should accommodate those participants without pretending they already exist.

## Robots can accelerate research before they perform all human work

A robot need not possess general dexterity to help execute a constrained, well-characterized operation. A fixture or instrument can sometimes perform it more effectively.

The A-Lab study reports an integrated materials-synthesis workflow combining recipe selection, robotic preparation and transfer, heating, characterization and iterative optimization. The inspected text also describes later manual analysis of reported outcomes. This is evidence for bounded closed-loop physical research on a built apparatus, not general autonomous engineering or an infallible scientific evaluator. Publisher retrieval failed; selected author-hosted primary passages were inspected. [Primary paper](https://bartel.cems.umn.edu/sites/bartel.cems.umn.edu/files/2026-02/szymanski.ceder_2023-nature.pdf)

The lesson for ANIMA is to connect decision-making, real execution and interpretable feedback in a tractable domain. The work required to build and maintain the apparatus still counts.

Repeated operation is one kind of gain. Better experiment selection, more reliable diagnosis and improved reuse are additional claims with separate evidence.

Robotic participation can grow as the task repertoire and evidence improve. It can also remain deliberately constrained where a simpler facility supplies the needed operation.

This supports early physical research without making a complete humanoid the prerequisite for its own development.

## The workplace collaborator is a further integration problem

The user's workplace ambition combines physical presence with understanding and improvement.

An embodied system might observe repeated inventory reconciliation, identify a possible information-flow problem, investigate a software opportunity and propose a change. Each step introduces another interpretation.

Observing repetition does not establish why it occurs. A plausible explanation does not establish that a proposed intervention helps. The effect needs an appropriate outcome measure and the operational scope to carry out the change.

A capable model can assist with technical formulation, but it needs relevant evidence about the actual workplace. Physical access, conversation, process understanding, software tools and domain expertise can be complementary.

The construction environment can help build and assess these capabilities. The eventual workplace world should retain its own objectives, responsibilities, uncertainty and operational state.

This remains broader than manipulation. It also gives the developing body a meaningful purpose: participation in a wider collective system that investigates and realizes improvements.

## Computational hardware and physical research reinforce one another

The broader hardware/software direction contains two connected loops.

One improves how computational work is implemented: memory locality, communication, precision, allocation, reconfiguration and eventually new physical primitives. The other improves how physical research and construction are performed: instruments, fixtures, robots, fabrication and measurement.

A physical research system can use ordinary compute while exploring a new mechanism. A computational hardware investigation can use the same experimental discipline without needing a dexterous robot.

The first entry should follow a consequential bottleneck or hypothesis. The software path should make that investigation faster or more reusable. A technology ladder from GPU to FPGA to neuromorphic hardware would not by itself establish useful progress.

The two loops can later co-develop. A body can expose a computation that benefits from specialized implementation. A computational capability can enable better sensing, experiment selection or physical control.

This preserves A → C → B → D as the priority map while allowing hardware competence and useful physical work to begin on overlapping timescales.

## How to start learning hardware without mastering everything first

The user needs enough strategic competence to frame questions, challenge assumptions and judge the important tradeoffs. The team needs detailed implementation competence for the selected work.

Those needs can be developed together through a bounded investigation. Identify the physical mechanism, its measurement requirements, relevant design choices and the evidence that would change direction. Bring in competent engineering judgment early where it changes the plan.

Models can prepare background, alternatives and explanations. Practical work can reveal which parts of that knowledge actually matter. A growing map of adjacent fields can prevent the first specialty from becoming a permanent boundary.

Mastery of all hardware should not be an entry condition. Neither should a literature packet be mistaken for the competence needed to realize and assess a device.

The useful route is depth tied to work, with access to complementary expertise. It can develop into broader hardware capability while software and substrate development continue.

## The strongest simpler competitor

The meaningful comparator is a competent engineering team using ordinary design tools, scripts, laboratory records and established automation.

Give that team comparable expertise, facilities and assistance. It can already preserve design history, run simulations, diagnose failures and improve procedures.

The proposed environment earns its place if it produces useful capability, reduces reconstruction, improves investigation or makes more work reliably delegable. A more elaborate ontology or a larger agent roster is insufficient.

Count setup, fabrication, calibration, failures, physical throughput, maintenance, software repair, engineering effort and human attention. Preserve new-capability gains alongside efficiency measures.

An early implementation can justifiably cost more while creating a reusable capability. That is a hypothesis about subsequent value, not a license to exclude the initial cost.

Repeated metacoordination can also become the bottleneck. Each shared service should resolve a real caller's difficulty. Some responsibilities should stay in existing tools or with specialists until repeated use justifies extracting common machinery.

## What would show the environment is developing?

A requirement change is a demanding test.

The changed task should invalidate some old design, control or measurement assumptions. The environment should identify affected artifacts and evidence, develop suitable alternatives, coordinate the necessary realization work and preserve the interpretation of the results.

A later participant should be able to continue with less reconstruction. A retained procedure should improve another decision. A new realization should declare its dependencies and supported conditions.

Several outcomes need separate assessment: physical task performance, experiment quality, correctness of interpretation, reuse, intervention burden and complete cost.

Failure can be informative. The environment may discover that it lacks a necessary measurement, that a source model was wrong, or that its construction repertoire cannot realize the proposed change. Useful development includes recognizing those gaps and forming a productive next question.

If engineers still reconstruct every connection informally while the system generates polished design packages, the reusable construction claim remains unestablished.

No experiment is launched by these criteria. They identify what a focused physical-development architect should discriminate.

## What I would preserve for the next design stage

I propose five principles for later consideration.

1. **Conceptual intent leads to an evidence-bearing realization.** Retain design, control, sensing, fabrication, calibration, conditions and actual outcomes.
2. **Physical identity and uncertain state are first-class concerns.** Models, specimens, configurations, interventions and measurements remain linked and distinct.
3. **Co-design is a supported form of development.** Design, computation, measurement and organization can change together.
4. **Hardware entry uses the smallest useful experimental path.** Physical competence and investigation can develop alongside the wider software system.
5. **Autonomy grows through assessed capability and reuse.** Engineers, AI systems, robots and instruments progressively own more work, with complete costs and consequential responsibilities visible.

These proposals fit the current [ANIMA responsibility map](../../RESPONSIBILITIES.md). TL and TRACE retain their source and interpretation duties, SST provides bounded exploration under domain evaluation, STC contributes construction/execution machinery, and the broad substrate accommodates worlds and structural change. Particular physical worlds and facilities need their own contracts.

The immediate architectural commitment I would seek later is this experimental and realization model. The body, actuator family, simulator, facilities, staffing and runtime topology remain choices to investigate.

The longer ambition is a construction ecosystem that develops better ways to investigate and build, including revising what it builds with. The useful early path should already produce physical knowledge that future worlds can inherit.

Vector 5 can then examine creative coverage: how unusual evidence and unfamiliar combinations remain discoverable as knowledge is compressed and organization becomes more efficient.

## Review and evidence scope

A separate agent reviewed the main essay and its [evidence note](VECTOR-04-EVIDENCE-NOTE.md) for conceptual coherence, preservation of user intent and calibration of claims. The review prompted explicit evidence and assessment status in the world diagram, a fixed documentation version and clarification of how changed specimen conditions affect prior assessments. A follow-up review confirmed these amendments resolved the identified ambiguities.

The evidence note records primary-source inspection by a separate research agent. The main author also inspected the cited MuJoCo section, shoulder-study passages and selected passages of the author-hosted A-Lab paper. The conceptual reviewer did not independently reproduce the studies or verify the underlying actuator accounting. This is reviewed architectural analysis and scoped literature inspection; it establishes neither physical qualification nor adoption of these proposals.
