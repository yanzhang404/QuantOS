package backtest

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

var (
	ErrTaskNotFound        = errors.New("task not found")
	ErrIdempotencyConflict = errors.New("idempotency key already belongs to another request")
)

type TaskStore struct {
	root          string
	mu            sync.RWMutex
	tasks         map[string]Task
	byIdempotency map[string]string
	now           func() time.Time
}

func OpenTaskStore(root string, now func() time.Time) (*TaskStore, error) {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	if err := os.MkdirAll(root, 0o700); err != nil {
		return nil, fmt.Errorf("create task store: %w", err)
	}
	store := &TaskStore{
		root:          root,
		tasks:         make(map[string]Task),
		byIdempotency: make(map[string]string),
		now:           now,
	}
	if err := store.load(); err != nil {
		return nil, err
	}
	if err := store.recoverInterrupted(); err != nil {
		return nil, err
	}
	return store, nil
}

func (s *TaskStore) Create(request Submission) (Task, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if taskID, ok := s.byIdempotency[request.IdempotencyKey]; ok {
		task := s.tasks[taskID]
		if !sameSubmission(task.Request, request) {
			return Task{}, false, ErrIdempotencyConflict
		}
		return task, true, nil
	}
	taskID, err := newTaskID()
	if err != nil {
		return Task{}, false, err
	}
	task := Task{
		SchemaVersion: SchemaVersion,
		TaskID:        taskID,
		Status:        "queued",
		CreatedAt:     s.now(),
		Request:       request,
	}
	if err := s.writeLocked(task); err != nil {
		return Task{}, false, err
	}
	s.tasks[task.TaskID] = task
	s.byIdempotency[request.IdempotencyKey] = task.TaskID
	return task, false, nil
}

func (s *TaskStore) Get(taskID string) (Task, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	task, ok := s.tasks[taskID]
	if !ok {
		return Task{}, ErrTaskNotFound
	}
	return task, nil
}

func (s *TaskStore) List() []Task {
	s.mu.RLock()
	defer s.mu.RUnlock()
	tasks := make([]Task, 0, len(s.tasks))
	for _, task := range s.tasks {
		tasks = append(tasks, task)
	}
	sort.Slice(tasks, func(i, j int) bool {
		return tasks[i].CreatedAt.After(tasks[j].CreatedAt)
	})
	return tasks
}

func (s *TaskStore) Update(taskID string, update func(*Task) error) (Task, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	task, ok := s.tasks[taskID]
	if !ok {
		return Task{}, ErrTaskNotFound
	}
	if err := update(&task); err != nil {
		return Task{}, err
	}
	if err := s.writeLocked(task); err != nil {
		return Task{}, err
	}
	s.tasks[taskID] = task
	return task, nil
}

func (s *TaskStore) load() error {
	entries, err := os.ReadDir(s.root)
	if err != nil {
		return fmt.Errorf("read task store: %w", err)
	}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasPrefix(entry.Name(), "task_") ||
			filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		path := filepath.Join(s.root, entry.Name())
		handle, err := os.Open(path)
		if err != nil {
			return fmt.Errorf("open task record %s: %w", path, err)
		}
		decoder := json.NewDecoder(io.LimitReader(handle, 2<<20))
		decoder.UseNumber()
		decoder.DisallowUnknownFields()
		var task Task
		decodeErr := decoder.Decode(&task)
		closeErr := handle.Close()
		if decodeErr != nil {
			return fmt.Errorf("decode task record %s: %w", path, decodeErr)
		}
		if closeErr != nil {
			return fmt.Errorf("close task record %s: %w", path, closeErr)
		}
		if task.SchemaVersion != SchemaVersion || task.TaskID == "" {
			return fmt.Errorf("unsupported task record: %s", path)
		}
		if prior, exists := s.byIdempotency[task.Request.IdempotencyKey]; exists {
			return fmt.Errorf(
				"duplicate idempotency key in task store: %s and %s",
				prior,
				task.TaskID,
			)
		}
		s.tasks[task.TaskID] = task
		s.byIdempotency[task.Request.IdempotencyKey] = task.TaskID
	}
	return nil
}

func (s *TaskStore) recoverInterrupted() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	for taskID, task := range s.tasks {
		if task.Status != "queued" && task.Status != "running" {
			continue
		}
		finished := s.now()
		if task.StartedAt == nil {
			started := task.CreatedAt
			task.StartedAt = &started
		}
		task.Status = "failed"
		task.FinishedAt = &finished
		task.Error = &TaskError{
			Code:      "service_restarted",
			Message:   "The API restarted before this task reached a terminal state.",
			Retryable: true,
		}
		if err := s.writeLocked(task); err != nil {
			return err
		}
		s.tasks[taskID] = task
	}
	return nil
}

func (s *TaskStore) writeLocked(task Task) error {
	path := filepath.Join(s.root, task.TaskID+".json")
	temp, err := os.CreateTemp(s.root, ".task-*.json")
	if err != nil {
		return fmt.Errorf("create temporary task record: %w", err)
	}
	tempPath := temp.Name()
	defer os.Remove(tempPath)
	if err := temp.Chmod(0o600); err != nil {
		temp.Close()
		return fmt.Errorf("protect temporary task record: %w", err)
	}
	encoder := json.NewEncoder(temp)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(task); err != nil {
		temp.Close()
		return fmt.Errorf("encode task record: %w", err)
	}
	if err := temp.Sync(); err != nil {
		temp.Close()
		return fmt.Errorf("sync task record: %w", err)
	}
	if err := temp.Close(); err != nil {
		return fmt.Errorf("close task record: %w", err)
	}
	if err := os.Rename(tempPath, path); err != nil {
		return fmt.Errorf("publish task record: %w", err)
	}
	return nil
}

func newTaskID() (string, error) {
	value := make([]byte, 8)
	if _, err := rand.Read(value); err != nil {
		return "", fmt.Errorf("generate task id: %w", err)
	}
	return "task_" + hex.EncodeToString(value), nil
}
