package agentflow

// Role constants for message authors.
const (
	RoleSystem    = "system"
	RoleUser      = "user"
	RoleAssistant = "assistant"
	RoleTool      = "tool"
)

// Message represents a single message in a conversation.
type Message struct {
	Role    string
	Content string
}

// Context carries conversation history and arbitrary key-value data between
// agents in a flow. Every agent receives a *Context and returns a (possibly
// new) *Context so that state flows naturally through the pipeline.
type Context struct {
	Messages []Message
	Data     map[string]any
}

// NewContext returns an empty Context ready for use.
func NewContext() *Context {
	return &Context{
		Messages: make([]Message, 0),
		Data:     make(map[string]any),
	}
}

// Clone returns a shallow copy of the Context.  Message slice and Data map
// entries are copied so that modifications to the clone do not affect the
// original.
func (c *Context) Clone() *Context {
	clone := &Context{
		Messages: make([]Message, len(c.Messages)),
		Data:     make(map[string]any, len(c.Data)),
	}
	copy(clone.Messages, c.Messages)
	for k, v := range c.Data {
		clone.Data[k] = v
	}
	return clone
}

// AddMessage appends a message with the given role and content.
func (c *Context) AddMessage(role, content string) *Context {
	c.Messages = append(c.Messages, Message{Role: role, Content: content})
	return c
}

// LastMessage returns the most recent message, or the zero value if there are
// none.
func (c *Context) LastMessage() (Message, bool) {
	if len(c.Messages) == 0 {
		return Message{}, false
	}
	return c.Messages[len(c.Messages)-1], true
}

// Set stores a value under key in the context data map.
func (c *Context) Set(key string, value any) *Context {
	c.Data[key] = value
	return c
}

// Get retrieves a value from the context data map.
func (c *Context) Get(key string) (any, bool) {
	v, ok := c.Data[key]
	return v, ok
}

// GetString retrieves a string value from the context data map.  It returns
// ("", false) when the key is absent or the value is not a string.
func (c *Context) GetString(key string) (string, bool) {
	v, ok := c.Data[key]
	if !ok {
		return "", false
	}
	s, ok := v.(string)
	return s, ok
}
