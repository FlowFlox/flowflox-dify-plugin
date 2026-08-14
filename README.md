# FlowFlox for Dify

Bring FlowFlox into your Dify workspace.

This package exposes only the normal **FlowFlox** provider. Its stable public
gateway selects a currently compatible model route at request time; neither
the Dify connection nor this plugin is tied to a RunPod, private-network, or
individual model endpoint.

There is one FlowFlox model provider. Development, customer, and product
separation belongs in the Dify apps and workflows that use it—not in a second
provider or a second embedding index.

Choose what your app needs and keep building:

- Chat
- Code
- Reasoning
- Tools
- Vision
- Embeddings for Dify Knowledge

FlowFlox takes care of the details in the background.

## Streaming replies

FlowFlox streams answer text from a compatible runtime through Dify to the
Flox chat as it is generated. The chat shows a clear working state before the
first token arrives, then renders each response incrementally. It does not
expose private model chain-of-thought; the visible status is limited to safe
workflow and tool progress.

## Get started

For an assistant that needs both a model and approved live actions:

1. Set the normal FlowFlox provider's connection URL to
   `https://gateway.flowflox.dev/v1`.
2. Configure its encrypted **Dify workspace connection token** with the
   platform-managed `AI_INTERNAL_INTEGRATION_TOKEN`. This is one server-to-
   server Dify connection for the workspace, not a user credential and not a
   customer, developer, or tool credential.
3. For each Dify app that needs actions, create a least-privileged app-tool
   credential in **AI Infrastructure → Connections**, assign its approved
   APIs in a FlowFlox tool collection, then issue that app's one-time
   authorization code.
4. Choose the model capability that fits the Dify app, then build and publish.

The connection is still scoped: it never gives the workspace direct Supabase,
storage, SQL, or knowledge access. FlowFlox decides the live compatible
runtime. A Dify workspace connection always uses automatic routing; model
comparison is available only to a FlowFlox administrator.

Knowledge is configured in **Dify Studio → Knowledge**. Dify owns the
documents, parsing, chunking, embeddings, retrieval, reranking, and Knowledge
Retrieval nodes. FlowFlox deliberately does not inject a second RAG context
into a Dify Chatflow. Use a separately scoped FlowFlox tool only when the
Chatflow needs live tenant data, a signed file link, or an approved report.

### Use the shared FlowFlox embedding pool for Dify Knowledge

After the provider is updated, choose **FlowFlox → EmbeddingGemma 300M** as
the embedding model for every Dify dataset that should use the shared pool.
The normal provider uses the same platform-managed workspace connection for
both document and query embeddings; Dify never receives a RunPod URL, model
secret, or a per-app service credential. Re-index existing documents only when
changing the embedding model itself—not when adding another Dify app.

## Live FlowFlox actions

This model provider remains runtime-only. It never receives an app-tool
credential and it never becomes a data connector.

For approved live actions, install **[FlowFlox Tools](https://github.com/FlowFlox/flowflox-dify-tools)** and authorize each saved
Dify app with its own one-time code. Dify currently requires model providers
and tool providers to be separate extension types; this is one FlowFlox model
provider plus one app-scoped tools extension, not two model providers and not
two GPU routes. In the Agent's FlowFlox tool settings, bind the form-only
**Dify app context** value to `sys.app_id`; the model does not see or decide
that value. Attach **FlowFlox MCP tool catalog** and **FlowFlox MCP action
gateway** to an Agent for intent-driven tool use, or put **FlowFlox conditional
API action** nodes after Dify router/If-Else branches when every decision and
API step must be visible on the canvas. APIs are never a required first step:
the request or an explicit branch must call for one.

For an administrator-only one-off comparison, choose **Chosen model — Chat**,
then enter a model ID in that node's **Model ID to try** setting. Leave it
blank to let Flox choose automatically. A Dify workspace connection always
uses Automatic, by design.
