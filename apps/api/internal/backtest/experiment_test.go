package backtest

import (
	"encoding/json"
	"errors"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestExperimentStoreDerivesNormalizedVisualization(t *testing.T) {
	root := t.TempDir()
	writeExperimentFixture(t, root, "336fe16f3f221153")

	experiment, err := NewExperimentStore(root).Get("336fe16f3f221153")
	if err != nil {
		t.Fatal(err)
	}
	if experiment.RunID != "336fe16f3f221153" {
		t.Fatalf("run id = %s", experiment.RunID)
	}
	if len(experiment.Equity) != 3 {
		t.Fatalf("equity points = %d", len(experiment.Equity))
	}
	if len(experiment.Bars) != 3 || experiment.Bars[2].Close != 95 {
		t.Fatalf("bars = %#v", experiment.Bars)
	}
	if len(experiment.Features) != 1 || experiment.Features[0].Instance != "entry_channel" {
		t.Fatalf("features = %#v", experiment.Features)
	}
	if difference := math.Abs(experiment.Equity[1].Drawdown - (-0.1)); difference > 1e-12 {
		t.Fatalf("drawdown = %f", experiment.Equity[1].Drawdown)
	}
	if len(experiment.Fills) != 2 {
		t.Fatalf("fills = %d", len(experiment.Fills))
	}
	if experiment.Fills[0].Side != "buy" || experiment.Fills[1].Side != "sell" {
		t.Fatalf("fill sides = %#v", experiment.Fills)
	}
	if experiment.Fills[1].Quantity != 0.25 {
		t.Fatalf("normalized sell quantity = %f", experiment.Fills[1].Quantity)
	}
}

func TestExperimentHTTPReturnsDetailAndSafeErrors(t *testing.T) {
	root := t.TempDir()
	writeExperimentFixture(t, root, "336fe16f3f221153")
	handler := NewHTTPHandler(nil, NewExperimentStore(root), "")

	response := httptest.NewRecorder()
	handler.ServeHTTP(
		response,
		httptest.NewRequest(
			http.MethodGet,
			"/api/v1/experiments/336fe16f3f221153",
			nil,
		),
	)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", response.Code, response.Body)
	}
	var detail ExperimentVisualization
	if err := json.Unmarshal(response.Body.Bytes(), &detail); err != nil {
		t.Fatal(err)
	}
	if len(detail.Bars) != 3 || len(detail.Equity) != 3 || len(detail.Fills) != 2 {
		t.Fatalf("unexpected detail = %#v", detail)
	}

	for _, runID := range []string{"missing000000000", "..%2Fprivate"} {
		missing := httptest.NewRecorder()
		handler.ServeHTTP(
			missing,
			httptest.NewRequest(
				http.MethodGet,
				"/api/v1/experiments/"+runID,
				nil,
			),
		)
		if missing.Code != http.StatusNotFound {
			t.Fatalf("missing %q status = %d", runID, missing.Code)
		}
	}
}

