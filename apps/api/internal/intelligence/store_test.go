package intelligence

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestStoreReadsAndValidatesLatestSnapshot(t *testing.T) {
	root := t.TempDir()
	writeSnapshot(t, root, validSnapshot())

	snapshot, err := NewStore(root).Latest()
	if err != nil {
		t.Fatalf("Latest() error = %v", err)
	}
	if snapshot.Score != 50 || snapshot.Label != "neutral" {
		t.Fatalf("Latest() = score %.2f, label %q", snapshot.Score, snapshot.Label)
	}
}

func TestStoreRejectsInvalidAndSymlinkedSnapshots(t *testing.T) {
	t.Run("invalid methodology", func(t *testing.T) {
		root := t.TempDir()
		snapshot := validSnapshot()
		snapshot.Score = 80
		writeSnapshot(t, root, snapshot)

		_, err := NewStore(root).Latest()
		if !errors.Is(err, ErrSnapshotInvalid) {
			t.Fatalf("Latest() error = %v, want ErrSnapshotInvalid", err)
		}
	})

	t.Run("symlink", func(t *testing.T) {
		root := t.TempDir()
		target := filepath.Join(root, "target.json")
		payload, err := json.Marshal(validSnapshot())
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

func TestHTTPHandlerReportsAvailabilityAndServesSnapshot(t *testing.T) {
	root := t.TempDir()
	handler := NewHTTPHandler(NewStore(root), "http://localhost:3000")

	unavailable := httptest.NewRecorder()
	handler.ServeHTTP(unavailable, httptest.NewRequest(http.MethodGet, "/api/v1/intelligence/latest", nil))
	if unavailable.Code != http.StatusServiceUnavailable {
		t.Fatalf("unavailable status = %d", unavailable.Code)
	}

	writeSnapshot(t, root, validSnapshot())
	request := httptest.NewRequest(http.MethodGet, "/api/v1/intelligence/latest", nil)
	request.Header.Set("Origin", "http://localhost:3000")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if response.Header().Get("Access-Control-Allow-Origin") != "http://localhost:3000" {
		t.Fatal("expected allowed CORS origin")
	}
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

func validSnapshot() Snapshot {
	methods := []struct {
		key       string
		weight    float64
		direction string
	}{
		{"crypto_volatility", .20, "fear_when_high"},
		{"options_positioning", .20, "fear_when_high"},
		{"perpetual_positioning", .20, "greed_when_high"},
		{"momentum_volume", .15, "greed_when_high"},
		{"liquidation_balance", .10, "greed_when_high"},
		{"market_breadth", .10, "greed_when_high"},
		{"macro_risk", .05, "fear_when_high"},
	}
	factors := make([]Factor, 0, len(methods))
	for _, method := range methods {
		factors = append(factors, Factor{
			Key: method.key, RawValue: 1, Unit: "index", Percentile: .5,
			Source: "https://example.com/data", ObservedAt: "2026-08-01T08:00:00Z",
			Weight: method.weight, Direction: method.direction, Score: 50,
			Contribution: 50 * method.weight,
		})
	}
	return Snapshot{
		SchemaVersion: SchemaVersion, MethodologyVersion: MethodologyVersion,
		Date: "2026-08-01", AsOf: "2026-08-01T08:00:00Z", Status: "sample",
		Score: 50, Label: "neutral", MarketScore: 50, NewsScore: 50,
		Factors: factors,
		Brief: Brief{
			Title: "Daily brief", TitleZH: "每日简报", Summary: "Neutral market.",
			SummaryZH: "市场中性。", Highlights: []string{}, HighlightsZH: []string{},
			News: []NewsItem{},
		},
		Provenance: Provenance{
			InputSHA256:      "0000000000000000000000000000000000000000000000000000000000000000",
			GeneratorVersion: GeneratorVersion, FactorCount: 7, NewsCount: 0,
		},
	}
}
