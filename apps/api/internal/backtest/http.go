package backtest

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"time"
)

type HTTPHandler struct {
	orchestrator  *Orchestrator
	experiments   *ExperimentStore
	archives      *ExperimentArchiveStore
	allowedOrigin string
	mux           *http.ServeMux
}

func NewHTTPHandler(
	orchestrator *Orchestrator,
	experiments *ExperimentStore,
	allowedOrigin string,
	archives ...*ExperimentArchiveStore,
) http.Handler {
	var archiveStore *ExperimentArchiveStore
	if len(archives) > 0 {
		archiveStore = archives[0]
	}
	handler := &HTTPHandler{
		orchestrator:  orchestrator,
		experiments:   experiments,
		archives:      archiveStore,
		allowedOrigin: allowedOrigin,
		mux:           http.NewServeMux(),
	}
	handler.mux.HandleFunc("GET /healthz", handler.health)
	handler.mux.HandleFunc("GET /api/v1/strategies", handler.strategies)
	handler.mux.HandleFunc("POST /api/v1/backtests", handler.submit)
	handler.mux.HandleFunc("GET /api/v1/tasks", handler.list)
	handler.mux.HandleFunc("GET /api/v1/tasks/{task_id}", handler.get)
	handler.mux.HandleFunc("GET /api/v1/experiments", handler.listExperiments)
	handler.mux.HandleFunc("GET /api/v1/experiments/{run_id}", handler.getExperiment)
	handler.mux.HandleFunc("PUT /api/v1/experiment-archives/{run_id}", handler.archiveExperiment)
	handler.mux.HandleFunc("DELETE /api/v1/experiment-archives/{run_id}", handler.restoreExperiment)
	return handler
}

func (h *HTTPHandler) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	if h.allowedOrigin != "" && request.Header.Get("Origin") == h.allowedOrigin {
		response.Header().Set("Access-Control-Allow-Origin", h.allowedOrigin)
		response.Header().Set("Access-Control-Allow-Headers", "Content-Type, Idempotency-Key")
		response.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		response.Header().Set("Vary", "Origin")
	}
	if request.Method == http.MethodOptions {
		response.WriteHeader(http.StatusNoContent)
		return
	}
	h.mux.ServeHTTP(response, request)
}

func (h *HTTPHandler) health(response http.ResponseWriter, _ *http.Request) {
	writeJSON(response, http.StatusOK, map[string]string{"status": "ok"})
}

func (h *HTTPHandler) strategies(response http.ResponseWriter, _ *http.Request) {
	writeJSON(response, http.StatusOK, strategyCatalog())
}

func (h *HTTPHandler) submit(response http.ResponseWriter, request *http.Request) {
	request.Body = http.MaxBytesReader(response, request.Body, 1<<20)
	decoder := json.NewDecoder(request.Body)
	decoder.UseNumber()
	decoder.DisallowUnknownFields()
	var submission Submission
	if err := decoder.Decode(&submission); err != nil {
		writeAPIError(response, http.StatusBadRequest, "invalid_json", "Invalid request body.")
		return
	}
	if err := ensureEOF(decoder); err != nil {
		writeAPIError(response, http.StatusBadRequest, "invalid_json", "Invalid request body.")
		return
	}
	if header := request.Header.Get("Idempotency-Key"); header != "" &&
		header != submission.IdempotencyKey {
		writeAPIError(
			response,
			http.StatusBadRequest,
			"idempotency_mismatch",
			"Idempotency-Key header does not match the request body.",
		)
		return
	}
	if err := submission.Validate(); err != nil {
		writeAPIError(response, http.StatusUnprocessableEntity, "invalid_request", err.Error())
		return
	}
	task, existing, err := h.orchestrator.Submit(request.Context(), submission)
	if errors.Is(err, ErrIdempotencyConflict) {
		writeAPIError(
			response,
			http.StatusConflict,
			"idempotency_conflict",
			ErrIdempotencyConflict.Error(),
		)
		return
	}
	if err != nil {
		writeAPIError(response, http.StatusInternalServerError, "submission_failed", "Task submission failed.")
		return
	}
	status := http.StatusAccepted
	if existing {
		status = http.StatusOK
	}
	response.Header().Set("Location", "/api/v1/tasks/"+task.TaskID)
	writeJSON(response, status, task)
}

func (h *HTTPHandler) list(response http.ResponseWriter, _ *http.Request) {
	writeJSON(response, http.StatusOK, map[string]any{"tasks": h.orchestrator.List()})
}

