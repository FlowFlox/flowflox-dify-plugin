# FlowFlox Tools for Dify

FlowFlox Tools is the app-scoped API-action plugin. It is separate from the
FlowFlox model provider: it does not select a model and it never exposes
FlowFlox database, storage, cloud, or tenant credentials.

## App connection and revocation

Install the plugin once in Dify. Do **not** authorize it from a global provider
page. Each Dify app receives its own narrow FlowFlox capability.

1. In **FlowFlox → AI Infrastructure → Connections**, issue a one-time Dify
   authorization code for the saved Dify app ID and its API-only credential.
   The `ffx_dac_…` code expires after 10 minutes and is usable once.
2. In that app, add **Authorize FlowFlox app** as an unconnected direct Tool
   node. Paste the one-time code and run that setup step once. It exchanges
   the code for a narrow `ffx_app_…` capability; neither a durable service key
   nor the capability reaches an Agent or an Answer node. Remove the setup
   node after the success message.
3. In that app’s Agent tool settings, bind **Dify app context** on both
   **FlowFlox API catalog** and **FlowFlox action gateway** to the system
   variable `sys.app_id`. This is a configuration value, not an LLM parameter:
   the model never sees or selects an app ID.

Dify's stock FunctionCalling Agent does not currently forward `session.app_id`
to a plugin tool. The form-only `sys.app_id` binding preserves the same
app-owned context across that Dify gap, without a shared FlowFlox key.

```text
revoke app credential for Dify App A  →  App A's FlowFlox actions stop
                                        App B stays connected with its own credential
```

Every catalogue lookup and action is checked again against that capability,
its parent key, its tenant/company policy, and its explicit API grants.

## Open-ended AI: one intent-driven planner

This is the normal approach for an assistant that must understand varied
phrasing, languages, follow-up requests, and multi-step work:

```text
User input → Intent planner Agent (approved app toolbox) → Answer
                     ↳ API catalogue → eligible action → planner again
                     ↳ current weather → planner again
```

The planner reads the full meaning and conversation, then decides whether a
tool is needed. It may call several eligible tools in sequence, use each
result as context, and write one final answer. Tool descriptions and JSON
schemas define the capability contract; there are no static keyword triggers
such as `weather` or `runtime`, and raw JSON never goes directly to the user.

Use **FlowFlox API catalog** before a FlowFlox action when the planner does not
already have the approved operation and its input schema. Then use
**FlowFlox action gateway** only with an exact catalogued operation. The
gateway returns safe structured data for the planner’s next reasoning step.

## Fixed operational processes

Use separate visible **FlowFlox conditional API action** nodes only where the
sequence is deliberately fixed and reviewable, for example:

```text
approve invoice → charge payment → issue receipt
```

Each node runs only when its explicit Dify branch reaches it. Bind its
**Dify app context** field to `sys.app_id`; it does not use a global key. Do
not create a router class or static trigger list for every normal API.

## Security

- The installed plugin is code only; it has no shared FlowFlox authorization.
- A setup node accepts only an expiring, single-use `ffx_dac_…` code—not a
  durable `ffx_svc_…` service key. This avoids turning a Dify run trace into
  a reusable credential leak.
- Plugin storage retains only the narrow app capability, namespaced by Dify app
  ID. Agent tools receive the app ID from their form-only `sys.app_id` binding.
- The capability can call only explicitly granted FlowFlox **API** actions. It
  cannot use model runtime, knowledge, SQL, storage, or cloud routes.
- An API-only FlowFlox credential can authorize one Dify app, making the
  revocation and audit boundary app-specific.
