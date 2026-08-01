package candidates

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"time"
)

const maximumDraftBytes = 1 << 20

var (
	ErrDraftNotFound = errors.New("candidate draft not found")
	ErrDraftInvalid  = errors.New("candidate draft is invalid")
	weekPattern      = regexp.MustCompile(`^[0-9]{4}-W(?:0[1-9]|[1-4][0-9]|5[0-3])$`)
)

type DraftStore struct {
	root string
}

type Draft struct {
	SchemaVersion string    `json:"schema_version"`
	DraftID       string    `json:"draft_id"`
	ProposalID    string    `json:"proposal_id"`
	StrategySlug  string    `json:"strategy_slug"`
	ISOWeek       string    `json:"iso_week"`
	Slot          int       `json:"slot"`
	WeeklyLimit   int       `json:"weekly_limit"`
	CreatedAt     time.Time `json:"created_at"`
	Status        string    `json:"status"`
	Artifacts     []string  `json:"artifacts"`
}

func NewDraftStore(root string) *DraftStore {
	return &DraftStore{root: filepath.Clean(root)}
}

func (s *DraftStore) List() ([]Draft, error) {
	weeks, err := os.ReadDir(s.root)
	if errors.Is(err, os.ErrNotExist) {
		return []Draft{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read candidate draft root: %w", err)
	}
	drafts := make([]Draft, 0, min(len(weeks)*2, 520))
	for _, week := range weeks {
		if !week.IsDir() || week.Type()&os.ModeSymlink != 0 || !weekPattern.MatchString(week.Name()) {
			continue
		}
		entries, readErr := os.ReadDir(filepath.Join(s.root, week.Name()))
		if readErr != nil {
			return nil, fmt.Errorf("read candidate draft week: %w", readErr)
		}
		for _, entry := range entries {
			if !entry.IsDir() || entry.Type()&os.ModeSymlink != 0 || !hex16Pattern.MatchString(entry.Name()) {
				continue
			}
			draft, readErr := s.read(week.Name(), entry.Name())
			if readErr != nil {
				return nil, readErr
			}
			drafts = append(drafts, draft)
			if len(drafts) > 520 {
				return nil, ErrDraftInvalid
			}
		}
	}
	if !validDraftHistory(drafts) {
		return nil, ErrDraftInvalid
	}
	sort.Slice(drafts, func(i, j int) bool {
		return drafts[i].CreatedAt.After(drafts[j].CreatedAt)
	})
	return drafts, nil
}

func (s *DraftStore) Get(draftID string) (Draft, error) {
	if !hex16Pattern.MatchString(draftID) {
		return Draft{}, ErrDraftNotFound
	}
	drafts, err := s.List()
	if err != nil {
		return Draft{}, err
	}
	for _, draft := range drafts {
		if draft.DraftID == draftID {
			return draft, nil
		}
	}
	return Draft{}, ErrDraftNotFound
}

func (s *DraftStore) read(week, draftID string) (Draft, error) {
	path := filepath.Join(s.root, week, draftID, "record.json")
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return Draft{}, ErrDraftInvalid
	}
	if err != nil {
		return Draft{}, fmt.Errorf("inspect candidate draft: %w", err)
	}
	if !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > maximumDraftBytes {
		return Draft{}, ErrDraftInvalid
	}
	handle, err := os.Open(path)
	if err != nil {
		return Draft{}, fmt.Errorf("open candidate draft: %w", err)
	}
	defer handle.Close()
	decoder := json.NewDecoder(io.LimitReader(handle, maximumDraftBytes+1))
	decoder.DisallowUnknownFields()
	var draft Draft
	if err := decoder.Decode(&draft); err != nil {
		return Draft{}, ErrDraftInvalid
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return Draft{}, ErrDraftInvalid
	}
	if !draft.valid(week, draftID) {
		return Draft{}, ErrDraftInvalid
	}
	proposal, err := readDraftProposal(filepath.Join(s.root, week, draftID, "proposal.json"))
	if err != nil || proposal.validate(draft.ProposalID) != nil ||
		proposal.StrategySlug != draft.StrategySlug || len(proposal.Parameters) > 6 ||
		len(proposal.SupportedIntervals) > 3 {
		return Draft{}, ErrDraftInvalid
	}
	return draft, nil
}

func readDraftProposal(path string) (Proposal, error) {
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Size() <= 0 ||
		info.Size() > maximumRecordBytes {
		return Proposal{}, ErrDraftInvalid
	}
	handle, err := os.Open(path)
	if err != nil {
		return Proposal{}, err
	}
	defer handle.Close()
	decoder := json.NewDecoder(io.LimitReader(handle, maximumRecordBytes+1))
	decoder.DisallowUnknownFields()
	var proposal Proposal
	if err := decoder.Decode(&proposal); err != nil {
		return Proposal{}, ErrDraftInvalid
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return Proposal{}, ErrDraftInvalid
	}
	return proposal, nil
}

func (d Draft) valid(expectedWeek, expectedID string) bool {
	artifacts := []string{"proposal.json", "review-checklist.json", "PULL_REQUEST.md"}
	if d.SchemaVersion != "candidate-draft.v1" || d.Status != "prepared" ||
		d.DraftID != expectedID || d.ISOWeek != expectedWeek ||
		!hex16Pattern.MatchString(d.DraftID) || !hex16Pattern.MatchString(d.ProposalID) ||
		!slugPattern.MatchString(d.StrategySlug) || !weekPattern.MatchString(d.ISOWeek) ||
		d.Slot < 1 || d.Slot > 2 || d.WeeklyLimit < 1 || d.WeeklyLimit > 2 ||
		d.Slot > d.WeeklyLimit || d.CreatedAt.IsZero() || len(d.Artifacts) != len(artifacts) {
		return false
	}
	for index := range artifacts {
		if d.Artifacts[index] != artifacts[index] {
			return false
		}
	}
	payload := fmt.Sprintf(
		`{"iso_week":%q,"proposal_id":%q,"schema_version":"candidate-draft.v1"}`,
		d.ISOWeek,
		d.ProposalID,
	)
	digest := sha256.Sum256([]byte(payload))
	return hex.EncodeToString(digest[:])[:16] == d.DraftID
}

func validDraftHistory(drafts []Draft) bool {
	proposalIDs := map[string]bool{}
	slots := map[string]bool{}
	counts := map[string]int{}
	for _, draft := range drafts {
		slot := fmt.Sprintf("%s/%d", draft.ISOWeek, draft.Slot)
		if proposalIDs[draft.ProposalID] || slots[slot] {
			return false
		}
		proposalIDs[draft.ProposalID] = true
		slots[slot] = true
		counts[draft.ISOWeek]++
		if counts[draft.ISOWeek] > 2 {
			return false
		}
	}
	return true
}
