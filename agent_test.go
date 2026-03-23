package agentflow

import (
	"errors"
	"testing"
)

func TestAgentFunc(t *testing.T) {
	agent := AgentFunc(func(ctx *Context) (*Context, error) {
		ctx.Set("visited", true)
		return ctx, nil
	})

	ctx := NewContext()
	out, err := agent.Run(ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	v, ok := out.Get("visited")
	if !ok || v != true {
		t.Errorf("expected visited=true, got %v (ok=%v)", v, ok)
	}
}

func TestAgentFuncError(t *testing.T) {
	sentinel := errors.New("boom")
	agent := AgentFunc(func(ctx *Context) (*Context, error) {
		return ctx, sentinel
	})

	ctx := NewContext()
	_, err := agent.Run(ctx)
	if !errors.Is(err, sentinel) {
		t.Fatalf("expected sentinel error, got %v", err)
	}
}
