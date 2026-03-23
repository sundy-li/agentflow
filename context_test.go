package agentflow

import (
	"testing"
)

func TestNewContext(t *testing.T) {
	ctx := NewContext()
	if ctx.Messages == nil {
		t.Fatal("expected Messages to be initialised")
	}
	if ctx.Data == nil {
		t.Fatal("expected Data to be initialised")
	}
}

func TestContextAddMessage(t *testing.T) {
	ctx := NewContext()
	ctx.AddMessage(RoleUser, "hello")
	ctx.AddMessage(RoleAssistant, "hi there")

	if len(ctx.Messages) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(ctx.Messages))
	}
	if ctx.Messages[0].Role != RoleUser || ctx.Messages[0].Content != "hello" {
		t.Errorf("unexpected first message: %+v", ctx.Messages[0])
	}
	if ctx.Messages[1].Role != RoleAssistant || ctx.Messages[1].Content != "hi there" {
		t.Errorf("unexpected second message: %+v", ctx.Messages[1])
	}
}

func TestContextLastMessage(t *testing.T) {
	ctx := NewContext()
	if _, ok := ctx.LastMessage(); ok {
		t.Fatal("expected no last message on empty context")
	}
	ctx.AddMessage(RoleUser, "ping")
	msg, ok := ctx.LastMessage()
	if !ok {
		t.Fatal("expected a last message")
	}
	if msg.Content != "ping" {
		t.Errorf("unexpected last message content: %q", msg.Content)
	}
}

func TestContextSetGet(t *testing.T) {
	ctx := NewContext()
	ctx.Set("answer", 42)
	v, ok := ctx.Get("answer")
	if !ok {
		t.Fatal("expected key to be present")
	}
	if v.(int) != 42 {
		t.Errorf("unexpected value: %v", v)
	}

	_, ok = ctx.Get("missing")
	if ok {
		t.Fatal("expected missing key to be absent")
	}
}

func TestContextGetString(t *testing.T) {
	ctx := NewContext()
	ctx.Set("name", "agentflow")
	s, ok := ctx.GetString("name")
	if !ok || s != "agentflow" {
		t.Errorf("unexpected string value: %q, ok=%v", s, ok)
	}

	ctx.Set("number", 7)
	_, ok = ctx.GetString("number")
	if ok {
		t.Fatal("expected GetString to return false for non-string value")
	}
}

func TestContextClone(t *testing.T) {
	ctx := NewContext()
	ctx.AddMessage(RoleUser, "original")
	ctx.Set("key", "value")

	clone := ctx.Clone()

	// Mutations to clone must not affect the original.
	clone.AddMessage(RoleAssistant, "reply")
	clone.Set("key", "changed")

	if len(ctx.Messages) != 1 {
		t.Errorf("original messages were mutated; got %d", len(ctx.Messages))
	}
	v, _ := ctx.GetString("key")
	if v != "value" {
		t.Errorf("original data was mutated; got %q", v)
	}
}
