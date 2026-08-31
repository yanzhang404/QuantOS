package intelligence

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
	if request.URL.Path == "/api/v1/intelligence/health" {
		h.serveHealth(response)
		return
	}
	if request.URL.Path != "/api/v1/intelligence/latest" {
		writeError(response, http.StatusNotFound, "not_found", "Resource not found.")
		return
	}
	snapshot, err := h.store.Latest()
	if errors.Is(err, ErrSnapshotUnavailable) {
		writeError(
			response,
			http.StatusServiceUnavailable,
			"intelligence_unavailable",
			"Daily intelligence has not been published yet.",
		)
		return
	}
	if errors.Is(err, ErrSnapshotInvalid) {
		writeError(
			response,
			http.StatusUnprocessableEntity,
			"intelligence_invalid",
			"The latest daily intelligence snapshot is invalid.",
		)
		return
	}
	if err != nil {
		writeError(
			response,
			http.StatusInternalServerError,
			"intelligence_read_failed",
			"Daily intelligence could not be read.",
		)
		return
	}
	writeJSON(response, http.StatusOK, snapshot)
}

func (h *HTTPHandler) serveHealth(response http.ResponseWriter) {
	health, err := h.store.Health()
	if errors.Is(err, ErrHealthUnavailable) {
		writeError(response, http.StatusServiceUnavailable, "intelligence_health_unavailable", "Daily refresh has not run yet.")
		return
	}
	if errors.Is(err, ErrHealthInvalid) {
		writeError(response, http.StatusUnprocessableEntity, "intelligence_health_invalid", "Daily refresh health is invalid.")
		return
	}
	if err != nil {
		writeError(response, http.StatusInternalServerError, "intelligence_health_read_failed", "Daily refresh health could not be read.")
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
	writeJSON(response, status, map[string]any{
		"error": map[string]string{"code": code, "message": message},
	})
}
