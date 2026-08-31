package backtest

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestTaskStorePersistsTerminalTasksAndIdempotency(t *testing.T) {
	root := t.TempDir()
	now := time.Date(2026, 7, 29, 12, 0, 0, 0, time.UTC)
	store, err := OpenTaskStore(root, func() time.Time { return now })
	if err != nil {
		t.Fatal(err)
	}
	request := validSubmission()
	task, existing, err := store.Create(request)
	if err != nil || existing {
		t.Fatalf("create task: existing=%v err=%v", existing, err)
	}
	finished := now.Add(time.Second)
	runID := "336fe16f3f221153"
	reused := false
	_, err = store.Update(task.TaskID, func(task *Task) error {
		task.Status = "succeeded"
		task.StartedAt = &now
		task.FinishedAt = &finished
		task.RunID = &runID
		task.Reused = &reused
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}

	reopened, err := OpenTaskStore(root, func() time.Time { return finished })
	if err != nil {
		t.Fatal(err)
	}
	persisted, existing, err := reopened.Create(request)
	if err != nil || !existing {
		t.Fatalf("reuse task: existing=%v err=%v", existing, err)
	}
	if persisted.TaskID != task.TaskID || persisted.Status != "succeeded" {
		t.Fatalf("unexpected persisted task: %+v", persisted)
	}
	info, err := os.Stat(filepath.Join(root, task.TaskID+".json"))
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("task file permissions = %o", info.Mode().Perm())
	}

	conflict := request
	label := "different request"
	conflict.Label = &label
	if _, _, err := reopened.Create(conflict); !errors.Is(err, ErrIdempotencyConflict) {
		t.Fatalf("expected idempotency conflict, got %v", err)
	}
}

func TestTaskStoreMarksInterruptedTasksFailedOnRestart(t *testing.T) {
	root := t.TempDir()
	created := time.Date(2026, 7, 29, 12, 0, 0, 0, time.UTC)
	store, err := OpenTaskStore(root, func() time.Time { return created })
	if err != nil {
		t.Fatal(err)
	}
	task, _, err := store.Create(validSubmission())
	if err != nil {
		t.Fatal(err)
	}

	restarted := created.Add(time.Minute)
	reopened, err := OpenTaskStore(root, func() time.Time { return restarted })
	if err != nil {
		t.Fatal(err)
	}
	recovered, err := reopened.Get(task.TaskID)
	if err != nil {
		t.Fatal(err)
	}
	if recovered.Status != "failed" || recovered.Error == nil {
		t.Fatalf("unexpected recovered task: %+v", recovered)
	}
	if recovered.Error.Code != "service_restarted" || !recovered.Error.Retryable {
		t.Fatalf("unexpected restart error: %+v", recovered.Error)
	}
}
