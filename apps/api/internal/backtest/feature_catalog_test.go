package backtest

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"testing"
)

func TestFeatureDatasetCatalogListsOnlyCompatibleVerifiedVersions(t *testing.T) {
	root := t.TempDir()
	spot := validSubmission().Dataset
	newer := writeFeatureFixture(t, root, spot, "2222333344445555", "2026-02-02T00:00:00Z")
	writeFeatureFixture(t, root, spot, "1111222233334444", "2026-02-01T00:00:00Z")
	invalid := writeFeatureFixture(t, root, spot, "aaaabbbbccccdddd", "2026-02-03T00:00:00Z")
	if err := os.Remove(filepath.Join(invalid, "part-00000.parquet")); err != nil {
		t.Fatal(err)
	}

	store := NewFeatureDatasetStore(root)
	items, err := store.List("funding-rate", spot)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 || items[0].DatasetVersion != "2222333344445555" {
		t.Fatalf("unexpected feature catalog: %#v", items)
	}
	resolved, _, err := store.Resolve("funding-rate", spot, items[0].DatasetVersion)
	if err != nil || resolved != newer {
		t.Fatalf("resolved=%s err=%v", resolved, err)
	}

	mismatch := spot
	mismatch.Version = "9999000011112222"
	items, err = store.List("funding-rate", mismatch)
	if err != nil || len(items) != 0 {
		t.Fatalf("mismatched Spot catalog=%#v err=%v", items, err)
	}
}

func TestFeatureDatasetCatalogHTTPRequiresExactSpotIdentity(t *testing.T) {
	root := t.TempDir()
	spot := validSubmission().Dataset
	writeFeatureFixture(t, root, spot, "1111222233334444", "2026-02-01T00:00:00Z")
	handler := NewHTTPHandler(
		nil, NewExperimentStore(t.TempDir()), NewFeatureDatasetStore(root), "",
	)
	query := url.Values{
		"series": {"funding-rate"}, "symbol": {spot.Symbol}, "interval": {spot.Interval},
		"spot_dataset_version": {spot.Version}, "spot_content_sha256": {spot.ContentSHA256},
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(
		http.MethodGet, "/api/v1/feature-datasets?"+query.Encode(), nil,
	))
	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body)
	}
	var result struct {
		FeatureDatasets []FeatureDatasetManifest `json:"feature_datasets"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if len(result.FeatureDatasets) != 1 {
		t.Fatalf("feature datasets=%#v", result.FeatureDatasets)
	}

	invalid := httptest.NewRecorder()
	handler.ServeHTTP(invalid, httptest.NewRequest(
		http.MethodGet, "/api/v1/feature-datasets?series=funding-rate", nil,
	))
	if invalid.Code != http.StatusUnprocessableEntity {
		t.Fatalf("invalid status=%d body=%s", invalid.Code, invalid.Body)
	}
}

func writeFeatureFixture(
	t *testing.T,
	root string,
	spot DatasetRef,
	version, createdAt string,
) string {
	t.Helper()
	path := filepath.Join(
		root, "features", "derivatives-aligned", "series=funding-rate",
		"symbol="+spot.Symbol, "spot_interval="+spot.Interval, "version="+version,
	)
	if err := os.MkdirAll(path, 0o700); err != nil {
		t.Fatal(err)
	}
	hash := version + "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	manifest := FeatureDatasetManifest{
		DatasetVersion: version, SchemaVersion: "aligned-derivatives.v1",
		AlignmentPolicyVersion: "asof-closed-bar.v1", Series: "funding-rate",
		Exchange: "binance", Symbol: spot.Symbol, SpotInterval: spot.Interval,
		SpotDatasetVersion: spot.Version, SpotContentSHA256: spot.ContentSHA256,
		DerivativeDatasetVersion: "aaaabbbbccccdddd", DerivativeContentSHA256: hash,
		RequestedStart: "2026-01-01T00:00:00Z", RequestedEnd: "2026-02-01T00:00:00Z",
		MaxAgeMS: 28800000, RowCount: 3, MatchedCount: 2, StaleCount: 1,
		ContentSHA256: hash, CreatedAt: createdAt, Producer: "quantos-market-data/0.1.0",
		FileSHA256: hash,
	}
	payload, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(path, "manifest.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(path, "part-00000.parquet"), []byte("fixture"), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}
