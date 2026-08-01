package intelligence

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/url"
	"os"
	"path/filepath"
	"time"
)

const (
	SchemaVersion      = "1.0"
	MethodologyVersion = "quantos-sentiment-v1.0.0"
	GeneratorVersion   = "0.1.0"
	maximumFileSize    = 2 << 20
)

var (
	ErrSnapshotUnavailable = errors.New("daily intelligence snapshot is unavailable")
	ErrSnapshotInvalid     = errors.New("daily intelligence snapshot is invalid")
)

type Store struct {
	root string
}

type Snapshot struct {
	SchemaVersion      string     `json:"schema_version"`
	MethodologyVersion string     `json:"methodology_version"`
	Date               string     `json:"date"`
	AsOf               string     `json:"as_of"`
	Status             string     `json:"status"`
	Score              float64    `json:"score"`
	PreviousScore      *float64   `json:"previous_score"`
	Change             *float64   `json:"change"`
	Label              string     `json:"label"`
	MarketScore        float64    `json:"market_score"`
	NewsScore          float64    `json:"news_score"`
	Factors            []Factor   `json:"factors"`
	Brief              Brief      `json:"brief"`
	Provenance         Provenance `json:"provenance"`
}

type Factor struct {
	Key          string  `json:"key"`
	RawValue     float64 `json:"raw_value"`
	Unit         string  `json:"unit"`
	Percentile   float64 `json:"percentile"`
	Source       string  `json:"source"`
	ObservedAt   string  `json:"observed_at"`
	Weight       float64 `json:"weight"`
	Direction    string  `json:"direction"`
	Score        float64 `json:"score"`
	Contribution float64 `json:"contribution"`
}

type Brief struct {
	Title        string     `json:"title"`
	TitleZH      string     `json:"title_zh"`
	Summary      string     `json:"summary"`
	SummaryZH    string     `json:"summary_zh"`
	Highlights   []string   `json:"highlights"`
	HighlightsZH []string   `json:"highlights_zh"`
	News         []NewsItem `json:"news"`
}

type NewsItem struct {
	ID          string   `json:"id"`
	Title       string   `json:"title"`
	TitleZH     string   `json:"title_zh,omitempty"`
	Summary     string   `json:"summary"`
	SummaryZH   string   `json:"summary_zh,omitempty"`
	URL         string   `json:"url"`
	Source      string   `json:"source"`
	PublishedAt string   `json:"published_at"`
	Assets      []string `json:"assets"`
	Sentiment   float64  `json:"sentiment"`
	Confidence  float64  `json:"confidence"`
	Relevance   float64  `json:"relevance"`
}

type Provenance struct {
	InputSHA256      string `json:"input_sha256"`
	GeneratorVersion string `json:"generator_version"`
	FactorCount      int    `json:"factor_count"`
	NewsCount        int    `json:"news_count"`
}

type factorMethod struct {
	weight    float64
	direction string
}

var factorMethods = map[string]factorMethod{
	"crypto_volatility":     {weight: 0.20, direction: "fear_when_high"},
	"options_positioning":   {weight: 0.20, direction: "fear_when_high"},
	"perpetual_positioning": {weight: 0.20, direction: "greed_when_high"},
	"momentum_volume":       {weight: 0.15, direction: "greed_when_high"},
	"liquidation_balance":   {weight: 0.10, direction: "greed_when_high"},
	"market_breadth":        {weight: 0.10, direction: "greed_when_high"},
	"macro_risk":            {weight: 0.05, direction: "fear_when_high"},
}

func NewStore(root string) *Store {
	return &Store{root: filepath.Clean(root)}
}

func (s *Store) Latest() (Snapshot, error) {
	path := filepath.Join(s.root, "latest.json")
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return Snapshot{}, ErrSnapshotUnavailable
	}
	if err != nil {
		return Snapshot{}, fmt.Errorf("inspect daily intelligence snapshot: %w", err)
	}
	if !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > maximumFileSize {
		return Snapshot{}, ErrSnapshotInvalid
	}
	file, err := os.Open(path)
	if err != nil {
		return Snapshot{}, fmt.Errorf("open daily intelligence snapshot: %w", err)
	}
	defer file.Close()
	decoder := json.NewDecoder(io.LimitReader(file, maximumFileSize+1))
	decoder.DisallowUnknownFields()
	var snapshot Snapshot
	if err := decoder.Decode(&snapshot); err != nil {
		return Snapshot{}, ErrSnapshotInvalid
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return Snapshot{}, ErrSnapshotInvalid
	}
	if err := snapshot.Validate(); err != nil {
		return Snapshot{}, errors.Join(ErrSnapshotInvalid, err)
	}
	return snapshot, nil
}

