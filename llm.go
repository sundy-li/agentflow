package agentflow

// LLMProvider is the interface that wraps calls to a language model backend.
// Implementations can target any provider (OpenAI, Anthropic, Ollama, etc.).
type LLMProvider interface {
	// Complete sends the conversation history held in ctx to the language
	// model together with an optional additional system prompt and returns
	// the model's response text.
	Complete(ctx *Context, systemPrompt string) (string, error)
}

// LLMAgent is an Agent that delegates to an LLMProvider.  It appends the
// model's response as an assistant message to the Context and stores it under
// the "llm_response" data key.
type LLMAgent struct {
	Provider     LLMProvider
	SystemPrompt string
}

// NewLLMAgent creates a new LLMAgent backed by the given provider.
func NewLLMAgent(provider LLMProvider, systemPrompt string) *LLMAgent {
	return &LLMAgent{Provider: provider, SystemPrompt: systemPrompt}
}

// Run implements Agent.
func (a *LLMAgent) Run(ctx *Context) (*Context, error) {
	response, err := a.Provider.Complete(ctx, a.SystemPrompt)
	if err != nil {
		return ctx, err
	}
	ctx.AddMessage(RoleAssistant, response)
	ctx.Set("llm_response", response)
	return ctx, nil
}
