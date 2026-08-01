package candidates

import (
	"errors"
	"net/http"
	"strings"
)

type DraftHTTPHandler struct {
	store         *DraftStore
	allowedOrigin string
}

func NewDraftHTTPHandler(store *DraftStore, allowedOrigin string) http.Handler {
	return &DraftHTTPHandler{store: store, allowedOrigin: allowedOrigin}
}

func (h *DraftHTTPHandler) ServeHTTP(response http.ResponseWriter, request *http.Request) {
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
	if request.URL.Path == "/api/v1/candidate-drafts" {
		drafts, err := h.store.List()
		if err != nil {
			writeError(response, http.StatusInternalServerError, "candidate_draft_list_failed", "Candidate drafts could not be listed.")
			return
		}
		writeJSON(response, http.StatusOK, map[string]any{"drafts": drafts})
		return
	}
	const prefix = "/api/v1/candidate-drafts/"
	if !strings.HasPrefix(request.URL.Path, prefix) {
		writeError(response, http.StatusNotFound, "not_found", "Resource not found.")
		return
	}
	draft, err := h.store.Get(strings.TrimPrefix(request.URL.Path, prefix))
	if errors.Is(err, ErrDraftNotFound) {
		writeError(response, http.StatusNotFound, "candidate_draft_not_found", "Candidate draft not found.")
		return
	}
	if errors.Is(err, ErrDraftInvalid) {
		writeError(response, http.StatusUnprocessableEntity, "candidate_draft_invalid", "Candidate draft is invalid.")
		return
	}
	if err != nil {
		writeError(response, http.StatusInternalServerError, "candidate_draft_read_failed", "Candidate draft could not be read.")
		return
	}
	writeJSON(response, http.StatusOK, draft)
}
