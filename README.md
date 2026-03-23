# agentflow

A lightweight Go framework for building and orchestrating AI agent pipelines.

## Overview

`agentflow` provides a small set of composable primitives that make it easy to
wire together LLM calls, tool invocations, and custom logic into structured
workflows:

| Primitive | Description |
|-----------|-------------|
| **Agent** | The core interface – receives a `*Context` and returns an updated `*Context`. |
| **Context** | Carries conversation messages and arbitrary key-value data between agents. |
| **Chain** | Runs a fixed sequence of agents one after another. |
| **Flow** | A graph of named `Step`s with conditional routing between them. |
| **Tool** | A callable capability (e.g. a web search) backed by a plain Go function. |
| **LLMProvider** | Interface for plugging in any language model backend. |

## Installation

```bash
go get github.com/sundy-li/agentflow
```

## Quick start

```go
package main

import (
    "fmt"
    "github.com/sundy-li/agentflow"
)

func main() {
    // Build a simple two-step chain.
    greet := agentflow.AgentFunc(func(ctx *agentflow.Context) (*agentflow.Context, error) {
        ctx.AddMessage(agentflow.RoleUser, "Hello, world!")
        return ctx, nil
    })

    echo := agentflow.AgentFunc(func(ctx *agentflow.Context) (*agentflow.Context, error) {
        msg, _ := ctx.LastMessage()
        ctx.Set("result", "Echo: "+msg.Content)
        return ctx, nil
    })

    chain := agentflow.NewChain(greet, echo)
    ctx, err := chain.Run(agentflow.NewContext())
    if err != nil {
        panic(err)
    }

    result, _ := ctx.GetString("result")
    fmt.Println(result) // Echo: Hello, world!
}
```

## Flow with conditional routing

```go
flow := agentflow.NewFlow().
    AddStep(&agentflow.Step{
        Name:  "classify",
        Agent: classifyAgent,
        Next: func(ctx *agentflow.Context) string {
            if sentiment, _ := ctx.GetString("sentiment"); sentiment == "positive" {
                return "handle_positive"
            }
            return "handle_negative"
        },
    }).
    AddStep(&agentflow.Step{Name: "handle_positive", Agent: positiveAgent}).
    AddStep(&agentflow.Step{Name: "handle_negative", Agent: negativeAgent})

ctx, err := flow.Run(agentflow.NewContext())
```

## LLM integration

Implement the `LLMProvider` interface to connect any language model:

```go
type MyProvider struct{ /* client */ }

func (p *MyProvider) Complete(ctx *agentflow.Context, systemPrompt string) (string, error) {
    // call your LLM API using ctx.Messages
    return "model response", nil
}

agent := agentflow.NewLLMAgent(&MyProvider{}, "You are a helpful assistant.")
ctx, err := agent.Run(agentflow.NewContext().AddMessage(agentflow.RoleUser, "Hi!"))
```

## Tool registry

```go
reg := agentflow.NewToolRegistry()
reg.Register(&agentflow.Tool{
    Name:        "search",
    Description: "Search the web for a query.",
    Func: func(query string) (string, error) {
        // perform search ...
        return "results", nil
    },
})

tool, _ := reg.Get("search")
result, _ := tool.Run("agentflow Go framework")
```

## License

MIT