func (h *HTTPHandler) get(response http.ResponseWriter, request *http.Request) {
	task, err := h.orchestrator.Get(request.PathValue("task_id"))
	if errors.Is(err, ErrTaskNotFound) {
		writeAPIError(response, http.StatusNotFound, "task_not_found", "Task not found.")
		return
	}
	if err != nil {
		writeAPIError(response, http.StatusInternalServerError, "task_read_failed", "Task read failed.")
		return
	}
	writeJSON(response, http.StatusOK, task)
}

func (h *HTTPHandler) getExperiment(response http.ResponseWriter, request *http.Request) {
	experiment, err := h.experiments.Get(request.PathValue("run_id"))
	if errors.Is(err, ErrExperimentNotFound) {
		writeAPIError(
			response,
			http.StatusNotFound,
			"experiment_not_found",
			"Experiment not found.",
		)
		return
	}
	if errors.Is(err, ErrExperimentInvalid) {
		writeAPIError(
			response,
			http.StatusUnprocessableEntity,
			"experiment_invalid",
			"Experiment artifacts are invalid.",
		)
		return
	}
	if err != nil {
		writeAPIError(
			response,
			http.StatusInternalServerError,
			"experiment_read_failed",
			"Experiment read failed.",
		)
		return
	}
	writeJSON(response, http.StatusOK, experiment)
}

func (h *HTTPHandler) listExperiments(response http.ResponseWriter, request *http.Request) {
	query := request.URL.Query()
	filters := ExperimentFilters{
		Symbol: query.Get("symbol"), Interval: query.Get("interval"),
		Strategy: query.Get("strategy"), ArchivedMode: query.Get("archived"), Limit: 100,
	}
	if filters.ArchivedMode == "" {
		filters.ArchivedMode = "exclude"
	}
	if filters.ArchivedMode != "exclude" && filters.ArchivedMode != "include" &&
		filters.ArchivedMode != "only" {
		writeAPIError(response, http.StatusUnprocessableEntity, "invalid_filter", "archived must be exclude, include, or only.")
		return
	}
	if filters.Symbol != "" && !symbolPattern.MatchString(filters.Symbol) ||
		filters.Interval != "" && !supportedInterval(filters.Interval) ||
		filters.Strategy != "" && !knownStrategy(filters.Strategy) {
		writeAPIError(response, http.StatusUnprocessableEntity, "invalid_filter", "One or more Run filters are invalid.")
		return
	}
	if value := query.Get("limit"); value != "" {
		parsed, err := strconv.Atoi(value)
		if err != nil || parsed < 1 || parsed > 200 {
			writeAPIError(response, http.StatusUnprocessableEntity, "invalid_filter", "limit must be between 1 and 200.")
			return
		}
		filters.Limit = parsed
	}
	archiveSnapshot := map[string]time.Time{}
	if h.archives != nil {
		archiveSnapshot = h.archives.Snapshot()
	}
	experiments, err := h.experiments.List(filters, archiveSnapshot)
	if err != nil {
		writeAPIError(response, http.StatusInternalServerError, "experiment_list_failed", "Experiment list failed.")
		return
	}
	writeJSON(response, http.StatusOK, map[string]any{"experiments": experiments})
}

func (h *HTTPHandler) archiveExperiment(response http.ResponseWriter, request *http.Request) {
	h.setExperimentArchive(response, request, true)
}

func (h *HTTPHandler) restoreExperiment(response http.ResponseWriter, request *http.Request) {
	h.setExperimentArchive(response, request, false)
}

func (h *HTTPHandler) setExperimentArchive(response http.ResponseWriter, request *http.Request, archived bool) {
	if h.archives == nil {
		writeAPIError(response, http.StatusServiceUnavailable, "archive_store_unavailable", "Experiment archive store is unavailable.")
		return
	}
	runID := request.PathValue("run_id")
	if _, err := h.experiments.readArtifact(runID); errors.Is(err, ErrExperimentNotFound) {
		writeAPIError(response, http.StatusNotFound, "experiment_not_found", "Experiment not found.")
		return
	} else if err != nil {
		writeAPIError(response, http.StatusUnprocessableEntity, "experiment_invalid", "Experiment artifacts are invalid.")
		return
	}
	if archived {
		archivedAt, err := h.archives.Archive(runID)
		if err != nil {
			writeAPIError(response, http.StatusInternalServerError, "archive_write_failed", "Experiment archive state could not be saved.")
			return
		}
		writeJSON(response, http.StatusOK, map[string]any{"run_id": runID, "archived_at": archivedAt})
		return
	}
	if err := h.archives.Restore(runID); err != nil {
		writeAPIError(response, http.StatusInternalServerError, "archive_write_failed", "Experiment archive state could not be saved.")
		return
	}
	writeJSON(response, http.StatusOK, map[string]any{"run_id": runID, "archived_at": nil})
}

