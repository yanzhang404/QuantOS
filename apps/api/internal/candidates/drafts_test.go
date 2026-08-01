package candidates

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestDraftStoreListsAndReadsRateLimitedRecords(t *testing.T) {
	root := t.TempDir()
	firstProposal, firstID := draftProposal(t, "volatility-breakout", "Volatility breakout")
	secondProposal, secondID := draftProposal(t, "range-expansion", "Range expansion")
	first := validDraft(firstID, firstProposal.StrategySlug, 1)
	second := validDraft(secondID, secondProposal.StrategySlug, 2)
	writeDraft(t, root, first, firstProposal)
	writeDraft(t, root, second, secondProposal)
	store := NewDraftStore(root)

	drafts, err := store.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(drafts) != 2 || drafts[0].DraftID != second.DraftID || drafts[1].Slot != 1 {
		t.Fatalf("drafts = %#v", drafts)
	}
	loaded, err := store.Get(first.DraftID)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.ProposalID != first.ProposalID || loaded.WeeklyLimit != 2 {
		t.Fatalf("loaded = %#v", loaded)
	}
}

func TestDraftStoreRejectsDuplicateSlotsAndTamperedIdentity(t *testing.T) {
	root := t.TempDir()
	firstProposal, firstID := draftProposal(t, "volatility-breakout", "Volatility breakout")
	secondProposal, secondID := draftProposal(t, "range-expansion", "Range expansion")
	first := validDraft(firstID, firstProposal.StrategySlug, 1)
	duplicate := validDraft(secondID, secondProposal.StrategySlug, 1)
	writeDraft(t, root, first, firstProposal)
	writeDraft(t, root, duplicate, secondProposal)
	if _, err := NewDraftStore(root).List(); err == nil {
		t.Fatal("expected duplicate weekly slot to fail")
	}

	tamperedRoot := t.TempDir()
	tamperedProposal, tamperedID := draftProposal(t, "volatility-breakout", "Volatility breakout")
	tampered := validDraft(tamperedID, tamperedProposal.StrategySlug, 1)
	tampered.StrategySlug = "changed-strategy"
	writeDraft(t, tamperedRoot, tampered, tamperedProposal)
	if _, err := NewDraftStore(tamperedRoot).Get(tampered.DraftID); err == nil {
		t.Fatal("expected tampered draft identity to fail")
	}
}

func TestDraftHTTPListsRecordsAndReturnsSafeErrors(t *testing.T) {
	root := t.TempDir()
	proposal, proposalID := draftProposal(t, "volatility-breakout", "Volatility breakout")
	draft := validDraft(proposalID, proposal.StrategySlug, 1)
	writeDraft(t, root, draft, proposal)
	handler := NewDraftHTTPHandler(NewDraftStore(root), "http://localhost:3000")

	list := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/api/v1/candidate-drafts", nil)
	request.Header.Set("Origin", "http://localhost:3000")
	handler.ServeHTTP(list, request)
	if list.Code != http.StatusOK ||
		list.Header().Get("Access-Control-Allow-Origin") != "http://localhost:3000" {
		t.Fatalf("list status=%d body=%s", list.Code, list.Body)
	}

	detail := httptest.NewRecorder()
	handler.ServeHTTP(detail, httptest.NewRequest(
		http.MethodGet,
		"/api/v1/candidate-drafts/"+draft.DraftID,
		nil,
	))
	if detail.Code != http.StatusOK {
		t.Fatalf("detail status=%d body=%s", detail.Code, detail.Body)
	}

	missing := httptest.NewRecorder()
	handler.ServeHTTP(missing, httptest.NewRequest(
		http.MethodGet,
		"/api/v1/candidate-drafts/not-a-draft",
		nil,
	))
	if missing.Code != http.StatusNotFound {
		t.Fatalf("missing status=%d", missing.Code)
	}
}

func validDraft(proposalID, strategySlug string, slot int) Draft {
	week := "2026-W31"
	payload := fmt.Sprintf(
		`{"iso_week":%q,"proposal_id":%q,"schema_version":"candidate-draft.v1"}`,
		week,
		proposalID,
	)
	digest := sha256.Sum256([]byte(payload))
	return Draft{
		SchemaVersion: "candidate-draft.v1",
		DraftID:       hex.EncodeToString(digest[:])[:16],
		ProposalID:    proposalID,
		StrategySlug:  strategySlug,
		ISOWeek:       week,
		Slot:          slot,
		WeeklyLimit:   2,
		CreatedAt:     time.Date(2026, 8, 1, 8, 0, slot, 0, time.UTC),
		Status:        "prepared",
		Artifacts:     []string{"proposal.json", "review-checklist.json", "PULL_REQUEST.md"},
	}
}

func draftProposal(t *testing.T, slug, title string) (Proposal, string) {
	t.Helper()
	proposal := validRecord(t).Proposal
	proposal.StrategySlug = slug
	proposal.Title = title
	payload, err := canonicalJSON(proposal)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(payload)
	return proposal, hex.EncodeToString(digest[:])[:16]
}

func writeDraft(t *testing.T, root string, draft Draft, proposal Proposal) {
	t.Helper()
	directory := filepath.Join(root, draft.ISOWeek, draft.DraftID)
	if err := os.MkdirAll(directory, 0o700); err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(draft)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "record.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	proposalPayload, err := json.Marshal(proposal)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "proposal.json"), proposalPayload, 0o600); err != nil {
		t.Fatal(err)
	}
}
