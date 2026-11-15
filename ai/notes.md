# AI / LLM Notes

The best recent AI engineering content, organized by area.

## Research Papers

**Added 2026-11-13**

### [InfraDev: Can Coding Agents Develop AI Infrastructure, and How Can We Tell?](http://arxiv.org/abs/2610.36589v1)
- **Authors:** Yangshen Deng, Jiaqi Ruan, Yeqi Huang, Nick Lau et al.
- **Published:** 2026-10-27 | **Primary category:** cs.DC
- **Categories:** cs.AI, cs.DC
- **Abstract:** Coding agents are beginning to develop the production-grade AI infrastructure that trains and serves large models, yet existing benchmarks cover only single kernels or single-GPU tasks, and grade with tests and prompts that misjudge both correct and incorrect patches. We introduce InfraDev, a benchmark of 36 tasks built from real-world pull requests to Megatron-LM, vLLM, and verl, covering infrastructure development for training, inference, and reinforcement learning. Each task asks an agent to ...
- **Why it's here:** fresh off arXiv cs.DC -- where the research behind next year's tooling shows up first.
- **Link:** http://arxiv.org/abs/2610.36589v1

**Added 2026-11-13**

### [Food Critic: An Agentic Visualization System for Auditable Restaurant-Safety Reasoning](http://arxiv.org/abs/2611.15843v1)
- **Authors:** Arleth Salinas, Ishrat Jahan Eliza, Valerio Pascucci
- **Published:** 2026-11-11 | **Primary category:** cs.AI
- **Categories:** cs.AI, cs.MA
- **Abstract:** Generative AI agents are increasingly being embedded into visualization systems that can search data, invoke tools, summarize evidence, and produce recommendations. However, when agents rely solely on their own knowledge, the visualization problem is not only whether the agent provides a useful answer, but also whether users can inspect how that answer is grounded. We present Food Critic, an agentic visualization system for diners' restaurant decision support that integrates public health inspec...
- **Why it's here:** fresh off arXiv cs.AI -- where the research behind next year's tooling shows up first.
- **Link:** http://arxiv.org/abs/2611.15843v1

**Added 2026-11-14**

### [DRAFT-Bench: Evaluating Frontier Agents Across the Professional Design Lifecycle](http://arxiv.org/abs/2611.08933v1)
- **Authors:** Rong Pan, Jianqiang Wang
- **Published:** 2026-11-06 | **Primary category:** cs.SE
- **Categories:** cs.SE, cs.AI
- **Abstract:** Can frontier general-purpose agents understand client intent, explore creative directions, execute revisions, and prepare production deliverables? We introduce DRAFT-Bench (Design Reliability Across Feedback and Tasks), a lifecycle-oriented evaluation of requirement elicitation, creative exploration, constrained editing, iterative revision, and production handoff. Its Requirement-to-Artifact framework links evolving requirements, protected properties, artifact versions, and delivery obligations....
- **Why it's here:** fresh off arXiv cs.SE -- where the research behind next year's tooling shows up first.
- **Link:** http://arxiv.org/abs/2611.08933v1

**Added 2026-11-14**

### [MARS: Multi-Specialist LLM Relay System for Competitive Programming](http://arxiv.org/abs/2608.23918v1)
- **Authors:** Andrei Mikhailov, Mikhail Burtsev, Alsu Sagirova
- **Published:** 2026-08-24 | **Primary category:** cs.PL
- **Categories:** cs.AI, cs.MA, cs.PL
- **Abstract:** Large Language Models excel at code generation, yet competitive programming exposes a persistent failure mode: existing multi-agent pipelines distribute work over generic planner, coder, and debugger roles and delegate the choice of algorithmic technique to the backbone alone. We present MARS (Multi-Agent Relay of Specialized LLMs), a prompt-only framework in which each agent is a topic specialist---dynamic programming, graphs, strings, geometry, and so on---grounded by retrieval-augmented gener...
- **Why it's here:** fresh off arXiv cs.PL -- where the research behind next year's tooling shows up first.
- **Link:** http://arxiv.org/abs/2608.23918v1

