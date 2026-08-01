package candidates

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"
)

type HTTPHandler struct {
	store         *Store
	allowedOrigin string
}

func NewHTTPHandler(store *Store, allowedOrigin string) http.Handler {
	return &HTTPHandler{store: store, allowedOrigin: allowedOrigin}
}

func (h *HTTPHandler) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	if h.allowedOrigin != "" && request.Header.Get("Origin") == h.allowedOrigin {
		response.Header().Set("Access-Control-Allow-Origin", h.allowedOrigin)
		response.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
		response.Header().Set("Vary", "Origin")
	}
	if request.Method == http.MethodOptions {
		response.WriteHeader(http.StatusNoContent)
		return
	}
	if request.Method != http.MethodGet {
		writeError(response, http.StatusNotFound, "not_found", "Resource not found.")
		return
	}
	if request.URL.Path == "/api/v1/candidates" {
		records, err := h.store.List()
		if err != nil {
			writeError(response, http.StatusInternalServerError, "candidate_list_failed", "Candidates could not be listed.")
			return
		}
		writeJSON(response, http.StatusOK, map[string]any{"candidates": records})
		return
	}
	const prefix = "/api/v1/candidates/"
	if !strings.HasPrefix(request.URL.Path, prefix) {
		writeError(response, http.StatusNotFound, "not_found", "Resource not found.")
		return
	}
	record, err := h.store.Get(strings.TrimPrefix(request.URL.Path, prefix))
	if errors.Is(err, ErrCandidateNotFound) {
		writeError(response, http.StatusNotFound, "candidate_not_found", "Candidate not found.")
		return
	}
	if errors.Is(err, ErrCandidateInvalid) {
		writeError(response, http.StatusUnprocessableEntity, "candidate_invalid", "Candidate record is invalid.")
		return
	}
	if err != nil {
		writeError(response, http.StatusInternalServerError, "candidate_read_failed", "Candidate could not be read.")
		return
	}
	writeJSON(response, http.StatusOK, record)
}

func writeJSON(response http.ResponseWriter, status int, value any) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(value)
}

func writeError(response http.ResponseWriter, status int, code, message string) {
	writeJSON(response, status, map[string]any{
		"error": map[string]string{"code": code, "message": message},
	})
}
