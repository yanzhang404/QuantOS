package backtest

import (
	"encoding/json"
	"math"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
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
	if len(detail.Equity) != 3 || len(detail.Fills) != 2 {
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

func writeExperimentFixture(t *testing.T, root, runID string) {
	t.Helper()
	directory := filepath.Join(root, runID)
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	run := map[string]any{
		"run_id":     runID,
		"status":     "completed",
		"created_at": time.Date(2026, 7, 30, 1, 2, 3, 0, time.UTC),
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
