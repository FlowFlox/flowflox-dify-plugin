# FlowFlox Development for Dify

This is a development-only Dify model-provider plugin. It is deliberately a
separate plugin from normal **FlowFlox**, so its active credential, package
updates, and model routing cannot alter a production or shared connection.

Use it only with:

- FlowFlox development or staging runtime URLs;
- a development-scoped `ffx_svc_…` runtime credential; and
- development Dify applications.

It supplies chat, code, reasoning, tool-calling, vision, and embedding model
profiles. It does not provide database, browser, repository, shell, cloud, or
production-data access.

## Release and update boundary

The plugin has its own Dify plugin identifier,
`flowflox/flowflox-development`, and its own signing key. It must be released
through the development GitHub release line. Do not package it under the normal
FlowFlox plugin identifier or sign it with the normal provider key.
