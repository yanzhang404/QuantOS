package backtest

import (
	"context"
	"errors"
	"sync"
	"time"
)

type Orchestrator struct {
	store  *TaskStore
	runner Runner
	queue  chan string
	now    func() time.Time
	cancel context.CancelFunc
	wg     sync.WaitGroup
}

func NewOrchestrator(
	store *TaskStore,
	runner Runner,
	queueSize int,
	now func() time.Time,
) *Orchestrator {
	if queueSize < 1 {
		queueSize = 1
	}
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	context, cancel := context.WithCancel(context.Background())
	orchestrator := &Orchestrator{
		store:  store,
		runner: runner,
		queue:  make(chan string, queueSize),
		now:    now,
		cancel: cancel,
	}
	orchestrator.wg.Add(1)
	go orchestrator.work(context)
	return orchestrator
}

func (o *Orchestrator) Submit(ctx context.Context, request Submission) (Task, bool, error) {
	task, existing, err := o.store.Create(request)
	if err != nil || existing {
		return task, existing, err
	}
	select {
	case o.queue <- task.TaskID:
		return task, false, nil
	case <-ctx.Done():
		finished := o.now()
		failed, updateErr := o.store.Update(task.TaskID, func(task *Task) error {
			started := task.CreatedAt
			task.Status = "failed"
			task.StartedAt = &started
			task.FinishedAt = &finished
			task.Error = &TaskError{
				Code:      "submission_cancelled",
				Message:   "The request ended before the task could be queued.",
				Retryable: true,
			}
			return nil
		})
		if updateErr != nil {
			return Task{}, false, updateErr
		}
		return failed, false, ctx.Err()
	}
}

func (o *Orchestrator) Get(taskID string) (Task, error) {
	return o.store.Get(taskID)
}

func (o *Orchestrator) List() []Task {
	return o.store.List()
}

func (o *Orchestrator) Close() {
	o.cancel()
	o.wg.Wait()
}

func (o *Orchestrator) work(ctx context.Context) {
	defer o.wg.Done()
	for {
		select {
		case <-ctx.Done():
			return
		case taskID := <-o.queue:
			o.execute(ctx, taskID)
		}
	}
}

func (o *Orchestrator) execute(ctx context.Context, taskID string) {
	started := o.now()
	task, err := o.store.Update(taskID, func(task *Task) error {
		if task.Status != "queued" {
			return errors.New("task is not queued")
		}
		task.Status = "running"
		task.StartedAt = &started
		return nil
	})
	if err != nil {
		return
	}

	result, runErr := o.runner.Run(ctx, task.Request)
	finished := o.now()
	if runErr != nil {
		taskError := &TaskError{
			Code:      "worker_failed",
			Message:   truncate(runErr.Error(), 500),
			Retryable: false,
		}
		var structured *RunError
		if errors.As(runErr, &structured) {
			taskError.Code = structured.Code
			taskError.Message = structured.Message
			taskError.Retryable = structured.Retryable
		}
		_, _ = o.store.Update(taskID, func(task *Task) error {
			task.Status = "failed"
			task.FinishedAt = &finished
			task.Error = taskError
			return nil
		})
		return
	}
	_, _ = o.store.Update(taskID, func(task *Task) error {
		task.Status = "succeeded"
		task.FinishedAt = &finished
		task.RunID = &result.RunID
		task.Reused = &result.Reused
		return nil
	})
}
