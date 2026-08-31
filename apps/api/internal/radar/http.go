package radar

import (
	"encoding/json"
	"errors"
	"net/http"
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
	if request.URL.Path == "/api/v1/radar/health" {
		h.serveHealth(response)
		return
	}
	if request.URL.Path != "/api/v1/radar/latest" {
		writeError(response, http.StatusNotFound, "not_found", "Resource not found.")
		return
	}
	snapshot, err := h.store.Latest()
	if errors.Is(err, ErrSnapshotUnavailable) {
		writeError(response, http.StatusServiceUnavailable, "radar_unavailable", "Market Radar has not been published yet.")
		return
	}
	if errors.Is(err, ErrSnapshotInvalid) {
		writeError(response, http.StatusUnprocessableEntity, "radar_invalid", "The latest Market Radar snapshot is invalid.")
		return
	}
	if err != nil {
		writeError(response, http.StatusInternalServerError, "radar_read_failed", "Market Radar could not be read.")
		return
	}
	writeJSON(response, http.StatusOK, snapshot)
}

func (h *HTTPHandler) serveHealth(response http.ResponseWriter) {
	health, err := h.store.Health()
	if errors.Is(err, ErrHealthUnavailable) {
		writeError(response, http.StatusServiceUnavailable, "radar_health_unavailable", "Market Radar refresh has not run yet.")
		return
	}
	if errors.Is(err, ErrHealthInvalid) {
		writeError(response, http.StatusUnprocessableEntity, "radar_health_invalid", "Market Radar refresh health is invalid.")
		return
	}
	if err != nil {
		writeError(response, http.StatusInternalServerError, "radar_health_read_failed", "Market Radar refresh health could not be read.")
		return
	}
	writeJSON(response, http.StatusOK, health)
}

func writeJSON(response http.ResponseWriter, status int, value any) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(value)
}

func writeError(response http.ResponseWriter, status int, code, message string) {
	writeJSON(response, status, map[string]any{"error": map[string]string{"code": code, "message": message}})
}
