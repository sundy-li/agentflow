package agentflow

import "fmt"

// Step is a named node inside a Flow.  It wraps an Agent and optionally
// declares the name of the next step to run via a routing function.  When
// Next is nil (or returns ""), execution stops after this step.
type Step struct {
	// Name uniquely identifies the step within a Flow.
	Name string

	// Agent is the processing unit executed at this step.
	Agent Agent

	// Next is an optional function that inspects the Context produced by
	// Agent.Run and returns the name of the next step to execute.  Returning
	// an empty string ends the flow.
	Next func(ctx *Context) string
}

// Flow orchestrates a directed graph of Steps.  Execution starts at the
// registered start step and follows the routing decisions returned by each
// step's Next function.
//
// Flow implements Agent so it can be composed with other agents.
type Flow struct {
	steps map[string]*Step
	start string
}

// NewFlow returns an empty Flow.
func NewFlow() *Flow {
	return &Flow{
		steps: make(map[string]*Step),
	}
}

// AddStep registers a step with the flow.  The first step added becomes the
// default start step unless SetStart has been called.  AddStep returns the
// Flow so calls can be chained.
func (f *Flow) AddStep(step *Step) *Flow {
	f.steps[step.Name] = step
	if f.start == "" {
		f.start = step.Name
	}
	return f
}

// SetStart designates the step with the given name as the entry point of the
// flow.
func (f *Flow) SetStart(name string) *Flow {
	f.start = name
	return f
}

// Run implements Agent.  It executes the flow starting from the start step,
// following the Next routing functions until a step returns "" or no Next
// function is defined.
func (f *Flow) Run(ctx *Context) (*Context, error) {
	if f.start == "" {
		return ctx, nil
	}

	current := f.start
	for current != "" {
		step, ok := f.steps[current]
		if !ok {
			return ctx, fmt.Errorf("agentflow: step %q not found", current)
		}

		var err error
		ctx, err = step.Agent.Run(ctx)
		if err != nil {
			return ctx, fmt.Errorf("agentflow: step %q failed: %w", current, err)
		}

		if step.Next != nil {
			current = step.Next(ctx)
		} else {
			current = ""
		}
	}

	return ctx, nil
}
