// Package candidates exposes validated, read-only strategy candidate records.
package candidates

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

const maximumRecordBytes = 2 << 20

var (
	ErrCandidateNotFound  = errors.New("candidate not found")
	ErrCandidateInvalid   = errors.New("candidate record is invalid")
	hex16Pattern          = regexp.MustCompile(`^[0-9a-f]{16}$`)
	hex64Pattern          = regexp.MustCompile(`^[0-9a-f]{64}$`)
	slugPattern           = regexp.MustCompile(`^[a-z][a-z0-9-]{2,39}$`)
	keyPattern            = regexp.MustCompile(`^[a-z][a-z0-9_]{1,39}$`)
	versionPattern        = regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`)
	implementationPattern = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_.]{7,159}$`)
	testIDPattern         = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.:/-]{3,159}$`)
	actorPattern          = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_. -]{1,79}$`)
)

type Store struct {
	root string
}

type Parameter struct {
	Key     string          `json:"key"`
	Kind    string          `json:"kind"`
	Label   string          `json:"label"`
	Default json.RawMessage `json:"default"`
	Minimum json.RawMessage `json:"minimum"`
	Maximum json.RawMessage `json:"maximum"`
}

type Source struct {
	Title string `json:"title"`
	URL   string `json:"url"`
}

type ProposedBy struct {
	Kind            string `json:"kind"`
	Name            string `json:"name"`
	WorkflowVersion string `json:"workflow_version"`
}

type Proposal struct {
	SchemaVersion      string      `json:"schema_version"`
	StrategySlug       string      `json:"strategy_slug"`
	Title              string      `json:"title"`
	Hypothesis         string      `json:"hypothesis"`
	Rationale          string      `json:"rationale"`
	Category           string      `json:"category"`
	SupportedIntervals []string    `json:"supported_intervals"`
	Parameters         []Parameter `json:"parameters"`
	ImplementationPlan []string    `json:"implementation_plan"`
	ResearchPlan       []string    `json:"research_plan"`
	Sources            []Source    `json:"sources"`
	ProposedBy         ProposedBy  `json:"proposed_by"`
}

type Implementation struct {
	ImplementationRef string   `json:"implementation_ref"`
	TestIDs           []string `json:"test_ids"`
}

type Transition struct {
	FromStatus *string   `json:"from_status"`
	ToStatus   string    `json:"to_status"`
	ActorKind  string    `json:"actor_kind"`
	ActorName  string    `json:"actor_name"`
	Rationale  string    `json:"rationale"`
	OccurredAt time.Time `json:"occurred_at"`
	EvidenceID *string   `json:"evidence_id"`
}

type Record struct {
	SchemaVersion      string          `json:"schema_version"`
	ProposalID         string          `json:"proposal_id"`
	CreatedAt          time.Time       `json:"created_at"`
	UpdatedAt          time.Time       `json:"updated_at"`
	Status             string          `json:"status"`
	Proposal           Proposal        `json:"proposal"`
	Implementation     *Implementation `json:"implementation"`
	RobustnessReviewID *string         `json:"robustness_review_id"`
	RobustnessSHA256   *string         `json:"robustness_sha256"`
	Transitions        []Transition    `json:"transitions"`
}

func NewStore(root string) *Store {
	return &Store{root: filepath.Clean(root)}
}

func (s *Store) List() ([]Record, error) {
	entries, err := os.ReadDir(s.root)
	if errors.Is(err, os.ErrNotExist) {
		return []Record{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read candidate root: %w", err)
	}
	records := make([]Record, 0, min(len(entries), 100))
	for _, entry := range entries {
		if entry.IsDir() || !hex16Pattern.MatchString(strings.TrimSuffix(entry.Name(), ".json")) ||
			filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		record, readErr := s.Get(strings.TrimSuffix(entry.Name(), ".json"))
		if errors.Is(readErr, ErrCandidateNotFound) || errors.Is(readErr, ErrCandidateInvalid) {
			continue
		}
		if readErr != nil {
			return nil, readErr
		}
		records = append(records, record)
	}
	sort.Slice(records, func(i, j int) bool {
		return records[i].CreatedAt.After(records[j].CreatedAt)
	})
	if len(records) > 100 {
		records = records[:100]
	}
	return records, nil
}

func (s *Store) Get(proposalID string) (Record, error) {
	if !hex16Pattern.MatchString(proposalID) {
		return Record{}, ErrCandidateNotFound
	}
	path := filepath.Join(s.root, proposalID+".json")
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return Record{}, ErrCandidateNotFound
	}
	if err != nil {
		return Record{}, fmt.Errorf("inspect candidate record: %w", err)
	}
	if !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > maximumRecordBytes {
		return Record{}, ErrCandidateInvalid
	}
	handle, err := os.Open(path)
	if err != nil {
		return Record{}, fmt.Errorf("open candidate record: %w", err)
	}
	defer handle.Close()
	decoder := json.NewDecoder(io.LimitReader(handle, maximumRecordBytes+1))
	decoder.DisallowUnknownFields()
	var record Record
	if err := decoder.Decode(&record); err != nil {
		return Record{}, ErrCandidateInvalid
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return Record{}, ErrCandidateInvalid
	}
	if err := record.validate(proposalID); err != nil {
		return Record{}, errors.Join(ErrCandidateInvalid, err)
	}
	return record, nil
}

