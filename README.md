# Flox for Dify

Flox is the FlowFlox AI. In Dify, choose the Flox option that matches the task
and Flox finds a ready, compatible AI to do the work.

Flox options:

- `Flox — Chat`
- `Flox — Code`
- `Flox — Reasoning`
- `Flox — Tools`
- `Flox — Vision`

None of these profiles identifies a model, deployment, GPU, or provider. If a
compatible deployment stops, the next request routes to another live compatible
deployment. A profile cannot be configured if the FlowFlox model registry has
no live model with its required capabilities.

## Install in Dify

1. Package this directory with the Dify Plugin CLI and install the package in
   Dify's Plugin Management page.
2. Configure the FlowFlox provider once with `https://gateway.flowflox.dev/v1`
   and the server-only internal integration credential.
3. Replace the workflow HTTP node with a Dify LLM node.
4. Select `Flox — Chat` for this knowledge assistant and connect
   it directly to the Answer node.

The workflow must not select a raw Qwen/RunPod model. The provider always calls
FlowFlox's runtime-only gateway and sends a capability requirement alongside
the request.
