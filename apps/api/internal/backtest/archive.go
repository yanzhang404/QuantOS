package backtest

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type ExperimentArchiveStore struct {
	path string
	mu   sync.RWMutex
	now  func() time.Time
	data map[string]time.Time
}

type archiveFile struct {
	SchemaVersion string               `json:"schema_version"`
	Archives      map[string]time.Time `json:"archives"`
}

func OpenExperimentArchiveStore(root string, now func() time.Time) (*ExperimentArchiveStore, error) {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	if err := os.MkdirAll(root, 0o700); err != nil {
		return nil, fmt.Errorf("create experiment archive store: %w", err)
	}
	store := &ExperimentArchiveStore{
		path: filepath.Join(root, "experiment-archives.json"),
		now:  now, data: make(map[string]time.Time),
	}
	handle, err := os.Open(store.path)
	if errors.Is(err, os.ErrNotExist) {
		return store, nil
	}
	if err != nil {
		return nil, fmt.Errorf("open experiment archive store: %w", err)
	}
	defer handle.Close()
	decoder := json.NewDecoder(io.LimitReader(handle, 2<<20))
	decoder.DisallowUnknownFields()
	var payload archiveFile
	if err := decoder.Decode(&payload); err != nil || ensureEOF(decoder) != nil ||
		payload.SchemaVersion != SchemaVersion {
		return nil, errors.New("invalid experiment archive store")
	}
	for runID, archivedAt := range payload.Archives {
		if !hex16Pattern.MatchString(runID) || archivedAt.IsZero() {
			return nil, errors.New("invalid experiment archive entry")
		}
		store.data[runID] = archivedAt.UTC()
	}
	return store, nil
}

func (s *ExperimentArchiveStore) Snapshot() map[string]time.Time {
	s.mu.RLock()
	defer s.mu.RUnlock()
	result := make(map[string]time.Time, len(s.data))
	for runID, archivedAt := range s.data {
		result[runID] = archivedAt
	}
	return result
}

func (s *ExperimentArchiveStore) Archive(runID string) (time.Time, error) {
	if !hex16Pattern.MatchString(runID) {
		return time.Time{}, ErrExperimentNotFound
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if archivedAt, exists := s.data[runID]; exists {
		return archivedAt, nil
	}
	archivedAt := s.now().UTC()
	s.data[runID] = archivedAt
	if err := s.writeLocked(); err != nil {
		delete(s.data, runID)
		return time.Time{}, err
	}
	return archivedAt, nil
}

func (s *ExperimentArchiveStore) Restore(runID string) error {
	if !hex16Pattern.MatchString(runID) {
		return ErrExperimentNotFound
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	prior, exists := s.data[runID]
	if !exists {
		return nil
	}
	delete(s.data, runID)
	if err := s.writeLocked(); err != nil {
		s.data[runID] = prior
		return err
	}
	return nil
}

func (s *ExperimentArchiveStore) writeLocked() error {
	directory := filepath.Dir(s.path)
	temporary, err := os.CreateTemp(directory, ".experiment-archives-*.json")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if err := temporary.Chmod(0o600); err != nil {
		temporary.Close()
		return err
	}
	encoder := json.NewEncoder(temporary)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(archiveFile{SchemaVersion: SchemaVersion, Archives: s.data}); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	if err := os.Rename(temporaryPath, s.path); err != nil {
		return err
	}
	return nil
}