**Added 2026-11-14**

### [Reassessing Dataset Quality and Fine-Tuning Practices for Vulnerability Detection on PrimeVul dataset](http://arxiv.org/abs/2611.06373v1)
- **Authors:** Norbert Sándor Szolnoki, Gábor Antal
- **Published:** 2026-11-04 | **Primary category:** cs.SE
- **Categories:** cs.SE
- **Abstract:** Recent studies report promising results from supervised fine-tuning of pre-trained code language models for automated vulnerability detection on benchmarks such as PrimeVul. In this paper, we present a large-scale empirical evaluation of both model performance and dataset quality in this setting. We systematically fine-tune three widely used encoder models (CodeBERT, GraphCodeBERT, and UniXCoder) across five imbalance mitigation strategies, extensive hyperparameter sweeps, and multiple random se...
- **Why it's here:** fresh off arXiv cs.SE -- where the research behind next year's tooling shows up first.
- **Link:** http://arxiv.org/abs/2611.06373v1

**Added 2026-11-14**

### [Bug2Scenario: Root-Cause-Preserving Test Scenario Amplification for Autonomous Driving Software](http://arxiv.org/abs/2611.06229v1)
- **Authors:** Yuchen Cao, Zhenyu Mao, Jacky Wai Keung, Yifei Wang et al.
- **Published:** 2026-11-04 | **Primary category:** cs.SE
- **Categories:** cs.SE
- **Abstract:** Simulation-based fuzzing exposes autonomous driving system (ADS) failures by repeatedly mutating and executing scenarios, but converting one failure into reusable regression scenarios remains difficult. Such variants test whether the mechanism persists after software changes, for example by varying weather or actor placement while retaining a collision's actor-route conflict. We present Bug2Scenario, a root-cause-guided post-fuzzing framework. From scenario data, traces, and oracle evidence, it ...
- **Why it's here:** fresh off arXiv cs.SE -- where the research behind next year's tooling shows up first.
- **Link:** http://arxiv.org/abs/2611.06229v1

**Added 2026-11-15**

### [Relational-Core Graph Analytics Querying graphs at SQL scale, and why the node/edge model is a performance tax, not a truer picture of connected data](http://arxiv.org/abs/2609.01525v1)
- **Authors:** Gene Zhang
- **Published:** 2026-09-01 | **Primary category:** cs.PL
- **Categories:** cs.DB, cs.AI, cs.PL
- **Abstract:** A durable assumption holds that graph analytics requires a purpose-built graph engine, and that relational systems are ill-suited to connected data. We argue the opposite for the workloads enterprises actually run. A columnar relational engine fronted by a graph query language matches or exceeds native graph engines on analytical graph queries, and - decisively - scales past the point where in-memory graph engines fail. We further argue that the node/edge property graph is not a more faithful mo...
- **Why it's here:** fresh off arXiv cs.PL -- where the research behind next year's tooling shows up first.
- **Link:** http://arxiv.org/abs/2609.01525v1


## Models & Datasets

**Added 2026-11-13**

### [PrunaAI/P-H3-Image](https://huggingface.co/PrunaAI/P-H3-Image)
- **Stats:** 285 likes | 1,666 downloads
- **Kind:** Hugging Face model | **Task:** text-to-image | **Created:** 2026-10-27
- **Tags:** diffusers, safetensors, text-to-image, image-to-image, image-generation, image-editing
- **What it is:** a model on the Hugging Face Hub with real community pull -- useful when you need something that already works.
- **Link:** https://huggingface.co/PrunaAI/P-H3-Image

**Added 2026-11-14**

