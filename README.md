# FlowFlox for Dify

Bring FlowFlox into your Dify workspace.

Choose what your app needs and keep building:

- Chat
- Code
- Reasoning
- Tools
- Vision

FlowFlox takes care of the details in the background.

## Get started

For an assistant that needs both a model and approved live actions, create a
runtime credential for the model provider in **AI Infrastructure →
Connections**:

1. Select **Chat Completions**.
2. Choose the smallest valid data scope.
3. Paste that credential into the provider's encrypted **FlowFlox runtime
   service credential** field.
4. Create a separate API-only credential for **FlowFlox Tools** below. It is
   never pasted into Dify; FlowFlox uses it only to issue an app-specific,
   one-time authorization code.
5. Choose the capability that fits your app, then build and publish.

The credential is still scoped: it never gives the workspace direct Supabase,
storage, SQL, or knowledge access. FlowFlox decides the live compatible
runtime. A scoped Dify connection always uses automatic routing; model
comparison is available only to a FlowFlox administrator.

Knowledge is configured in **Dify Studio → Knowledge**. Dify owns the
documents, parsing, chunking, embeddings, retrieval, reranking, and Knowledge
Retrieval nodes. FlowFlox deliberately does not inject a second RAG context
into a Dify Chatflow. Use a separately scoped FlowFlox tool only when the
Chatflow needs live tenant data, a signed file link, or an approved report.

## Live FlowFlox actions

This model provider remains runtime-only. It can share the signed assistant
credential with the tool plugin, but it never becomes a data connector.

For approved live actions, install **FlowFlox Tools** as a separate Dify
plugin. Issue a one-time app authorization code in FlowFlox for the saved
Dify app ID, then run **Authorize FlowFlox app** once as an unconnected setup
node. Do not paste a durable credential into Dify or configure the tools from
a global plugin authorization panel. In the Agent's FlowFlox tool settings,
bind the form-only **Dify app context** value to `sys.app_id`; the model does
not see or decide that value. Attach **FlowFlox API catalog** and **FlowFlox
action gateway** to an Agent for intent-driven tool use, or put
**FlowFlox conditional API action** nodes after Dify router/If-Else branches
when every decision and API step must be visible on the canvas. APIs are never
a required first step: the request or an explicit branch must call for one.

For an administrator-only one-off comparison, choose **Chosen model — Chat**,
then enter a model ID in that node's **Model ID to try** setting. Leave it
blank to let Flox choose automatically. A scoped service credential always
uses Automatic, by design.
