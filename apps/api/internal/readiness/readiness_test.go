package readiness

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestHandlerRequiresConfiguredBundleAndRoots(t *testing.T) {
	root := t.TempDir()
	for _, name := range []string{"artifacts", "state", "intelligence"} {
		if err := os.Mkdir(filepath.Join(root, name), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	checker := Checker{
		DataRoot:         root,
		ArtifactRoot:     filepath.Join(root, "artifacts"),
		StateRoot:        filepath.Join(root, "state"),
		IntelligenceRoot: filepath.Join(root, "intelligence"),
		UVBinary:         "go",
		RequiredBundle:   "47a8b29be444e2ba",
	}

	response := httptest.NewRecorder()
	checker.Handler(response, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 before bundle exists, got %d", response.Code)
	}

	manifest := filepath.Join(
		root,
		"bundles",
		"market",
		"spot",
		"exchange=binance",
		"version=47a8b29be444e2ba",
		"manifest.json",
	)
	if err := os.MkdirAll(filepath.Dir(manifest), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(manifest, []byte("{}\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	response = httptest.NewRecorder()
	checker.Handler(response, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if response.Code != http.StatusOK {
		t.Fatalf("expected 200 when prerequisites exist, got %d: %s", response.Code, response.Body)
	}
	var payload struct {
		Status string          `json:"status"`
		Checks map[string]bool `json:"checks"`
	}
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	if payload.Status != "ready" || !payload.Checks["required_bundle"] {
		t.Fatalf("unexpected readiness payload: %#v", payload)
	}
}

func TestHandlerRejectsUnsafeBundleVersion(t *testing.T) {
	checker := Checker{
		DataRoot:         t.TempDir(),
		ArtifactRoot:     t.TempDir(),
		StateRoot:        t.TempDir(),
		IntelligenceRoot: t.TempDir(),
		UVBinary:         "go",
		RequiredBundle:   "../../etc/passwd",
	}
	if checker.Check()["required_bundle"] {
		t.Fatal("unsafe bundle version must not be accepted")
	}
}

func TestHandlerAllowsOnlyGet(t *testing.T) {
	response := httptest.NewRecorder()
	Checker{}.Handler(response, httptest.NewRequest(http.MethodPost, "/readyz", nil))
	if response.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", response.Code)
	}
}