func (s Snapshot) Validate() error {
	if s.SchemaVersion != SchemaVersion || s.MethodologyVersion != MethodologyVersion {
		return errors.New("unsupported intelligence version")
	}
	parsedDate, err := time.Parse("2006-01-02", s.Date)
	if err != nil {
		return errors.New("invalid intelligence date")
	}
	asOf, err := time.Parse(time.RFC3339, s.AsOf)
	if err != nil || asOf.UTC().Format("2006-01-02") != parsedDate.Format("2006-01-02") {
		return errors.New("invalid intelligence as_of")
	}
	if s.Status != "complete" && s.Status != "partial" && s.Status != "sample" {
		return errors.New("invalid intelligence status")
	}
	if !bounded(s.Score, 0, 100) || !bounded(s.MarketScore, 0, 100) ||
		!bounded(s.NewsScore, 0, 100) {
		return errors.New("intelligence scores must be in [0, 100]")
	}
	if math.Abs(s.Score-(0.75*s.MarketScore+0.25*s.NewsScore)) > 0.02 {
		return errors.New("composite intelligence score does not match methodology")
	}
	if s.PreviousScore == nil && s.Change != nil || s.PreviousScore != nil && s.Change == nil {
		return errors.New("previous_score and change must appear together")
	}
	if s.PreviousScore != nil &&
		(!bounded(*s.PreviousScore, 0, 100) || math.Abs(*s.Change-(s.Score-*s.PreviousScore)) > 0.02) {
		return errors.New("invalid intelligence score change")
	}
	if !validLabel(s.Score, s.Label) {
		return errors.New("intelligence label does not match score")
	}
	if err := validateFactors(s.Factors, s.MarketScore); err != nil {
		return err
	}
	if err := validateBrief(s.Brief); err != nil {
		return err
	}
	if s.Provenance.GeneratorVersion != GeneratorVersion ||
		s.Provenance.FactorCount != len(factorMethods) ||
		s.Provenance.NewsCount < 0 || s.Provenance.NewsCount > 100 ||
		!validSHA256(s.Provenance.InputSHA256) {
		return errors.New("invalid intelligence provenance")
	}
	return nil
}

func validateFactors(factors []Factor, marketScore float64) error {
	if len(factors) != len(factorMethods) {
		return errors.New("invalid intelligence factor count")
	}
	seen := make(map[string]struct{}, len(factors))
	contributions := 0.0
	for _, factor := range factors {
		method, ok := factorMethods[factor.Key]
		if !ok {
			return errors.New("unsupported intelligence factor")
		}
		if _, duplicate := seen[factor.Key]; duplicate {
			return errors.New("duplicate intelligence factor")
		}
		seen[factor.Key] = struct{}{}
		if factor.Direction != method.direction || math.Abs(factor.Weight-method.weight) > 0.0001 ||
			!bounded(factor.Percentile, 0, 1) || !bounded(factor.Score, 0, 100) ||
			!bounded(factor.Contribution, 0, 100) || factor.Unit == "" ||
			!validHTTPSURL(factor.Source) {
			return errors.New("invalid intelligence factor")
		}
		if _, err := time.Parse(time.RFC3339, factor.ObservedAt); err != nil {
			return errors.New("invalid factor observation time")
		}
		expectedScore := factor.Percentile * 100
		if method.direction == "fear_when_high" {
			expectedScore = (1 - factor.Percentile) * 100
		}
		if math.Abs(factor.Score-expectedScore) > 0.02 ||
			math.Abs(factor.Contribution-factor.Score*factor.Weight) > 0.02 {
			return errors.New("factor score does not match methodology")
		}
		contributions += factor.Contribution
	}
	if math.Abs(marketScore-contributions) > 0.02 {
		return errors.New("market score does not match factor contributions")
	}
	return nil
}

func validateBrief(brief Brief) error {
	if brief.Title == "" || brief.TitleZH == "" || brief.Summary == "" || brief.SummaryZH == "" ||
		len(brief.Highlights) > 3 || len(brief.HighlightsZH) > 3 || len(brief.News) > 10 {
		return errors.New("invalid daily brief")
	}
	for _, item := range brief.News {
		if item.ID == "" || item.Title == "" || item.Summary == "" || item.Source == "" ||
			!validHTTPSURL(item.URL) || len(item.Assets) == 0 || len(item.Assets) > 8 ||
			!bounded(item.Sentiment, -1, 1) || !bounded(item.Confidence, 0, 1) ||
			!bounded(item.Relevance, 0, 1) {
			return errors.New("invalid daily brief news item")
		}
		if _, err := time.Parse(time.RFC3339, item.PublishedAt); err != nil {
			return errors.New("invalid news publication time")
		}
	}
	return nil
}

func bounded(value, minimum, maximum float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0) && value >= minimum && value <= maximum
}

func validLabel(score float64, label string) bool {
	switch {
	case score <= 20:
		return label == "extreme_fear"
	case score <= 40:
		return label == "fear"
	case score <= 60:
		return label == "neutral"
	case score <= 80:
		return label == "greed"
	default:
		return label == "extreme_greed"
	}
}

func validHTTPSURL(value string) bool {
	parsed, err := url.Parse(value)
	return err == nil && parsed.Scheme == "https" && parsed.Hostname() != "" && parsed.User == nil
}

func validSHA256(value string) bool {
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded) == 32
}
