package candidates

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestStoreListsAndReadsValidatedCandidateRecords(t *testing.T) {
	root := t.TempDir()
	record := validRecord(t)
	writeRecord(t, root, record)
	store := NewStore(root)

	records, err := store.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(records) != 1 || records[0].ProposalID != record.ProposalID ||
		records[0].Proposal.StrategySlug != "volatility-breakout" {
		t.Fatalf("records = %#v", records)
	}
	loaded, err := store.Get(record.ProposalID)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.Status != "proposed" || loaded.Proposal.Parameters[0].Key != "entry_period" {
		t.Fatalf("loaded = %#v", loaded)
	}
}

func TestProposalIdentityMatchesPythonContractExample(t *testing.T) {
	payload, err := os.ReadFile("../../../../examples/candidates/sample-proposal.v1.json")
	if err != nil {
		t.Fatal(err)
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	var proposal Proposal
	if err := decoder.Decode(&proposal); err != nil {
		t.Fatal(err)
	}
	canonical, err := canonicalJSON(proposal)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(canonical)
	if got := hex.EncodeToString(digest[:])[:16]; got != "f4af198752ab61ab" {
		t.Fatalf("proposal ID = %s", got)
	}
}

func TestStoreRejectsTamperedIdentityAndSymlink(t *testing.T) {
	root := t.TempDir()
	record := validRecord(t)
	record.Proposal.Title = "Tampered candidate title"
	writeRecord(t, root, record)
	if _, err := NewStore(root).Get(record.ProposalID); err == nil {
		t.Fatal("expected a tampered proposal to fail")
	}

	symlinkRoot := t.TempDir()
	target := filepath.Join(symlinkRoot, "target.json")
	payload, _ := json.Marshal(validRecord(t))
	if err := os.WriteFile(target, payload, 0o600); err != nil {
		t.Fatal(err)
	}
	record = validRecord(t)
	if err := os.Symlink(target, filepath.Join(symlinkRoot, record.ProposalID+".json")); err != nil {
		t.Fatal(err)
	}
	if _, err := NewStore(symlinkRoot).Get(record.ProposalID); err == nil {
		t.Fatal("expected a symlinked candidate to fail")
	}
}

func TestHTTPListsCandidatesAndReturnsSafeErrors(t *testing.T) {
	root := t.TempDir()
	record := validRecord(t)
	writeRecord(t, root, record)
	handler := NewHTTPHandler(NewStore(root), "http://localhost:3000")

	list := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/api/v1/candidates", nil)
	request.Header.Set("Origin", "http://localhost:3000")
	handler.ServeHTTP(list, request)
	if list.Code != http.StatusOK ||
		list.Header().Get("Access-Control-Allow-Origin") != "http://localhost:3000" {
		t.Fatalf("list status=%d headers=%v body=%s", list.Code, list.Header(), list.Body)
	}

	detail := httptest.NewRecorder()
	handler.ServeHTTP(detail, httptest.NewRequest(
		http.MethodGet,
		"/api/v1/candidates/"+record.ProposalID,
		nil,
	))
	if detail.Code != http.StatusOK {
		t.Fatalf("detail status=%d body=%s", detail.Code, detail.Body)
	}

	missing := httptest.NewRecorder()
	handler.ServeHTTP(missing, httptest.NewRequest(
		http.MethodGet,
		"/api/v1/candidates/not-a-candidate",
		nil,
	))
	if missing.Code != http.StatusNotFound {
		t.Fatalf("missing status=%d", missing.Code)
	}
}

func validRecord(t *testing.T) Record {
	t.Helper()
	proposal := Proposal{
		SchemaVersion: "candidate-proposal.v1",
		StrategySlug:  "volatility-breakout",
		Title:         "Volatility-adjusted channel breakout",
		Hypothesis: "A channel breakout sized by recent volatility may retain trend exposure " +
			"while limiting concentration during turbulent regimes.",
		Rationale: "This explainable candidate requires deterministic implementation and " +
			"independent robustness evidence before any human decision.",
		Category:           "trend",
		SupportedIntervals: []string{"4h", "1d"},
		Parameters: []Parameter{
			{
				Key: "entry_period", Kind: "integer", Label: "Entry channel bars",
				Default: json.RawMessage("55"), Minimum: json.RawMessage("20"),
				Maximum: json.RawMessage("120"),
			},
		},
		ImplementationPlan: []string{"Define the signal through the shared strategy interface."},
		ResearchPlan:       []string{"Evaluate immutable datasets across non-overlapping periods."},
		Sources: []Source{
			{Title: "Time Series Momentum", URL: "https://doi.org/10.1016/j.jfineco.2011.11.003"},
		},
		ProposedBy: ProposedBy{
			Kind: "agent", Name: "quantos-research-agent", WorkflowVersion: "1.0.0",
		},
	}
	payload, err := canonicalJSON(proposal)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(payload)
	proposalID := hex.EncodeToString(digest[:])[:16]
	created := time.Date(2026, 8, 1, 8, 0, 0, 0, time.UTC)
	return Record{
		SchemaVersion: "candidate-record.v1", ProposalID: proposalID,
		CreatedAt: created, UpdatedAt: created, Status: "proposed", Proposal: proposal,
		Transitions: []Transition{
			{
				ToStatus: "proposed", ActorKind: "agent", ActorName: "quantos-research-agent",
				Rationale:  "Bounded candidate proposal accepted for human-visible research review.",
				OccurredAt: created,
			},
		},
	}
}

func writeRecord(t *testing.T, root string, record Record) {
	t.Helper()
	payload, err := json.Marshal(record)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, record.ProposalID+".json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
}
