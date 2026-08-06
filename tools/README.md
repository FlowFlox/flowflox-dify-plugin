# FlowFlox Tools for Dify

This is the separate FlowFlox action integration. It is not the FlowFlox model
provider and it never chooses or runs a model.

Paste one scoped FlowFlox signed key. The plugin loads only the approved APIs
granted to that key. It then gives a Dify canvas two complementary ways to use
them: visible, individually configured action nodes and an optional dynamic
gateway for AI-directed action loops.

## Install and connect

1. In Dify, choose **Plugins → Install → GitHub**.
2. Enter `https://github.com/FlowFlox/flowflox-dify-plugin`.
3. Select the `tools-v0.2.0` release and the signed FlowFlox Tools package.
4. Open **FlowFlox Tools** and paste a FlowFlox `ffx_svc_…` signed key.
5. Keep the existing FlowFlox model provider selected only where the canvas
   needs AI reasoning.

There is no server URL, header, client ID, OAuth flow, or credential per API.
The signed key is the only connection setting. It determines the live action
picker and is checked again on every action call.

## Build a visible action chain

Drop **FlowFlox API action** onto the Dify canvas once for each action that
should be visible in that workflow. Its **FlowFlox action** picker is loaded
from the signed key at configuration time—there is no typing or maintaining a
separate operation list.

Bind the `data` output from one action node to the **Input** of the next action
node. Every action returns the same safe contract:

```text
ok          whether the call completed
operation   the granted action that ran
data        structured output for the next node
text        text representation of the result
error       safe failure detail when ok is false
```

This makes these valid canvas patterns without adding a tool per API:

```text
User Input → API action: Validate → API action: Create → AI adapter → Answer
User Input → API action: Lookup → API action: Enrich → API action: Notify
```

Use the Dify conditional node on `ok` when a failed API action needs a recovery
path. Use the output from any action as the input to another action, an LLM, a
code node, or a loop.

## Let the AI choose an action at run time

For an open-ended loop, use the two existing generic tools rather than adding
hundreds of actions to an Agent toolbox:

1. **FlowFlox API catalog** returns only the actions that the signed key may
   use, with their input schemas.
2. **FlowFlox action gateway** takes the chosen operation and a JSON input
   object, verifies that grant again, and returns the same action contract.

Put the adapter, catalog/gateway, and a Dify Loop in the workflow only when the
AI must choose its next action dynamically. The model can call the gateway more
than once; each call remains scoped by the credential. This is for a large
catalogue. A visual action chain is for the small, intentional subset of
actions that a particular workflow owns.

The plugin does not turn a model into a data connector and it does not bundle
all available APIs into every workflow. Each Dify workflow chooses either
explicit action nodes, a controlled dynamic loop, or both.

## Security

The key is stored in Dify's encrypted credential field. FlowFlox verifies the
credential and exact API grant on every catalogue lookup and every call. The
plugin cannot reach raw SQL, Supabase, cloud storage, or cloud credentials.
Tenant and company access always comes from the signed key, never from a tool
parameter.
