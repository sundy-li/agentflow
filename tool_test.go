package agentflow

import (
	"errors"
	"fmt"
	"testing"
)

func TestToolRun(t *testing.T) {
	echo := &Tool{
		Name:        "echo",
		Description: "Returns the input unchanged.",
		Func:        func(input string) (string, error) { return input, nil },
	}
	out, err := echo.Run("hello")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if out != "hello" {
		t.Errorf("expected 'hello', got %q", out)
	}
}

func TestToolRunError(t *testing.T) {
	sentinel := errors.New("tool failure")
	bad := &Tool{
		Name: "bad",
		Func: func(_ string) (string, error) { return "", sentinel },
	}
	_, err := bad.Run("x")
	if !errors.Is(err, sentinel) {
		t.Fatalf("expected sentinel error, got %v", err)
	}
}

func TestToolRegistry(t *testing.T) {
	reg := NewToolRegistry()
	reg.Register(&Tool{Name: "a", Func: func(s string) (string, error) { return s + "a", nil }})
	reg.Register(&Tool{Name: "b", Func: func(s string) (string, error) { return s + "b", nil }})

	tool, ok := reg.Get("a")
	if !ok {
		t.Fatal("expected tool 'a' to be registered")
	}
	out, _ := tool.Run("x")
	if out != "xa" {
		t.Errorf("unexpected output: %q", out)
	}

	_, ok = reg.Get("missing")
	if ok {
		t.Fatal("expected missing tool to be absent")
	}

	names := reg.Names()
	if len(names) != 2 {
		t.Errorf("expected 2 names, got %d", len(names))
	}
}

func TestToolRegistryChaining(t *testing.T) {
	reg := NewToolRegistry().
		Register(&Tool{Name: "t1", Func: func(s string) (string, error) { return s, nil }}).
		Register(&Tool{Name: "t2", Func: func(s string) (string, error) { return s, nil }})

	names := reg.Names()
	if len(names) != 2 {
		t.Errorf("expected 2 names after chained register, got %d: %v", len(names), names)
	}

	for _, n := range []string{"t1", "t2"} {
		if _, ok := reg.Get(n); !ok {
			t.Errorf("expected tool %q to be present", n)
		}
	}
}

func TestToolUsedInAgent(t *testing.T) {
	reg := NewToolRegistry()
	reg.Register(&Tool{
		Name: "upper",
		Func: func(s string) (string, error) {
			return fmt.Sprintf("[%s]", s), nil
		},
	})

	agent := AgentFunc(func(ctx *Context) (*Context, error) {
		tool, ok := reg.Get("upper")
		if !ok {
			return ctx, errors.New("tool not found")
		}
		msg, _ := ctx.LastMessage()
		result, err := tool.Run(msg.Content)
		if err != nil {
			return ctx, err
		}
		ctx.Set("tool_result", result)
		return ctx, nil
	})

	ctx := NewContext().AddMessage(RoleUser, "hello")
	out, err := agent.Run(ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if v, _ := out.GetString("tool_result"); v != "[hello]" {
		t.Errorf("unexpected tool result: %q", v)
	}
}