### [TaichuAI/ZDTaichu5.0-9B](https://huggingface.co/TaichuAI/ZDTaichu5.0-9B)
- **Stats:** 3,044 likes | 1,418 downloads
- **Kind:** Hugging Face model | **Task:** image-text-to-text | **Created:** 2026-09-04
- **Tags:** safetensors, zdtaichu5_0, multimodal, vision-language-model, spatial-reasoning, agent
- **What it is:** a model on the Hugging Face Hub with real community pull -- useful when you need something that already works.
- **Link:** https://huggingface.co/TaichuAI/ZDTaichu5.0-9B

**Added 2026-11-14**

### [zai-org/GLM-5.3](https://huggingface.co/zai-org/GLM-5.3)
- **Stats:** 2,446 likes | 1,853,368 downloads
- **Kind:** Hugging Face model | **Task:** text-generation | **Created:** 2026-08-25
- **Tags:** transformers, safetensors, glm_moe_dsa, text-generation, conversational, en
- **What it is:** a model on the Hugging Face Hub with real community pull -- useful when you need something that already works.
- **Link:** https://huggingface.co/zai-org/GLM-5.3

**Added 2026-11-15**

### [ccore/ThreeJS-3D-Scenes](https://huggingface.co/datasets/ccore/ThreeJS-3D-Scenes)
- **Stats:** 122 likes | 11,902 downloads
- **Kind:** Hugging Face dataset | **Task:** n/a | **Created:** 2026-10-28
- **Tags:** 3d, threejs, code, reasoning, conversational, html
- **What it is:** a dataset on the Hugging Face Hub with real community pull -- useful when you need something that already works.
- **Link:** https://huggingface.co/datasets/ccore/ThreeJS-3D-Scenes

**Added 2026-11-15**

### [codepawl/abo-glb](https://huggingface.co/datasets/codepawl/abo-glb)
- **Stats:** 126 likes | 63,523 downloads
- **Kind:** Hugging Face dataset | **Task:** n/a | **Created:** 2026-11-04
- **Tags:** 3d, gltf, glb, web, three.js, crucible
- **What it is:** a dataset on the Hugging Face Hub with real community pull -- useful when you need something that already works.
- **Link:** https://huggingface.co/datasets/codepawl/abo-glb

**Added 2026-11-15**

### [google/embeddinggemma-2](https://huggingface.co/google/embeddinggemma-2)
- **Stats:** 3,438 likes | 547,326 downloads
- **Kind:** Hugging Face model | **Task:** feature-extraction | **Created:** 2026-09-14
- **Tags:** transformers, safetensors, embedding_gemma2, feature-extraction, embedding, sentence-transformers
- **What it is:** a model on the Hugging Face Hub with real community pull -- useful when you need something that already works.
- **Link:** https://huggingface.co/google/embeddinggemma-2

**Added 2026-11-16**

### [poolside/Laguna-S-2.1](https://huggingface.co/poolside/Laguna-S-2.1)
- **Stats:** 1,080 likes | 488,183 downloads
- **Kind:** Hugging Face model | **Task:** text-generation | **Created:** 2026-07-13
- **Tags:** transformers, safetensors, laguna, text-generation, laguna-s-2.1, vllm
- **What it is:** a model on the Hugging Face Hub with real community pull -- useful when you need something that already works.
- **Link:** https://huggingface.co/poolside/Laguna-S-2.1


## LLMs

**Added 2026-11-14**

### [How much does it cost to run a text game with LLMs](https://dev.to/hiper2d/how-much-does-it-cost-to-run-a-text-game-with-llms-57o7)
- **Author:** Aliaksei Zelianouski | **Published:** Nov 8 | **Read time:** 18 min
- **Community:** 85 reactions, 88 comments -- a top post in #llm
- **Tags:** ai, llm, gamedev, machinelearning
- **Summary:** AI costs are confusing. Providers give you a lot of numbers and nothing to actually know how much you are going to pay in the long run. There is no point in these input/cached/output token prices if you have no idea how many reasoning tokens you'll spend on your tasks. How much will be cached. We are going to review the real-world usage of 27 frontier models.
- **Link:** https://dev.to/hiper2d/how-much-does-it-cost-to-run-a-text-game-with-llms-57o7