func (r Record) validate(expectedID string) error {
	if r.SchemaVersion != "candidate-record.v1" || r.ProposalID != expectedID ||
		r.CreatedAt.IsZero() || r.UpdatedAt.IsZero() || r.UpdatedAt.Before(r.CreatedAt) {
		return errors.New("invalid candidate identity")
	}
	if err := r.Proposal.validate(expectedID); err != nil {
		return err
	}
	return r.validateTransitions()
}

func (p Proposal) validate(expectedID string) error {
	if p.SchemaVersion != "candidate-proposal.v1" || !slugPattern.MatchString(p.StrategySlug) ||
		p.StrategySlug == "buy-and-hold" || p.StrategySlug == "ema-cross" ||
		p.StrategySlug == "donchian-atr" || !textLength(p.Title, 4, 120) ||
		!textLength(p.Hypothesis, 20, 500) || !textLength(p.Rationale, 20, 1000) {
		return errors.New("invalid candidate proposal")
	}
	if p.Category != "trend" && p.Category != "mean_reversion" && p.Category != "intraday" {
		return errors.New("invalid candidate category")
	}
	if !validIntervals(p.SupportedIntervals) || !validParameters(p.Parameters) ||
		!validPlans(p.ImplementationPlan) || !validPlans(p.ResearchPlan) ||
		!validSources(p.Sources) || p.ProposedBy.Kind != "agent" ||
		!textLength(p.ProposedBy.Name, 2, 80) ||
		!versionPattern.MatchString(p.ProposedBy.WorkflowVersion) {
		return errors.New("invalid candidate proposal detail")
	}
	payload, err := canonicalJSON(p)
	if err != nil {
		return errors.New("encode candidate proposal")
	}
	digest := sha256.Sum256(payload)
	if hex.EncodeToString(digest[:])[:16] != expectedID {
		return errors.New("candidate proposal identity mismatch")
	}
	return nil
}

func (r Record) validateTransitions() error {
	if len(r.Transitions) < 1 || len(r.Transitions) > 5 ||
		!r.CreatedAt.Equal(r.Transitions[0].OccurredAt) ||
		!r.UpdatedAt.Equal(r.Transitions[len(r.Transitions)-1].OccurredAt) ||
		r.Status != r.Transitions[len(r.Transitions)-1].ToStatus {
		return errors.New("invalid candidate transition history")
	}
	allowed := map[string]map[string]bool{
		"":             {"proposed": true},
		"proposed":     {"implemented": true, "rejected": true},
		"implemented":  {"review_ready": true, "rejected": true},
		"review_ready": {"approved": true, "rejected": true},
	}
	actor := map[string]string{
		"proposed": "agent", "implemented": "agent", "review_ready": "system",
		"approved": "human", "rejected": "human",
	}
	previous := ""
	visited := map[string]bool{}
	for index, transition := range r.Transitions {
		from := ""
		if transition.FromStatus != nil {
			from = *transition.FromStatus
		}
		minimumRationale := 8
		if transition.ToStatus == "approved" || transition.ToStatus == "rejected" {
			minimumRationale = 20
		}
		if from != previous || !allowed[previous][transition.ToStatus] ||
			transition.ActorKind != actor[transition.ToStatus] ||
			!actorPattern.MatchString(transition.ActorName) ||
			!textLength(transition.Rationale, minimumRationale, 500) ||
			transition.OccurredAt.IsZero() ||
			(index > 0 && transition.OccurredAt.Before(r.Transitions[index-1].OccurredAt)) {
			return errors.New("invalid candidate transition")
		}
		visited[transition.ToStatus] = true
		previous = transition.ToStatus
	}
	implementationRequired := visited["implemented"]
	reviewRequired := visited["review_ready"]
	if (r.Implementation != nil) != implementationRequired ||
		!validImplementation(r.Implementation, implementationRequired) {
		return errors.New("invalid candidate implementation evidence")
	}
	if reviewRequired {
		if r.RobustnessReviewID == nil || !hex16Pattern.MatchString(*r.RobustnessReviewID) ||
			r.RobustnessSHA256 == nil || !hex64Pattern.MatchString(*r.RobustnessSHA256) {
			return errors.New("invalid candidate robustness evidence")
		}
	} else if r.RobustnessReviewID != nil || r.RobustnessSHA256 != nil {
		return errors.New("unexpected candidate robustness evidence")
	}
	if !validTransitionEvidence(r) {
		return errors.New("invalid candidate transition evidence")
	}
	return nil
}

