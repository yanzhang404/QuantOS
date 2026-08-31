package robustness

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/big"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"time"
)

const maximumReviewBytes = 4 << 20

var (
	ErrReviewNotFound = errors.New("robustness review not found")
	ErrReviewInvalid  = errors.New("robustness review is invalid")
	hex16Pattern      = regexp.MustCompile(`^[0-9a-f]{16}$`)
	hex64Pattern      = regexp.MustCompile(`^[0-9a-f]{64}$`)
	versionPattern    = regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`)
	decimalPattern    = regexp.MustCompile(`^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?$`)
)

type Store struct {
	root string
}

type Strategy struct {
	Name    string          `json:"name"`
	Version string          `json:"version"`
	Winner  json.RawMessage `json:"winner"`
}

type Dataset struct {
	Version       string `json:"version"`
	ContentSHA256 string `json:"content_sha256"`
	Symbol        string `json:"symbol"`
	Interval      string `json:"interval"`
}

type Gate struct {
	Name         string          `json:"name"`
	Passed       bool            `json:"passed"`
	Reason       string          `json:"reason"`
	Observations json.RawMessage `json:"observations"`
	RunIDs       []string        `json:"run_ids"`
}

type Review struct {
	SchemaVersion    string          `json:"schema_version"`
	ReviewID         string          `json:"review_id"`
	Status           string          `json:"status"`
	CreatedAt        time.Time       `json:"created_at"`
	Passed           bool            `json:"passed"`
	Strategy         Strategy        `json:"strategy"`
	Datasets         []Dataset       `json:"datasets"`
	ResearchConfig   json.RawMessage `json:"research_config"`
	RobustnessConfig json.RawMessage `json:"robustness_config"`
	Gates            []Gate          `json:"gates"`
	WalkForward      json.RawMessage `json:"walk_forward"`
	Neighbors        json.RawMessage `json:"neighbors"`
	Markets          json.RawMessage `json:"markets"`
	Artifacts        []string        `json:"artifacts"`
}

type Summary struct {
	SchemaVersion string    `json:"schema_version"`
	ReviewID      string    `json:"review_id"`
	CreatedAt     time.Time `json:"created_at"`
	Passed        bool      `json:"passed"`
	Strategy      Strategy  `json:"strategy"`
	Datasets      []Dataset `json:"datasets"`
	Gates         []Gate    `json:"gates"`
}

func NewStore(root string) *Store {
	return &Store{root: filepath.Clean(root)}
}

func (s *Store) List() ([]Summary, error) {
	entries, err := os.ReadDir(s.root)
	if errors.Is(err, os.ErrNotExist) {
		return []Summary{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read robustness root: %w", err)
	}
	reviews := make([]Summary, 0, min(len(entries), 100))
	for _, entry := range entries {
		if !entry.IsDir() || !hex16Pattern.MatchString(entry.Name()) {
			continue
		}
		review, readErr := s.Get(entry.Name())
		if errors.Is(readErr, ErrReviewNotFound) || errors.Is(readErr, ErrReviewInvalid) {
			continue
		}
		if readErr != nil {
			return nil, readErr
		}
		reviews = append(reviews, Summary{
			SchemaVersion: review.SchemaVersion,
			ReviewID:      review.ReviewID,
			CreatedAt:     review.CreatedAt,
			Passed:        review.Passed,
			Strategy:      review.Strategy,
			Datasets:      review.Datasets,
			Gates:         review.Gates,
		})
	}
	sort.Slice(reviews, func(i, j int) bool {
		return reviews[i].CreatedAt.After(reviews[j].CreatedAt)
	})
	if len(reviews) > 100 {
		reviews = reviews[:100]
	}
	return reviews, nil
}

func (s *Store) Get(reviewID string) (Review, error) {
	if !hex16Pattern.MatchString(reviewID) {
		return Review{}, ErrReviewNotFound
	}
	path := filepath.Join(s.root, reviewID, "robustness.json")
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return Review{}, ErrReviewNotFound
	}
	if err != nil {
		return Review{}, fmt.Errorf("inspect robustness review: %w", err)
	}
	if !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > maximumReviewBytes {
		return Review{}, ErrReviewInvalid
	}
	handle, err := os.Open(path)
	if err != nil {
		return Review{}, fmt.Errorf("open robustness review: %w", err)
	}
	defer handle.Close()
	decoder := json.NewDecoder(io.LimitReader(handle, maximumReviewBytes+1))
	decoder.DisallowUnknownFields()
	var review Review
	if err := decoder.Decode(&review); err != nil {
		return Review{}, ErrReviewInvalid
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return Review{}, ErrReviewInvalid
	}
	if err := review.validate(reviewID); err != nil {
		return Review{}, errors.Join(ErrReviewInvalid, err)
	}
	return review, nil
}

func (r Review) validate(expectedID string) error {
	if (r.SchemaVersion != "robustness-review.v1" &&
		r.SchemaVersion != "robustness-review.v2") || r.ReviewID != expectedID ||
		r.Status != "completed" || r.CreatedAt.IsZero() {
		return errors.New("invalid review identity")
	}
	if !versionPattern.MatchString(r.Strategy.Version) ||
		validateWinner(r.SchemaVersion, r.Strategy) != nil {
		return errors.New("invalid review strategy")
	}
	if len(r.Datasets) < 2 || len(r.Datasets) > 8 {
		return errors.New("invalid review datasets")
	}
	symbols := make(map[string]struct{}, len(r.Datasets))
	interval := r.Datasets[0].Interval
	for _, dataset := range r.Datasets {
		if !hex16Pattern.MatchString(dataset.Version) ||
			!hex64Pattern.MatchString(dataset.ContentSHA256) ||
			(dataset.Symbol != "BTCUSDT" && dataset.Symbol != "ETHUSDT") ||
			dataset.Interval != interval {
			return errors.New("invalid review dataset")
		}
		if _, duplicate := symbols[dataset.Symbol]; duplicate {
			return errors.New("duplicate review dataset symbol")
		}
		symbols[dataset.Symbol] = struct{}{}
	}
	expectedGates := map[string]struct{}{
		"walk_forward": {}, "neighboring_parameters": {},
		"doubled_costs": {}, "multiple_markets": {},
	}
	if len(r.Gates) != len(expectedGates) {
		return errors.New("invalid robustness gate count")
	}
	allPassed := true
	for _, gate := range r.Gates {
		if _, ok := expectedGates[gate.Name]; !ok || len(gate.Reason) < 5 ||
			len(gate.Observations) < 2 || len(gate.RunIDs) == 0 {
			return errors.New("invalid robustness gate")
		}
		delete(expectedGates, gate.Name)
		for _, runID := range gate.RunIDs {
			if !hex16Pattern.MatchString(runID) {
				return errors.New("invalid robustness gate Run ID")
			}
		}
		allPassed = allPassed && gate.Passed
	}
	if len(expectedGates) != 0 || r.Passed != allPassed {
		return errors.New("robustness overall status does not match gates")
	}
	if len(r.ResearchConfig) < 2 || len(r.RobustnessConfig) < 2 ||
		len(r.WalkForward) < 2 || len(r.Neighbors) < 2 || len(r.Markets) < 2 ||
		len(r.Artifacts) != 2 || r.Artifacts[0] != "walk-forward.csv" ||
		r.Artifacts[1] != "review.md" {
		return errors.New("invalid robustness review detail")
	}
	return nil
}

type emaWinner struct {
	FastPeriod int `json:"fast_period"`
	SlowPeriod int `json:"slow_period"`
}

type donchianWinner struct {
	EntryPeriod            int    `json:"entry_period"`
	ExitPeriod             int    `json:"exit_period"`
	ATRPeriod              int    `json:"atr_period"`
	TargetAnnualVolatility string `json:"target_annual_volatility"`
	MaxExposure            string `json:"max_exposure"`
	RebalanceThreshold     string `json:"rebalance_threshold"`
}

func validateWinner(schemaVersion string, strategy Strategy) error {
	if strategy.Name == "ema-cross" {
		var winner emaWinner
		if err := decodeStrict(strategy.Winner, &winner); err != nil ||
			winner.FastPeriod < 1 || winner.SlowPeriod <= winner.FastPeriod {
			return errors.New("invalid EMA winner")
		}
		return nil
	}
	if schemaVersion != "robustness-review.v2" || strategy.Name != "donchian-atr" {
		return errors.New("unsupported robustness strategy")
	}
	var winner donchianWinner
	if err := decodeStrict(strategy.Winner, &winner); err != nil ||
		winner.EntryPeriod < 2 || winner.ExitPeriod < 1 ||
		winner.ExitPeriod > winner.EntryPeriod || winner.ATRPeriod < 2 ||
		!decimalInRange(winner.TargetAnnualVolatility, "0", "", false, false) ||
		!decimalInRange(winner.MaxExposure, "0", "1", false, true) ||
		!decimalInRange(winner.RebalanceThreshold, "0", "1", true, true) {
		return errors.New("invalid Donchian ATR winner")
	}
	return nil
}

func decodeStrict(raw json.RawMessage, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return errors.New("unexpected trailing JSON")
	}
	return nil
}

func decimalInRange(value, minimum, maximum string, includeMinimum, includeMaximum bool) bool {
	if !decimalPattern.MatchString(value) {
		return false
	}
	number, ok := new(big.Rat).SetString(value)
	if !ok {
		return false
	}
	lower, _ := new(big.Rat).SetString(minimum)
	comparison := number.Cmp(lower)
	if comparison < 0 || (comparison == 0 && !includeMinimum) {
		return false
	}
	if maximum == "" {
		return true
	}
	upper, _ := new(big.Rat).SetString(maximum)
	comparison = number.Cmp(upper)
	return comparison < 0 || (comparison == 0 && includeMaximum)
}
