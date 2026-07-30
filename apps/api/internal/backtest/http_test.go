package backtest

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHTTPBacktestSubmissionIsIdempotentAndQueryable(t *testing.T) {
	store, err := OpenTaskStore(t.TempDir(), nil)
	if err != nil {
		t.Fatal(err)
	}
	runner := &blockingRunner{
		started: make(chan Submission, 1),
		result:  make(chan runnerReply, 1),
	}
	orchestrator := NewOrchestrator(store, runner, 2, nil)
	defer orchestrator.Close()
	handler := NewHTTPHandler(
		orchestrator,
		NewExperimentStore(t.TempDir()),
		"http://localhost:3000",
	)
	payload, _ := json.Marshal(validSubmission())

	first := httptest.NewRequest(http.MethodPost, "/api/v1/backtests", bytes.NewReader(payload))
	first.Header.Set("Content-Type", "application/json")
	first.Header.Set("Idempotency-Key", "test-20260729-0001")
	first.Header.Set("Origin", "http://localhost:3000")
	firstResponse := httptest.NewRecorder()
	handler.ServeHTTP(firstResponse, first)
	if firstResponse.Code != http.StatusAccepted {
		t.Fatalf("first status = %d body=%s", firstResponse.Code, firstResponse.Body)
	}
	if firstResponse.Header().Get("Access-Control-Allow-Origin") != "http://localhost:3000" {
		t.Fatal("expected exact configured CORS origin")
	}
	var task Task
	if err := json.Unmarshal(firstResponse.Body.Bytes(), &task); err != nil {
		t.Fatal(err)
	}
	<-runner.started

	second := httptest.NewRequest(http.MethodPost, "/api/v1/backtests", bytes.NewReader(payload))
	secondResponse := httptest.NewRecorder()
	handler.ServeHTTP(secondResponse, second)
	if secondResponse.Code != http.StatusOK {
		t.Fatalf("idempotent status = %d body=%s", secondResponse.Code, secondResponse.Body)
	}

	get := httptest.NewRequest(http.MethodGet, "/api/v1/tasks/"+task.TaskID, nil)
	getResponse := httptest.NewRecorder()
	handler.ServeHTTP(getResponse, get)
	if getResponse.Code != http.StatusOK {
		t.Fatalf("get status = %d body=%s", getResponse.Code, getResponse.Body)
	}
	runner.result <- runnerReply{
		result: RunResult{RunID: "336fe16f3f221153", Reused: false},
	}
	waitForStatus(store, task.TaskID, "succeeded")
}

func TestHTTPRejectsUnknownFieldsAndIdempotencyConflict(t *testing.T) {
	store, err := OpenTaskStore(t.TempDir(), nil)
	if err != nil {
		t.Fatal(err)
	}
	runner := &blockingRunner{
		started: make(chan Submission, 2),
		result:  make(chan runnerReply, 2),
	}
	orchestrator := NewOrchestrator(store, runner, 2, nil)
	defer orchestrator.Close()
	handler := NewHTTPHandler(orchestrator, NewExperimentStore(t.TempDir()), "")

	request := validSubmission()
	payload, _ := json.Marshal(request)
	response := httptest.NewRecorder()
	handler.ServeHTTP(
		response,
		httptest.NewRequest(http.MethodPost, "/api/v1/backtests", bytes.NewReader(payload)),
	)
	if response.Code != http.StatusAccepted {
		t.Fatalf("status = %d body=%s", response.Code, response.Body)
	}
	<-runner.started

	label := "different request"
	request.Label = &label
	conflictPayload, _ := json.Marshal(request)
	conflict := httptest.NewRecorder()
	handler.ServeHTTP(
		conflict,
		httptest.NewRequest(
			http.MethodPost,
			"/api/v1/backtests",
			bytes.NewReader(conflictPayload),
		),
	)
	if conflict.Code != http.StatusConflict {
		t.Fatalf("conflict status = %d body=%s", conflict.Code, conflict.Body)
	}

	unknown := append(payload[:len(payload)-1], []byte(`,"command":"rm"}`)...)
	invalid := httptest.NewRecorder()
	handler.ServeHTTP(
		invalid,
		httptest.NewRequest(http.MethodPost, "/api/v1/backtests", bytes.NewReader(unknown)),
	)
	if invalid.Code != http.StatusBadRequest {
		t.Fatalf("invalid status = %d body=%s", invalid.Code, invalid.Body)
	}

	runner.result <- runnerReply{err: context.Canceled}
	waitForStatus(store, responseTaskID(t, response), "failed")
}

func responseTaskID(t *testing.T, response *httptest.ResponseRecorder) string {
	t.Helper()
	var task Task
	if err := json.Unmarshal(response.Body.Bytes(), &task); err != nil {
		t.Fatal(err)
	}
	return task.TaskID
}
