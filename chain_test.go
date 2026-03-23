package agentflow

import (
	"errors"
	"fmt"
	"testing"
)

func appendAgent(label string) Agent {
	return AgentFunc(func(ctx *Context) (*Context, error) {
		prev, _ := ctx.GetString("trace")
		ctx.Set("trace", prev+label)
		return ctx, nil
	})
}

func TestChainRunsInOrder(t *testing.T) {
	chain := NewChain(
		appendAgent("A"),
		appendAgent("B"),
		appendAgent("C"),
	)

	ctx := NewContext()
	out, err := chain.Run(ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if trace, _ := out.GetString("trace"); trace != "ABC" {
		t.Errorf("expected trace=ABC, got %q", trace)
	}
}

func TestChainAdd(t *testing.T) {
	chain := NewChain(appendAgent("X"))
	chain.Add(appendAgent("Y"), appendAgent("Z"))

	ctx := NewContext()
	out, err := chain.Run(ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if trace, _ := out.GetString("trace"); trace != "XYZ" {
		t.Errorf("expected trace=XYZ, got %q", trace)
	}
}

func TestChainStopsOnError(t *testing.T) {
	sentinel := errors.New("step failed")
	chain := NewChain(
		appendAgent("A"),
		AgentFunc(func(ctx *Context) (*Context, error) {
			return ctx, sentinel
		}),
		appendAgent("C"),
	)

	ctx := NewContext()
	out, err := chain.Run(ctx)
	if !errors.Is(err, sentinel) {
		t.Fatalf("expected sentinel error, got %v", err)
	}
	// Step A should have run, step C should not.
	trace, _ := out.GetString("trace")
	if trace != "A" {
		t.Errorf("expected trace=A after error, got %q", trace)
	}
}

func TestChainErrorWrapping(t *testing.T) {
	inner := fmt.Errorf("inner")
	chain := NewChain(AgentFunc(func(ctx *Context) (*Context, error) {
		return ctx, inner
	}))
	_, err := chain.Run(NewContext())
	if !errors.Is(err, inner) {
		t.Fatalf("expected inner error in chain, got: %v", err)
	}
}

func TestChainEmpty(t *testing.T) {
	chain := NewChain()
	ctx := NewContext()
	ctx.Set("x", 1)
	out, err := chain.Run(ctx)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	v, _ := out.Get("x")
	if v.(int) != 1 {
		t.Errorf("expected context to be unchanged, got %v", v)
	}
}
