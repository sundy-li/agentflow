package agentflow

// Agent is the core interface implemented by every processing unit in an
// agentflow pipeline.  Run receives the current Context and returns an updated
// Context (which may be the same pointer or a new one) together with any error
// that occurred.
type Agent interface {
	Run(ctx *Context) (*Context, error)
}

// AgentFunc is a function that implements the Agent interface.  It allows
// plain functions to be used wherever an Agent is expected.
type AgentFunc func(ctx *Context) (*Context, error)

// Run implements Agent.
func (f AgentFunc) Run(ctx *Context) (*Context, error) {
	return f(ctx)
}