func TestExperimentCatalogFiltersAndArchivesWithoutChangingArtifacts(t *testing.T) {
	root := t.TempDir()
	stateRoot := t.TempDir()
	writeExperimentFixture(t, root, "336fe16f3f221153")
	writeExperimentFixture(t, root, "436fe16f3f221153")
	archives, err := OpenExperimentArchiveStore(
		stateRoot,
		func() time.Time { return time.Date(2026, 8, 1, 2, 3, 4, 0, time.UTC) },
	)
	if err != nil {
		t.Fatal(err)
	}
	handler := NewHTTPHandler(nil, NewExperimentStore(root), "", archives)

	list := httptest.NewRecorder()
	handler.ServeHTTP(list, httptest.NewRequest(
		http.MethodGet,
		"/api/v1/experiments?symbol=BTCUSDT&interval=4h&strategy=donchian-atr",
		nil,
	))
	if list.Code != http.StatusOK {
		t.Fatalf("list status = %d body=%s", list.Code, list.Body)
	}
	var result struct {
		Experiments []ExperimentSummary `json:"experiments"`
	}
	if err := json.Unmarshal(list.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if len(result.Experiments) != 2 {
		t.Fatalf("experiments = %#v", result.Experiments)
	}
	if len(result.Experiments[0].Strategy.Parameters) == 0 ||
		result.Experiments[0].Metrics.FinalEquity != 99000 {
		t.Fatalf("summary missing inputs or metrics: %#v", result.Experiments[0])
	}

	runPath := filepath.Join(root, "336fe16f3f221153", "run.json")
	before, err := os.ReadFile(runPath)
	if err != nil {
		t.Fatal(err)
	}
	archive := httptest.NewRecorder()
	handler.ServeHTTP(archive, httptest.NewRequest(
		http.MethodPut,
		"/api/v1/experiment-archives/336fe16f3f221153",
		nil,
	))
	if archive.Code != http.StatusOK {
		t.Fatalf("archive status = %d body=%s", archive.Code, archive.Body)
	}
	after, err := os.ReadFile(runPath)
	if err != nil {
		t.Fatal(err)
	}
	if string(before) != string(after) {
		t.Fatal("archive operation changed immutable Run artifact")
	}

	active := httptest.NewRecorder()
	handler.ServeHTTP(active, httptest.NewRequest(http.MethodGet, "/api/v1/experiments", nil))
	if err := json.Unmarshal(active.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if len(result.Experiments) != 1 || result.Experiments[0].RunID != "436fe16f3f221153" {
		t.Fatalf("active experiments = %#v", result.Experiments)
	}

	archived := httptest.NewRecorder()
	handler.ServeHTTP(archived, httptest.NewRequest(
		http.MethodGet,
		"/api/v1/experiments?archived=only",
		nil,
	))
	if err := json.Unmarshal(archived.Body.Bytes(), &result); err != nil {
		t.Fatal(err)
	}
	if len(result.Experiments) != 1 || result.Experiments[0].ArchivedAt == nil {
		t.Fatalf("archived experiments = %#v", result.Experiments)
	}

	restore := httptest.NewRecorder()
	handler.ServeHTTP(restore, httptest.NewRequest(
		http.MethodDelete,
		"/api/v1/experiment-archives/336fe16f3f221153",
		nil,
	))
	if restore.Code != http.StatusOK {
		t.Fatalf("restore status = %d body=%s", restore.Code, restore.Body)
	}
	reopened, err := OpenExperimentArchiveStore(stateRoot, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(reopened.Snapshot()) != 0 {
		t.Fatal("restored archive marker persisted")
	}
}

func TestExperimentCatalogRejectsInvalidFiltersAndArchiveTargets(t *testing.T) {
	root := t.TempDir()
	archives, err := OpenExperimentArchiveStore(t.TempDir(), nil)
	if err != nil {
		t.Fatal(err)
	}
	handler := NewHTTPHandler(nil, NewExperimentStore(root), "", archives)
	for _, target := range []string{
		"/api/v1/experiments?interval=1minute",
		"/api/v1/experiments?archived=yes",
		"/api/v1/experiments?limit=201",
	} {
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, target, nil))
		if response.Code != http.StatusUnprocessableEntity {
			t.Fatalf("target %s status = %d", target, response.Code)
		}
	}
	missing := httptest.NewRecorder()
	handler.ServeHTTP(missing, httptest.NewRequest(
		http.MethodPut,
		"/api/v1/experiment-archives/336fe16f3f221153",
		nil,
	))
	if missing.Code != http.StatusNotFound {
		t.Fatalf("missing archive status = %d", missing.Code)
	}
}

func TestExperimentDetailExposesValidatedV4FeatureDatasetLineage(t *testing.T) {
	root := t.TempDir()
	runID := "336fe16f3f221153"
	writeExperimentFixture(t, root, runID)
	path := filepath.Join(root, runID, "run.json")
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var run map[string]any
	if err := json.Unmarshal(payload, &run); err != nil {
		t.Fatal(err)
	}
	run["artifact_schema_version"] = "experiment-artifacts.v4"
	run["strategy"] = map[string]any{
		"name": "funding-filtered-ema", "version": "0.1.0",
		"parameters": map[string]any{
			"fast_period": 20, "slow_period": 50, "max_funding_rate": "0.0001",
		},
	}
	hash := strings.Repeat("a", 64)
	run["feature_datasets"] = []map[string]any{{
		"dataset_version": "1111222233334444", "schema_version": "aligned-derivatives.v1",
		"alignment_policy_version": "asof-closed-bar.v1", "series": "funding-rate",
		"exchange": "binance", "symbol": "BTCUSDT", "spot_interval": "4h",
		"derivative_period": nil, "spot_dataset_version": "024f23d9a629502e",
		"spot_content_sha256":        "024f23d9a629502eabf7c8186735938cb585ab76286b072e20ded76c1b4bc7b3",
		"derivative_dataset_version": "aaaabbbbccccdddd",
		"derivative_content_sha256":  hash,
		"requested_start":            "2026-01-01T00:00:00Z", "requested_end": "2026-02-01T00:00:00Z",
		"max_age_ms": 28800000, "row_count": 3, "matched_count": 2,
		"stale_count": 1, "no_prior_count": 0, "content_sha256": hash,
		"created_at": "2026-02-01T01:00:00Z", "producer": "quantos-market-data/0.1.0",
		"file_sha256": hash,
	}}
	payload, err = json.Marshal(run)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, payload, 0o600); err != nil {
		t.Fatal(err)
	}

	experiment, err := NewExperimentStore(root).Get(runID)
	if err != nil {
		t.Fatal(err)
	}
	if len(experiment.FeatureDatasets) != 1 ||
		experiment.FeatureDatasets[0].DatasetVersion != "1111222233334444" {
		t.Fatalf("unexpected feature lineage: %#v", experiment.FeatureDatasets)
	}

	run["feature_datasets"] = []any{}
	payload, _ = json.Marshal(run)
	if err := os.WriteFile(path, payload, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := NewExperimentStore(root).Get(runID); !errors.Is(err, ErrExperimentInvalid) {
		t.Fatalf("expected invalid missing funding lineage, got %v", err)
	}
}

func writeExperimentFixture(t *testing.T, root, runID string) {
	t.Helper()
	directory := filepath.Join(root, runID)
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	run := map[string]any{
		"artifact_schema_version": "experiment-artifacts.v3",
		"run_id":                  runID,
		"status":                  "completed",
		"created_at":              time.Date(2026, 7, 30, 1, 2, 3, 0, time.UTC),
		"dataset": map[string]any{
			"version":        "024f23d9a629502e",
			"content_sha256": "024f23d9a629502eabf7c8186735938cb585ab76286b072e20ded76c1b4bc7b3",
			"symbol":         "BTCUSDT",
			"interval":       "4h",
		},
		"strategy": map[string]any{
			"name":    "donchian-atr",
			"version": "1.0.0",
			"parameters": map[string]any{
				"entry_period":             55,
				"exit_period":              20,
				"atr_period":               20,
				"target_annual_volatility": "0.20",
				"max_exposure":             "1",
				"rebalance_threshold":      "0.05",
			},
		},
		"features": []map[string]any{
			{
				"feature_id": "prior-high-channel", "instance": "entry_channel",
				"version": "1.0.0", "definition_sha256": strings.Repeat("a", 64),
				"implementation": "quantos_backtest.strategies.DonchianAtrStrategy.on_bar",
				"inputs":         []string{"high"}, "parameters": map[string]int{"period": 55},
				"strategy_parameter": "entry_period", "warmup_bars": 55,
				"uses_current_closed_bar": false,
			},
		},
		"config": map[string]any{
			"initial_cash":        "100000",
			"fee_bps":             "10",
			"slippage_bps":        "5",
			"max_target_exposure": "1",
			"liquidate_at_end":    true,
		},
		"engine_version":  "0.2.0",
		"metrics_version": "0.1.0",
		"metrics": map[string]any{
			"initial_equity": 100000,
			"final_equity":   99000,
			"total_return":   -0.01,
			"sharpe_ratio":   0.12,
			"max_drawdown":   0.1,
			"trade_count":    1,
			"fill_count":     2,
			"fees_paid":      42.5,
		},
	}
	payload, err := json.Marshal(run)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "run.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	bars := `open_time,open,high,low,close,volume
2026-01-01T00:00:00Z,100,105,95,100,10
2026-01-01T04:00:00Z,100,102,88,90,12
2026-01-01T08:00:00Z,90,98,89,95,11
`
	if err := os.WriteFile(filepath.Join(directory, "bars.csv"), []byte(bars), 0o600); err != nil {
		t.Fatal(err)
	}
	equity := `timestamp,cash,position_quantity,market_price,equity
2026-01-01T03:59:59.999Z,100000,0,100,100000
2026-01-01T07:59:59.999Z,45000,500,90,90000
2026-01-01T11:59:59.999Z,99000,0,95,99000
`
	if err := os.WriteFile(filepath.Join(directory, "equity.csv"), []byte(equity), 0o600); err != nil {
		t.Fatal(err)
	}
	fills := `timestamp,symbol,quantity,price,notional,fee,reason
2026-01-01T04:00:00Z,BTCUSDT,0.5,100,50,0.05,enter
2026-01-01T08:00:00Z,BTCUSDT,-0.25,90,22.5,0.03,reduce
`
	if err := os.WriteFile(filepath.Join(directory, "fills.csv"), []byte(fills), 0o600); err != nil {
		t.Fatal(err)
	}
}
