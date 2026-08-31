package radar

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestStoreReadsAndValidatesRadarSnapshot(t *testing.T) {
	root := t.TempDir()
	writeFixture(t, root)

	snapshot, err := NewStore(root).Latest()
	if err != nil {
		t.Fatalf("Latest() error = %v", err)
	}
	if len(snapshot.Stocks) != 6 || len(snapshot.Themes) != 4 || *snapshot.Summary.HottestTheme != "液冷" {
		t.Fatalf("unexpected radar snapshot: %#v", snapshot.Summary)
	}
}

func TestStoreRejectsTamperedAndSymlinkedRadarSnapshots(t *testing.T) {
	t.Run("tampered heat", func(t *testing.T) {
		root := t.TempDir()
		snapshot := fixture(t)
		snapshot.Stocks[0].HeatScore = 1
		writeSnapshot(t, root, snapshot)

		_, err := NewStore(root).Latest()
		if !errors.Is(err, ErrSnapshotInvalid) {
			t.Fatalf("Latest() error = %v, want ErrSnapshotInvalid", err)
		}
	})

	t.Run("false complete status", func(t *testing.T) {
		root := t.TempDir()
		snapshot := fixture(t)
		snapshot.Status = "complete"
		snapshot.Stocks[0].NewHigh20d = nil
		writeSnapshot(t, root, snapshot)

		_, err := NewStore(root).Latest()
		if !errors.Is(err, ErrSnapshotInvalid) {
			t.Fatalf("Latest() error = %v, want ErrSnapshotInvalid", err)
		}
	})

	t.Run("symlink", func(t *testing.T) {
		root := t.TempDir()
		target := filepath.Join(root, "target.json")
		payload, err := json.Marshal(fixture(t))
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(target, payload, 0o600); err != nil {
			t.Fatal(err)
		}
		if err := os.Symlink(target, filepath.Join(root, "latest.json")); err != nil {
			t.Fatal(err)
		}
		_, err = NewStore(root).Latest()
		if !errors.Is(err, ErrSnapshotInvalid) {
			t.Fatalf("Latest() error = %v, want ErrSnapshotInvalid", err)
		}
	})
}

func TestHTTPHandlerServesRadarAndHealth(t *testing.T) {
	root := t.TempDir()
	writeFixture(t, root)
	success := "2026-08-12T02:31:00Z"
	bucket := "2026-08-12T02:30Z"
	writeHealth(t, root, refreshHealthRecord{
		SchemaVersion: SchemaVersion, State: "succeeded", LastAttemptAt: success,
		LastSuccessAt: &success, LastSuccessBucket: &bucket,
	})
	store := NewStore(root)
	store.now = func() time.Time { return time.Date(2026, 8, 12, 2, 45, 0, 0, time.UTC) }
	handler := NewHTTPHandler(store, "http://localhost:3000")

	for _, path := range []string{"/api/v1/radar/latest", "/api/v1/radar/health"} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		request.Header.Set("Origin", "http://localhost:3000")
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("%s status = %d, body = %s", path, response.Code, response.Body.String())
		}
	}

	health, err := store.Health()
	if err != nil || health.Stale {
		t.Fatalf("Health() = %#v, %v", health, err)
	}
}

func TestHTTPHandlerReportsUnavailableRadar(t *testing.T) {
	response := httptest.NewRecorder()
	NewHTTPHandler(NewStore(t.TempDir()), "").ServeHTTP(
		response,
		httptest.NewRequest(http.MethodGet, "/api/v1/radar/latest", nil),
	)
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d", response.Code)
	}
}

func fixture(t *testing.T) Snapshot {
	t.Helper()
	payload, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "examples", "radar", "sample-snapshot.v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	var snapshot Snapshot
	if err := json.Unmarshal(payload, &snapshot); err != nil {
		t.Fatal(err)
	}
	return snapshot
}

func writeFixture(t *testing.T, root string) {
	t.Helper()
	writeSnapshot(t, root, fixture(t))
}

func writeSnapshot(t *testing.T, root string, snapshot Snapshot) {
	t.Helper()
	payload, err := json.Marshal(snapshot)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "latest.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
}

func writeHealth(t *testing.T, root string, health refreshHealthRecord) {
	t.Helper()
	payload, err := json.Marshal(health)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "refresh-health.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
}
