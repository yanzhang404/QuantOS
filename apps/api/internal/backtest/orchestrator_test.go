package backtest

import (
	"context"
	"testing"
	"time"
)

func TestOrchestratorRunsTaskAndPersistsResult(t *testing.T) {
	now := time.Date(2026, 7, 29, 12, 0, 0, 0, time.UTC)
	clock := func() time.Time {
		now = now.Add(time.Second)
		return now
	}
	store, err := OpenTaskStore(t.TempDir(), clock)
	if err != nil {
		t.Fatal(err)
	}
	runner := &blockingRunner{
		started: make(chan Submission, 1),
		result:  make(chan runnerReply, 1),
	}
	orchestrator := NewOrchestrator(store, runner, 2, clock)
	defer orchestrator.Close()

	task, existing, err := orchestrator.Submit(context.Background(), validSubmission())
	if err != nil || existing {
		t.Fatalf("submit: existing=%v err=%v", existing, err)
	}
	<-runner.started
	running := waitForStatus(store, task.TaskID, "running")
	if running.StartedAt == nil {
		t.Fatal("running task missing started_at")
	}
	runner.result <- runnerReply{
		result: RunResult{RunID: "336fe16f3f221153", Reused: true},
	}
	succeeded := waitForStatus(store, task.TaskID, "succeeded")
	if succeeded.RunID == nil || *succeeded.RunID != "336fe16f3f221153" {
		t.Fatalf("unexpected result: %+v", succeeded)
	}
	if succeeded.Reused == nil || !*succeeded.Reused {
		t.Fatalf("expected reused result: %+v", succeeded)
	}
}

func TestOrchestratorPersistsStructuredWorkerFailure(t *testing.T) {
	store, err := OpenTaskStore(t.TempDir(), nil)
	if err != nil {
		t.Fatal(err)
	}
	runner := &blockingRunner{
		started: make(chan Submission, 1),
		result:  make(chan runnerReply, 1),
	}
	orchestrator := NewOrchestrator(store, runner, 1, nil)
	defer orchestrator.Close()
	task, _, err := orchestrator.Submit(context.Background(), validSubmission())
	if err != nil {
		t.Fatal(err)
	}
	<-runner.started
	runner.result <- runnerReply{
		err: &RunError{
			Code:      "dataset_not_found",
			Message:   "The selected immutable dataset is unavailable.",
			Retryable: false,
		},
	}
	failed := waitForStatus(store, task.TaskID, "failed")
	if failed.Error == nil || failed.Error.Code != "dataset_not_found" {
		t.Fatalf("unexpected failure: %+v", failed)
	}
}
