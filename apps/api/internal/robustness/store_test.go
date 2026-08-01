package robustness

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestStoreListsAndReadsValidatedRobustnessReviews(t *testing.T) {
	root := t.TempDir()
	writeReview(t, root, validReview("336fe16f3f221153"))
	store := NewStore(root)

	reviews, err := store.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(reviews) != 1 || reviews[0].ReviewID != "336fe16f3f221153" {
		t.Fatalf("reviews = %#v", reviews)
	}
	if len(reviews[0].Gates) != 4 || reviews[0].Passed {
		t.Fatalf("summary = %#v", reviews[0])
	}
	review, err := store.Get("336fe16f3f221153")
	if err != nil {
		t.Fatal(err)
	}
	if review.Strategy.Winner.FastPeriod != 20 || len(review.Datasets) != 2 {
		t.Fatalf("review = %#v", review)
	}
}

func TestStoreRejectsMismatchedOverallGateAndSymlink(t *testing.T) {
	root := t.TempDir()
	invalid := validReview("336fe16f3f221153")
	invalid["passed"] = true
	writeReview(t, root, invalid)
	if _, err := NewStore(root).Get("336fe16f3f221153"); err == nil {
		t.Fatal("expected mismatched gate status to fail")
	}

	symlinkRoot := t.TempDir()
	directory := filepath.Join(symlinkRoot, "436fe16f3f221153")
	if err := os.MkdirAll(directory, 0o700); err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(symlinkRoot, "target.json")
	payload, _ := json.Marshal(validReview("436fe16f3f221153"))
	if err := os.WriteFile(target, payload, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, filepath.Join(directory, "robustness.json")); err != nil {
		t.Fatal(err)
	}
	if _, err := NewStore(symlinkRoot).Get("436fe16f3f221153"); err == nil {
		t.Fatal("expected symlinked review to fail")
	}
}

func TestHTTPListsReviewsAndReturnsSafeErrors(t *testing.T) {
	root := t.TempDir()
	writeReview(t, root, validReview("336fe16f3f221153"))
	handler := NewHTTPHandler(NewStore(root), "http://localhost:3000")

	list := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/api/v1/robustness", nil)
	request.Header.Set("Origin", "http://localhost:3000")
	handler.ServeHTTP(list, request)
	if list.Code != http.StatusOK {
		t.Fatalf("list status = %d body=%s", list.Code, list.Body)
	}
	if list.Header().Get("Access-Control-Allow-Origin") != "http://localhost:3000" {
		t.Fatal("expected exact CORS origin")
	}

	detail := httptest.NewRecorder()
	handler.ServeHTTP(detail, httptest.NewRequest(
		http.MethodGet,
		"/api/v1/robustness/336fe16f3f221153",
		nil,
	))
	if detail.Code != http.StatusOK {
		t.Fatalf("detail status = %d body=%s", detail.Code, detail.Body)
	}

	missing := httptest.NewRecorder()
	handler.ServeHTTP(missing, httptest.NewRequest(
		http.MethodGet,
		"/api/v1/robustness/not-a-review",
		nil,
	))
	if missing.Code != http.StatusNotFound {
		t.Fatalf("missing status = %d", missing.Code)
	}
}

func writeReview(t *testing.T, root string, review map[string]any) {
	t.Helper()
	reviewID := review["review_id"].(string)
	directory := filepath.Join(root, reviewID)
	if err := os.MkdirAll(directory, 0o700); err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(review)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "robustness.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
}

func validReview(reviewID string) map[string]any {
	runID := "536fe16f3f221153"
	gates := []any{}
	for index, name := range []string{
		"walk_forward",
		"neighboring_parameters",
		"doubled_costs",
		"multiple_markets",
	} {
		gates = append(gates, map[string]any{
			"name": name, "passed": index != 2,
			"reason": "deterministic gate evidence", "observations": map[string]any{"return": 0.01},
			"run_ids": []string{runID},
		})
	}
	return map[string]any{
		"schema_version": "robustness-review.v1", "review_id": reviewID,
		"status": "completed", "created_at": "2026-08-01T12:00:00Z", "passed": false,
		"strategy": map[string]any{
			"name": "ema-cross", "version": "1.0.0",
			"winner": map[string]any{"fast_period": 20, "slow_period": 50},
		},
		"datasets": []any{
			map[string]any{
				"version":        "024f23d9a629502e",
				"content_sha256": "024f23d9a629502eabf7c8186735938cb585ab76286b072e20ded76c1b4bc7b3",
				"symbol":         "BTCUSDT", "interval": "4h",
			},
			map[string]any{
				"version":        "124f23d9a629502e",
				"content_sha256": "124f23d9a629502eabf7c8186735938cb585ab76286b072e20ded76c1b4bc7b3",
				"symbol":         "ETHUSDT", "interval": "4h",
			},
		},
		"research_config":   map[string]any{"fast_periods": []int{20}},
		"robustness_config": map[string]any{"fold_count": 3},
		"gates":             gates, "walk_forward": []any{map[string]any{"fold": 1}},
		"neighbors": []any{map[string]any{"run_id": runID}},
		"markets":   []any{map[string]any{"run_id": runID}},
		"artifacts": []string{"walk-forward.csv", "review.md"},
	}
}
