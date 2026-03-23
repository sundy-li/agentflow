package agentflow

import (
	"errors"
	"testing"
)

// mockProvider is a test LLMProvider.
type mockProvider struct {
	response string
	err      error
}

func (m *mockProvider) Complete(_ *Context, _ string) (string, error) {
	return m.response, m.err
}

func TestLLMAgentRun(t *testing.T) {
	provider := &mockProvider{response: "I am helpful."}
	agent := NewLLMAgent(provider, "You are a helpful assistant.")

	ctx := NewContext()
	ctx.AddMessage(RoleUser, "Hello!")

	out, err := agent.Run(ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Response should be appended as assistant message.
	last, ok := out.LastMessage()
	if !ok {
		t.Fatal("expected at least one message")
	}
	if last.Role != RoleAssistant || last.Content != "I am helpful." {
		t.Errorf("unexpected last message: %+v", last)
	}

	// Response should also be stored under "llm_response".
	v, ok := out.GetString("llm_response")
	if !ok || v != "I am helpful." {
		t.Errorf("unexpected llm_response: %q, ok=%v", v, ok)
	}
}

func TestLLMAgentRunError(t *testing.T) {
	sentinel := errors.New("model error")
	provider := &mockProvider{err: sentinel}
	agent := NewLLMAgent(provider, "")

	ctx := NewContext()
	_, err := agent.Run(ctx)
	if !errors.Is(err, sentinel) {
		t.Fatalf("expected sentinel error, got %v", err)
	}
}

func TestLLMAgentImplementsAgent(t *testing.T) {
	var _ Agent = NewLLMAgent(&mockProvider{}, "")
}
