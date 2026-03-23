package agentflow

import (
	"errors"
	"testing"
)

func stepAgent(name string) Agent {
	return AgentFunc(func(ctx *Context) (*Context, error) {
		prev, _ := ctx.GetString("visited")
		ctx.Set("visited", prev+name+",")
		return ctx, nil
	})
}

func TestFlowLinear(t *testing.T) {
	flow := NewFlow().
		AddStep(&Step{Name: "a", Agent: stepAgent("A"), Next: func(_ *Context) string { return "b" }}).
		AddStep(&Step{Name: "b", Agent: stepAgent("B"), Next: func(_ *Context) string { return "c" }}).
		AddStep(&Step{Name: "c", Agent: stepAgent("C")})

	out, err := flow.Run(NewContext())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if v, _ := out.GetString("visited"); v != "A,B,C," {
		t.Errorf("expected A,B,C, got %q", v)
	}
}

func TestFlowConditionalRouting(t *testing.T) {
	// Route to "yes" or "no" based on a flag in the context.
	flow := NewFlow().
		AddStep(&Step{
			Name:  "check",
			Agent: AgentFunc(func(ctx *Context) (*Context, error) { return ctx, nil }),
			Next: func(ctx *Context) string {
				v, _ := ctx.Get("go_yes")
				if v == true {
					return "yes"
				}
				return "no"
			},
		}).
		AddStep(&Step{Name: "yes", Agent: stepAgent("YES")}).
		AddStep(&Step{Name: "no", Agent: stepAgent("NO")})

	t.Run("yes branch", func(t *testing.T) {
		ctx := NewContext()
		ctx.Set("go_yes", true)
		out, err := flow.Run(ctx)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if v, _ := out.GetString("visited"); v != "YES," {
			t.Errorf("expected YES, got %q", v)
		}
	})

	t.Run("no branch", func(t *testing.T) {
		ctx := NewContext()
		ctx.Set("go_yes", false)
		out, err := flow.Run(ctx)
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if v, _ := out.GetString("visited"); v != "NO," {
			t.Errorf("expected NO, got %q", v)
		}
	})
}

func TestFlowUnknownStep(t *testing.T) {
	flow := NewFlow().
		AddStep(&Step{
			Name:  "start",
			Agent: stepAgent("S"),
			Next:  func(_ *Context) string { return "ghost" },
		})

	_, err := flow.Run(NewContext())
	if err == nil {
		t.Fatal("expected error for unknown step")
	}
}

func TestFlowAgentError(t *testing.T) {
	sentinel := errors.New("step error")
	flow := NewFlow().
		AddStep(&Step{
			Name:  "fail",
			Agent: AgentFunc(func(ctx *Context) (*Context, error) { return ctx, sentinel }),
		})

	_, err := flow.Run(NewContext())
	if !errors.Is(err, sentinel) {
		t.Fatalf("expected sentinel error, got %v", err)
	}
}

func TestFlowEmpty(t *testing.T) {
	flow := NewFlow()
	ctx := NewContext()
	ctx.Set("x", 99)
	out, err := flow.Run(ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if v, _ := out.Get("x"); v.(int) != 99 {
		t.Errorf("expected unchanged context, got %v", v)
	}
}

func TestFlowSetStart(t *testing.T) {
	flow := NewFlow().
		AddStep(&Step{Name: "skip", Agent: stepAgent("SKIP")}).
		AddStep(&Step{Name: "real", Agent: stepAgent("REAL")})
	flow.SetStart("real")

	out, err := flow.Run(NewContext())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if v, _ := out.GetString("visited"); v != "REAL," {
		t.Errorf("expected REAL, got %q", v)
	}
}

func TestFlowImplementsAgent(t *testing.T) {
	var _ Agent = NewFlow()
}
