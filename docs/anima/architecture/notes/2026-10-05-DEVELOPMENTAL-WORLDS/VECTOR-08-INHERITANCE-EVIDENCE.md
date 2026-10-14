# Vector 8 evidence note: retention and descendants

Status: proposed architecture and bounded literature analysis, 2026-10-07. Companion: [Retention and descendants](VECTOR-08-RETENTION-AND-DESCENDANTS.md). This note does not select a runtime, authorize construction, or qualify an inheritance mechanism.

The question is what can remain useful after a world changes, retires, fuses, splits, or produces descendants. Three precedents distinguish copying acquired state, evolving a compact structural generator, and continuing search through changing environments. Their reported endpoints are narrower than ANIMA's proposed worlds. The architecture implications below are original proposals, not capabilities established by these papers.

## Inspected primary evidence

### 1. Acquired state: population based training

[Jaderberg et al., Population Based Training of Neural Networks](https://arxiv.org/html/1711.09846v2), arXiv:1711.09846v2, 28 November 2017. Inspected Algorithm 1, §§3, 4.2–4.4 and reported results; no reproduction.

Workers copy selected peers' learned weights and hyperparameters, perturb hyperparameters, and continue training. In the tested DeepMind Lab setting, combining weight selection and adaptive hyperparameters worked better than either alone; reusing final hyperparameter values did not reproduce adaptive training's benefit. Endpoints include reinforcement-learning returns, translation validation/test BLEU, and GAN Inception scores. This establishes useful continuation and selection within tested training tasks, not transferable world organization or developmental rules. Acquired weights and an adaptive trajectory differ from a final configuration. Population training, evaluation and copying still consume resources; asynchronous execution does not erase total work. The inspected algorithm describes weights and hyperparameters, insufficient to infer universal copying of optimizer state, histories or dependencies.

### 2. Generated structure: HyperNEAT

[Stanley, D'Ambrosio and Gauci, author-uploaded accepted manuscript](https://www.researchgate.net/publication/23986881_A_Hypercube-Based_Encoding_for_Evolving_Large-Scale_Neural_Networks), *Artificial Life* 15(2), 2009; [DOI](https://doi.org/10.1162/artl.2009.15.2.15202). Inspected selected methods/results in §§3–7 and §8.2 discussion; no reproduction.

Evolved CPPN genomes encode coordinate functions generating connection weights for a supplied neural substrate. Inheritance concerns this generator rather than a fully enumerated mature matrix. Visual-discrimination solutions scaled to higher resolutions, including previously unavailable positions, without further evolution. Food-gathering transfer could instead expose artifacts and require further evolution. Substrate geometry, input/output placement, interpretation and fitness were supplied; these were deliberately simple tasks. This supports investigating generative structural reuse under particular regularities, not automatic invention of arbitrary world organization. Compact encoding does not remove genotype search, fitness evaluation, generating expanded networks or executing them. Access used the coauthor's accepted manuscript uploaded September 2014; publisher text was unavailable, so exact final-typesetting equivalence was not checked.

### 3. Changing conditions: Enhanced POET

[Wang et al., Enhanced POET](https://proceedings.mlr.press/v119/wang20l/wang20l.pdf), published ICML/PMLR 119, 2020; [supplement](https://proceedings.mlr.press/v119/wang20l/wang20l-supp.pdf). Inspected §§3–4, 6.1–6.2 and supplementary A.7–A.8; no reproduction.

Environment encodings mutate while paired policy weights undergo optimization and transfer between simulated biped obstacle courses. Admission, novelty and predefined scoring govern this process. Controls compare direct optimization and ground-interpolation curricula against fifteen targets selected from already generated, solved environments; these are not independent broad heldout tasks. Budget matching counts target/ancestor-line simulation rollouts and incoming transfer attempts, not full population lifetime expenditure. The supplementary cross-environment matrix shows mostly specialists, not agents solving all or most challenges. Thus continued population innovation and useful transfer can coexist with limited individual generalization. Search, transfer evaluation, environmental generation and archive costs remain relevant; neither indefinite innovation nor physical-world inheritance is demonstrated.

## Proposed distinction: what travels, what remains available, what must be reacquired

An inheritance proposal should distinguish at least three questions. What state or procedure is passed? What external capability remains usable? What must a descendant learn or reconstruct in its new conditions? These questions can have different answers for the same world.

Acquired state could include trained parameters, working interpretations, calibration, procedural experience and unresolved tasks. A structural rule could generate a different organization from a seed when demand or evidence changes. An update procedure could guide subsequent adaptation without specifying the resulting organization. A mature snapshot can combine all three, yet still fail to contain the dependencies responsible for its usefulness.

These are analytical distinctions, not a mandatory genome format. Software need not enforce a biological separation between lifetime learning and heredity: acquired changes can be copied, distilled, transformed or deliberately omitted. The useful separation is between how an arrangement became capable during its lifetime and which parts of that process or result actually support a successor. Preserve the distinction between the enacted transformation, the adaptation being assessed, and the material inherited; they need not share a boundary.

A seed and generative procedure also inherit assumptions. A rule that creates specialists according to workload may depend on the available repertoire, measurements and access rights. It should be possible to adapt the rule, its representation and the organization it generates. Calling the rule “developmental” does not establish that it can recover when those assumptions fail.

## Proposed relational and environmental inheritance

Competence may depend on a relationship: a joint model, shared experimental procedure, translation between representations, complementary expert histories, or access to a facility. Copying each participant independently can lose the capability even if every local checkpoint survives. A useful descendant might therefore inherit a composite, continue using the joint capability remotely, inherit a reconstruction procedure, or accept partial competence while reacquiring missing relations.

These alternatives change actual organization. A composite can host other worlds, share machinery, and take custody of joint state. Fission can separate some activities while keeping a shared service or evidence base. Fusion can produce a successor whose useful differences remain attributable even though the previous participants no longer operate independently. Neither operation should imply that old worlds can always be recreated or that obligations and resource claims can be duplicated.

An inherited relation must correspond to available machinery or a justified reconstruction path. Copying a graph edge is insufficient if the collaborator has retired, the interpreter changed, or the descendant lacks required access. Access, custody, containment and placement remain separate. A shared commitment requires a current responsible participant; ancestry cannot confer competence, a right to use data, or authority over another world's decisions.

Environment inheritance is similarly conditional. A simulated challenge specification can be copied. A physical apparatus has wear, material state, calibration and contingent availability that a file does not duplicate. Even in software, inherited tool names can resolve to different versions or behavior. Sometimes the valuable inheritance is a method for discovering and adapting to present conditions, rather than a promise that prior conditions persist.

## Proposed retention without compulsory active history

Retention should serve prospective use, accountability or reconstruction under an actual owner's scope. Keeping a capable world active, keeping its source evidence, retaining a procedure, and preserving enough state to reconstruct it are different expenditures and different promises.

A retired specialist need not retain an active tombstone in every working graph. Historical records can remain outside ordinary traversal, with discovery routes appropriate to their source collection. Nor should recoverability be asserted merely because a pointer exists: availability, interpretation and reconstruction dependencies matter. A descendant may preserve a compact explanation of consequential lineage without keeping the entire ancestral arrangement resident.

Retirement can abandon expensive state while preserving a useful conditional procedure and its evidence. Conversely, a cheap seed can be misleading if rebuilding requires unavailable collaborators or large reacquisition work. Some losses are acceptable and should be described as losses; retention cannot guarantee that every future useful combination will remain recoverable.

Under the [current responsibility map](../../RESPONSIBILITIES.md), local worlds and lifecycle owners retain state and obligations within their scope; TL organizes attributable source material within its releases, TRACE interprets within granted semantic authority, and SST supplies bounded alternatives. None becomes a universal archive or inheritance authority through this proposal.

## Proposed discriminating example and comparisons

Consider a hypothetical analysis world that has learned to coordinate a sensor specialist, a materials specialist and a shared estimator. A descendant receives a changed sensor layout and material regime. A mature snapshot may start quickly but preserve assumptions that now mislead. A generative procedure might assemble a different specialist arrangement, while a conditional update procedure discovers that calibration and representation must change together. It could also fail, consume more work, or recreate the same mistaken assumptions.

The capability is not demonstrated by producing a descendant record or plausible explanation. A useful comparison asks whether the inherited material changes reliable outcomes in the altered conditions, how quickly failures become observable, and which missing relations must be reacquired. Include conditions that break the ancestor's convenient representations, rather than only variations its inherited procedure already anticipates.

Strong simpler baselines should retain the current world or checkpoint, continue adapting, retrieve earlier evidence, use capable models and tools, and invent new procedures. An authored reusable procedure is also a legitimate competitor. Artificially restarting the baseline would credit ordinary continuation to a more elaborate inheritance system. A restart control can diagnose acquired-state value, but should not be the headline comparison.

Compare mature-state continuation, conditional procedures, generative seeds and retained composites both separately and in sensible combinations. Assessment should distinguish immediate success, adaptation cost, continued performance across changed conditions, forgetting, reconstruction failures and the ability to revise misleading inheritance. Descendant attribution remains separate from observed competence. Fresh evaluation must not silently become a new authority or per-step human approval mechanism.

Count acquisition and failed lineages, retained storage and indexing, realization, translation, calibration, tests, shared services, ongoing maintenance and eventual recovery. Report wall time, compute and human effort separately. Shared acquisition costs can be amortized across useful descendants, with the assumed reuse horizon explicit; repeated copying alone does not establish benefit. Acquisition and maintenance should be counted once per actual expenditure, rather than charged repeatedly to every descendant or hidden entirely upstream.

The most useful question is therefore whether a particular inherited package improves continued capability enough to justify its full costs and constraints. A costly composite may be worthwhile because its relations cannot yet be extracted. A cheap generator may be preferable when structural regularities survive condition changes. These remain alternatives to investigate, with failures retained as evidence rather than explained away through ancestry.

## Access and scope

Current responsibility map and selected continuity passages in Vectors 1, 3 and 6 were inspected. Primary paper methods/results were read in the bounded sections identified above; no code, checkpoint or reported experiment was independently run. Literature access used public sources only. This is documentary analysis and proposed architecture; existing project commitments and the canonical context packet retain their current status.
