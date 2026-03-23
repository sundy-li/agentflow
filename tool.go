package agentflow

// Tool represents an external capability that an agent can invoke by name.
// Tools expose a textual interface so they can be described to an LLM and
// called with a plain string argument.
type Tool struct {
	// Name is the unique identifier for the tool.
	Name string

	// Description explains what the tool does.  LLM-backed agents typically
	// include this in the system prompt so the model knows when to call it.
	Description string

	// Func is the implementation that processes the input and returns output.
	Func func(input string) (string, error)
}

// Run calls the tool with the given input string.
func (t *Tool) Run(input string) (string, error) {
	return t.Func(input)
}

// ToolRegistry holds a collection of named tools and provides convenience
// methods for looking them up.
type ToolRegistry struct {
	tools map[string]*Tool
}

// NewToolRegistry returns an empty ToolRegistry.
func NewToolRegistry() *ToolRegistry {
	return &ToolRegistry{tools: make(map[string]*Tool)}
}

// Register adds a Tool to the registry.
func (r *ToolRegistry) Register(t *Tool) *ToolRegistry {
	r.tools[t.Name] = t
	return r
}

// Get returns the Tool with the given name, or (nil, false) if not found.
func (r *ToolRegistry) Get(name string) (*Tool, bool) {
	t, ok := r.tools[name]
	return t, ok
}

// Names returns the names of all registered tools.
func (r *ToolRegistry) Names() []string {
	names := make([]string, 0, len(r.tools))
	for name := range r.tools {
		names = append(names, name)
	}
	return names
}
