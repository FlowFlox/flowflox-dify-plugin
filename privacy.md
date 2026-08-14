# FlowFlox Dify Provider Privacy

The provider sends only the Dify prompt, selected automatic capability profile,
and user-configured generation parameters to the FlowFlox application URL. Its
encrypted workspace connection token authenticates only the Dify server to the
shared FlowFlox runtime. The provider does not receive app-tool capabilities,
does not send prompts or credentials to any other service, and does not persist
them.