func writeJSON(response http.ResponseWriter, status int, value any) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(value)
}

func writeAPIError(response http.ResponseWriter, status int, code, message string) {
	writeJSON(response, status, map[string]any{
		"error": map[string]any{
			"code":    code,
			"message": message,
		},
	})
}

func ensureEOF(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("multiple JSON values")
		}
		return err
	}
	return nil
}

func strategyCatalog() map[string]any {
	return map[string]any{
		"schema_version": SchemaVersion,
		"strategies": []any{
			map[string]any{
				"name":                "buy-and-hold",
				"version":             "1.0.0",
				"label":               "Buy & Hold",
				"description":         "Passive long-only market exposure benchmark.",
				"category":            "benchmark",
				"stage":               "benchmark",
				"implementation":      "quantos_backtest.strategies.BuyAndHoldStrategy",
				"supported_intervals": []string{"5m", "15m", "1h", "4h", "1d"},
				"parameters": []any{
					parameter("target_exposure", "decimal", "Target exposure", "1", "0.01", "1"),
				},
			},
			map[string]any{
				"name":                "ema-cross",
				"version":             "1.0.0",
				"label":               "EMA Cross",
				"description":         "Long-only trend state from fast and slow exponential averages.",
				"category":            "trend",
				"stage":               "candidate",
				"implementation":      "quantos_backtest.strategies.EmaCrossStrategy",
				"supported_intervals": []string{"15m", "1h", "4h", "1d"},
				"parameters": []any{
					parameter("fast_period", "integer", "Fast period", 20, 1, 1000),
					parameter("slow_period", "integer", "Slow period", 50, 2, 2000),
				},
			},
			map[string]any{
				"name":                "donchian-atr",
				"version":             "1.0.0",
				"label":               "Donchian ATR",
				"description":         "Channel breakout with ATR volatility-targeted exposure.",
				"category":            "trend",
				"stage":               "candidate",
				"implementation":      "quantos_backtest.strategies.DonchianAtrStrategy",
				"supported_intervals": []string{"1h", "4h", "1d"},
				"parameters": []any{
					parameter("entry_period", "integer", "Entry period", 55, 2, 2000),
					parameter("exit_period", "integer", "Exit period", 20, 1, 2000),
					parameter("atr_period", "integer", "ATR period", 20, 2, 2000),
					parameter(
						"target_annual_volatility",
						"decimal",
						"Target annual volatility",
						"0.20",
						"0.01",
						"2",
					),
					parameter("max_exposure", "decimal", "Maximum exposure", "1", "0.01", "1"),
					parameter(
						"rebalance_threshold",
						"decimal",
						"Rebalance threshold",
						"0.05",
						"0",
						"1",
					),
				},
			},
			map[string]any{
				"name":                "funding-filtered-ema",
				"version":             "0.1.0",
				"label":               "Funding-filtered EMA",
				"description":         "EMA trend candidate that fails flat on crowded or unavailable funding.",
				"category":            "trend",
				"stage":               "candidate",
				"implementation":      "quantos_backtest.strategies.FundingFilteredEmaStrategy",
				"supported_intervals": []string{"1h", "4h", "1d"},
				"external_feature": map[string]any{
					"series": "funding-rate", "schema_version": "aligned-derivatives.v1",
					"alignment_policy_version": "asof-closed-bar.v1",
				},
				"parameters": []any{
					parameter("fast_period", "integer", "Fast period", 20, 1, 1000),
					parameter("slow_period", "integer", "Slow period", 50, 2, 2000),
					parameter("max_funding_rate", "decimal", "Maximum funding rate", "0.0001", "-0.01", "0.01"),
				},
			},
		},
	}
}

func parameter(key, kind, label string, value, minimum, maximum any) map[string]any {
	return map[string]any{
		"key":     key,
		"kind":    kind,
		"label":   label,
		"default": value,
		"minimum": minimum,
		"maximum": maximum,
	}
}
