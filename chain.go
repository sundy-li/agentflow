package agentflow

import "fmt"

// Chain runs a fixed sequence of agents one after the other, passing the
// Context returned by each agent as the input to the next.  It implements
// Agent itself so chains can be nested inside flows or other chains.
type Chain struct {
	agents []Agent
}

// NewChain creates a Chain that will execute the given agents in order.
func NewChain(agents ...Agent) *Chain {
	return &Chain{agents: agents}
}

// Add appends one or more agents to the chain and returns the Chain so that
// calls can be chained.
func (c *Chain) Add(agents ...Agent) *Chain {
	c.agents = append(c.agents, agents...)
	return c
}

// Run implements Agent.  Each agent in the chain is executed in order; the
// first error causes the chain to stop and return the error together with the
// Context as it stood at that point.
func (c *Chain) Run(ctx *Context) (*Context, error) {
	var err error
	for i, agent := range c.agents {
		ctx, err = agent.Run(ctx)
		if err != nil {
			return ctx, fmt.Errorf("chain step %d: %w", i, err)
		}
	}
	return ctx, nil
}
