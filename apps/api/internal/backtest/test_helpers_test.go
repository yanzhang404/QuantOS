package backtest

import (
	"context"
	"encoding/json"
	"time"
)

func validSubmission() Submission {
	start := "2025-01-01T00:00:00Z"
	end := "2026-01-01T00:00:00Z"
	return Submission{
		SchemaVersion:  SchemaVersion,
		IdempotencyKey: "test-20260729-0001",
		Dataset: DatasetRef{
			Version:       "024f23d9a629502e",
			ContentSHA256: "024f23d9a629502eabf7c8186735938cb585ab76286b072e20ded76c1b4bc7b3",
			Symbol:        "BTCUSDT",
			Interval:      "4h",
			DataStart:     &start,
			DataEnd:       &end,
		},
		Strategy: StrategyRef{
			Name:    "donchian-atr",
			Version: "1.0.0",
			Parameters: map[string]any{
				"entry_period":             json.Number("55"),
				"exit_period":              json.Number("20"),
				"atr_period":               json.Number("20"),
				"target_annual_volatility": "0.20",
				"max_exposure":             "1",
				"rebalance_threshold":      "0.05",
			},
		},
		Config: Config{
			InitialCash:       "100000",
			FeeBPS:            "10",
			SlippageBPS:       "5",
			MaxTargetExposure: "1",
			LiquidateAtEnd:    true,
		},
	}
}

type blockingRunner struct {
	started chan Submission
	result  chan runnerReply
}

type runnerReply struct {
	result RunResult
	err    error
}

func (r *blockingRunner) Run(ctx context.Context, request Submission) (RunResult, error) {
	select {
	case r.started <- request:
	case <-ctx.Done():
		return RunResult{}, ctx.Err()
	}
	select {
	case reply := <-r.result:
		return reply.result, reply.err
	case <-ctx.Done():
		return RunResult{}, ctx.Err()
	}
}

func waitForStatus(store *TaskStore, taskID, status string) Task {
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		task, err := store.Get(taskID)
		if err == nil && task.Status == status {
			return task
		}
		time.Sleep(time.Millisecond)
	}
	panic("task did not reach status " + status)
}
