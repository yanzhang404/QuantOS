package robustness

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
	if request.URL.Path == "/api/v1/robustness" {
		reviews, err := h.store.List()
		if err != nil {
			writeError(response, http.StatusInternalServerError, "robustness_list_failed", "Robustness reviews could not be listed.")
			return
		}
		writeJSON(response, http.StatusOK, map[string]any{"reviews": reviews})
		return
	}
	const prefix = "/api/v1/robustness/"
	if !strings.HasPrefix(request.URL.Path, prefix) {
		writeError(response, http.StatusNotFound, "not_found", "Resource not found.")
		return
	}
	review, err := h.store.Get(strings.TrimPrefix(request.URL.Path, prefix))
	if errors.Is(err, ErrReviewNotFound) {
		writeError(response, http.StatusNotFound, "robustness_not_found", "Robustness review not found.")
		return
	}
	if errors.Is(err, ErrReviewInvalid) {
		writeError(response, http.StatusUnprocessableEntity, "robustness_invalid", "Robustness review is invalid.")
		return
	}
	if err != nil {
		writeError(response, http.StatusInternalServerError, "robustness_read_failed", "Robustness review could not be read.")
		return
	}
	writeJSON(response, http.StatusOK, review)
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