func validTransitionEvidence(record Record) bool {
	for _, transition := range record.Transitions {
		switch transition.ToStatus {
		case "proposed", "rejected":
			if transition.ToStatus == "proposed" && transition.EvidenceID != nil {
				return false
			}
			if transition.ToStatus == "rejected" && transition.EvidenceID != nil &&
				(record.RobustnessReviewID == nil || *transition.EvidenceID != *record.RobustnessReviewID) {
				return false
			}
		case "implemented":
			if transition.EvidenceID == nil || record.Implementation == nil ||
				*transition.EvidenceID != record.Implementation.ImplementationRef {
				return false
			}
		case "review_ready", "approved":
			if transition.EvidenceID == nil || record.RobustnessReviewID == nil ||
				*transition.EvidenceID != *record.RobustnessReviewID {
				return false
			}
		}
	}
	return true
}

func validIntervals(values []string) bool {
	if len(values) < 1 || len(values) > 5 {
		return false
	}
	allowed := map[string]bool{"5m": true, "15m": true, "1h": true, "4h": true, "1d": true}
	seen := map[string]bool{}
	for _, value := range values {
		if !allowed[value] || seen[value] {
			return false
		}
		seen[value] = true
	}
	return true
}

func validParameters(values []Parameter) bool {
	if len(values) < 1 || len(values) > 12 {
		return false
	}
	seen := map[string]bool{}
	for _, value := range values {
		if !keyPattern.MatchString(value.Key) || seen[value.Key] ||
			(value.Kind != "integer" && value.Kind != "decimal") ||
			!textLength(value.Label, 2, 80) || !validParameterValues(value) {
			return false
		}
		seen[value.Key] = true
	}
	return true
}

func validParameterValues(value Parameter) bool {
	values := []json.RawMessage{value.Minimum, value.Default, value.Maximum}
	if value.Kind == "integer" {
		parsed := make([]int64, 3)
		for index, raw := range values {
			decoder := json.NewDecoder(bytes.NewReader(raw))
			if err := decoder.Decode(&parsed[index]); err != nil {
				return false
			}
		}
		return parsed[0] <= parsed[1] && parsed[1] <= parsed[2]
	}
	parsed := make([]string, 3)
	for index, raw := range values {
		if err := json.Unmarshal(raw, &parsed[index]); err != nil || !plainDecimal(parsed[index]) {
			return false
		}
	}
	var numbers [3]*big.Rat
	for index, value := range parsed {
		numbers[index] = new(big.Rat)
		if _, ok := numbers[index].SetString(value); !ok {
			return false
		}
	}
	return numbers[0].Cmp(numbers[1]) <= 0 && numbers[1].Cmp(numbers[2]) <= 0
}

func validPlans(values []string) bool {
	if len(values) < 1 || len(values) > 8 {
		return false
	}
	markers := []string{"\n", "`", "$(", "&&", "||", ";", "<script", "../", "/etc/"}
	for _, value := range values {
		if !textLength(value, 8, 200) {
			return false
		}
		lower := strings.ToLower(value)
		for _, marker := range markers {
			if strings.Contains(lower, marker) {
				return false
			}
		}
	}
	return true
}

func validSources(values []Source) bool {
	if len(values) < 1 || len(values) > 8 {
		return false
	}
	seen := map[string]bool{}
	for _, source := range values {
		parsed, err := url.Parse(source.URL)
		if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" ||
			parsed.User != nil || parsed.Hostname() == "localhost" ||
			parsed.Hostname() == "127.0.0.1" || parsed.Hostname() == "::1" ||
			!textLength(source.Title, 4, 200) || !textLength(source.URL, 8, 500) ||
			seen[source.URL] {
			return false
		}
		seen[source.URL] = true
	}
	return true
}

func validImplementation(value *Implementation, required bool) bool {
	if !required {
		return value == nil
	}
	if value == nil || !implementationPattern.MatchString(value.ImplementationRef) ||
		len(value.TestIDs) < 1 || len(value.TestIDs) > 20 {
		return false
	}
	seen := map[string]bool{}
	for _, testID := range value.TestIDs {
		if !testIDPattern.MatchString(testID) || seen[testID] {
			return false
		}
		seen[testID] = true
	}
	return true
}

func textLength(value string, minimum, maximum int) bool {
	return value == strings.TrimSpace(value) && len(value) >= minimum && len(value) <= maximum
}

func plainDecimal(value string) bool {
	matched, _ := regexp.MatchString(`^-?(0|[1-9][0-9]*)(\.[0-9]+)?$`, value)
	return matched
}

func canonicalJSON(value any) ([]byte, error) {
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	decoder := json.NewDecoder(bytes.NewReader(encoded))
	decoder.UseNumber()
	var normalized any
	if err := decoder.Decode(&normalized); err != nil {
		return nil, err
	}
	var output bytes.Buffer
	encoder := json.NewEncoder(&output)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(normalized); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(output.Bytes(), []byte("\n")), nil
}
