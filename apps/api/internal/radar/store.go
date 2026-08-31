// Package radar validates and reads immutable Market Radar snapshots.
package radar

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
	"regexp"
	"sort"
	"strings"
	"time"
)

const (
	SchemaVersion      = "1.0"
	MethodologyVersion = "quantos-market-radar-v1.0.0"
	GeneratorVersion   = "0.1.0"
	maximumFileSize    = 4 << 20
)

var (
	ErrSnapshotUnavailable = errors.New("market radar snapshot is unavailable")
	ErrSnapshotInvalid     = errors.New("market radar snapshot is invalid")
	ErrHealthUnavailable   = errors.New("market radar refresh health is unavailable")
	ErrHealthInvalid       = errors.New("market radar refresh health is invalid")
	symbolPattern          = regexp.MustCompile(`^[0-9]{6}\.(SH|SZ|BJ)$`)
)

type Store struct {
	root string
	now  func() time.Time
}

type Snapshot struct {
	SchemaVersion      string     `json:"schema_version"`
	MethodologyVersion string     `json:"methodology_version"`
	Market             string     `json:"market"`
	AsOf               string     `json:"as_of"`
	Status             string     `json:"status"`
	Stocks             []Stock    `json:"stocks"`
	Themes             []Theme    `json:"themes"`
	Summary            Summary    `json:"summary"`
	Provenance         Provenance `json:"provenance"`
}

type Stock struct {
	Symbol          string         `json:"symbol"`
	Name            string         `json:"name"`
	LastPrice       float64        `json:"last_price"`
	ChangePct       float64        `json:"change_pct"`
	RelativeVolume  *float64       `json:"relative_volume"`
	TurnoverPct     *float64       `json:"turnover_pct"`
	Change30mPct    *float64       `json:"change_30m_pct"`
	NewHigh20d      *bool          `json:"new_high_20d"`
	Themes          []string       `json:"themes"`
	Signals         []string       `json:"signals"`
	SourceURL       string         `json:"source_url"`
	ObservedAt      string         `json:"observed_at"`
	Catalyst        *Catalyst      `json:"catalyst"`
	Rank            int            `json:"rank"`
	HeatScore       float64        `json:"heat_score"`
	DataCoverage    float64        `json:"data_coverage"`
	HeatComponents  HeatComponents `json:"heat_components"`
	Acceleration30m *float64       `json:"acceleration_30m"`
	Acceleration60m *float64       `json:"acceleration_60m"`
}

type Catalyst struct {
	Title  string `json:"title"`
	Source string `json:"source"`
	URL    string `json:"url"`
}

type HeatComponents struct {
	PriceMove      float64  `json:"price_move"`
	RelativeVolume *float64 `json:"relative_volume"`
	Turnover       *float64 `json:"turnover"`
	Momentum30m    *float64 `json:"momentum_30m"`
	NewHigh20d     *float64 `json:"new_high_20d"`
}

type Theme struct {
	Rank            int      `json:"rank"`
	Name            string   `json:"name"`
	HeatScore       float64  `json:"heat_score"`
	LeaderScore     float64  `json:"leader_score"`
	BreadthScore    float64  `json:"breadth_score"`
	DataCoverage    float64  `json:"data_coverage"`
	ObservedBreadth int      `json:"observed_breadth"`
	Leaders         []string `json:"leaders"`
	Acceleration30m *float64 `json:"acceleration_30m"`
	Acceleration60m *float64 `json:"acceleration_60m"`
}

type Summary struct {
	HottestTheme       *string `json:"hottest_theme"`
	FastestRisingTheme *string `json:"fastest_rising_theme"`
	LeaderSymbol       *string `json:"leader_symbol"`
}

type Provenance struct {
	InputSHA256      string `json:"input_sha256"`
	GeneratorVersion string `json:"generator_version"`
	Provider         string `json:"provider"`
	StockCount       int    `json:"stock_count"`
	ThemeCount       int    `json:"theme_count"`
}

type RefreshHealth struct {
	SchemaVersion       string  `json:"schema_version"`
	State               string  `json:"state"`
	LastAttemptAt       string  `json:"last_attempt_at"`
	LastSuccessAt       *string `json:"last_success_at"`
	LastSuccessBucket   *string `json:"last_success_bucket"`
	ConsecutiveFailures int     `json:"consecutive_failures"`
	LastErrorCode       *string `json:"last_error_code"`
	Stale               bool    `json:"stale"`
}

type refreshHealthRecord struct {
	SchemaVersion       string  `json:"schema_version"`
	State               string  `json:"state"`
	LastAttemptAt       string  `json:"last_attempt_at"`
	LastSuccessAt       *string `json:"last_success_at"`
	LastSuccessBucket   *string `json:"last_success_bucket"`
	ConsecutiveFailures int     `json:"consecutive_failures"`
	LastErrorCode       *string `json:"last_error_code"`
}

func NewStore(root string) *Store {
	return &Store{root: filepath.Clean(root), now: time.Now}
}

func (s *Store) Latest() (Snapshot, error) {
	var snapshot Snapshot
	if err := readStrictJSON(filepath.Join(s.root, "latest.json"), maximumFileSize, &snapshot); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return Snapshot{}, ErrSnapshotUnavailable
		}
		if errors.Is(err, errInvalidFile) {
			return Snapshot{}, ErrSnapshotInvalid
		}
		return Snapshot{}, fmt.Errorf("read market radar snapshot: %w", err)
	}
	if err := snapshot.Validate(); err != nil {
		return Snapshot{}, errors.Join(ErrSnapshotInvalid, err)
	}
	return snapshot, nil
}

func (s *Store) Health() (RefreshHealth, error) {
	var record refreshHealthRecord
	if err := readStrictJSON(filepath.Join(s.root, "refresh-health.json"), 16<<10, &record); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return RefreshHealth{}, ErrHealthUnavailable
		}
		if errors.Is(err, errInvalidFile) {
			return RefreshHealth{}, ErrHealthInvalid
		}
		return RefreshHealth{}, fmt.Errorf("read market radar health: %w", err)
	}
	success, err := record.validate()
	if err != nil {
		return RefreshHealth{}, errors.Join(ErrHealthInvalid, err)
	}
	return RefreshHealth{
		SchemaVersion: record.SchemaVersion, State: record.State,
		LastAttemptAt: record.LastAttemptAt, LastSuccessAt: record.LastSuccessAt,
		LastSuccessBucket:   record.LastSuccessBucket,
		ConsecutiveFailures: record.ConsecutiveFailures, LastErrorCode: record.LastErrorCode,
		Stale: success.IsZero() || s.now().UTC().After(success.Add(30*time.Minute)),
	}, nil
}

var errInvalidFile = errors.New("invalid bounded JSON file")

func readStrictJSON(path string, limit int64, target any) error {
	info, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() || info.Size() <= 0 || info.Size() > limit {
		return errInvalidFile
	}
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()
	decoder := json.NewDecoder(io.LimitReader(file, limit+1))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return errInvalidFile
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return errInvalidFile
	}
	return nil
}

func (s Snapshot) Validate() error {
	if s.SchemaVersion != SchemaVersion || s.MethodologyVersion != MethodologyVersion || s.Market != "CN" {
		return errors.New("unsupported radar snapshot version")
	}
	asOf, err := time.Parse(time.RFC3339, s.AsOf)
	if err != nil {
		return errors.New("invalid radar as_of")
	}
	if s.Status != "complete" && s.Status != "partial" && s.Status != "sample" {
		return errors.New("invalid radar status")
	}
	if len(s.Stocks) > 100 || len(s.Themes) > 100 {
		return errors.New("radar result is too large")
	}
	stockBySymbol := make(map[string]Stock, len(s.Stocks))
	for index, stock := range s.Stocks {
		if s.Status == "complete" && !stock.hasFullCoverage() {
			return errors.New("complete radar snapshot has partial stock coverage")
		}
		if err := stock.validate(index+1, asOf); err != nil {
			return err
		}
		if _, exists := stockBySymbol[stock.Symbol]; exists {
			return errors.New("duplicate radar stock")
		}
		if index > 0 && stock.HeatScore > s.Stocks[index-1].HeatScore+0.001 {
			return errors.New("radar stocks are not heat-ranked")
		}
		stockBySymbol[stock.Symbol] = stock
	}
	if err := validateThemes(s.Themes, stockBySymbol); err != nil {
		return err
	}
	if err := validateSummary(s.Summary, s.Stocks, s.Themes); err != nil {
		return err
	}
	if s.Provenance.GeneratorVersion != GeneratorVersion ||
		s.Provenance.StockCount != len(s.Stocks) || s.Provenance.ThemeCount != len(s.Themes) ||
		!plain(s.Provenance.Provider, 80) || !validSHA256(s.Provenance.InputSHA256) {
		return errors.New("invalid radar provenance")
	}
	return nil
}

func (s Stock) validate(rank int, asOf time.Time) error {
	if s.Rank != rank || !symbolPattern.MatchString(s.Symbol) || !plain(s.Name, 80) ||
		!bounded(s.LastPrice, math.SmallestNonzeroFloat64, 1e9) || !bounded(s.ChangePct, math.SmallestNonzeroFloat64, 100) ||
		!stringList(s.Themes, 1, 8, 40) || !stringList(s.Signals, 1, 8, 120) || !httpsURL(s.SourceURL) {
		return errors.New("invalid radar stock")
	}
	observed, err := time.Parse(time.RFC3339, s.ObservedAt)
	if err != nil || observed.After(asOf.Add(10*time.Minute)) || observed.Before(asOf.Add(-48*time.Hour)) {
		return errors.New("invalid radar stock observation time")
	}
	if !optionalBounded(s.RelativeVolume, 0, 100) || !optionalBounded(s.TurnoverPct, 0, 100) ||
		!optionalBounded(s.Change30mPct, -100, 100) || !optionalBounded(s.Acceleration30m, -100, 100) ||
		!optionalBounded(s.Acceleration60m, -100, 100) {
		return errors.New("invalid radar stock metric")
	}
	if s.Catalyst != nil && (!plain(s.Catalyst.Title, 240) || !plain(s.Catalyst.Source, 80) || !httpsURL(s.Catalyst.URL)) {
		return errors.New("invalid radar stock catalyst")
	}
	return validateStockHeat(s)
}

func (s Stock) hasFullCoverage() bool {
	return s.RelativeVolume != nil && s.TurnoverPct != nil && s.Change30mPct != nil && s.NewHigh20d != nil
}

func validateStockHeat(stock Stock) error {
	components := []struct {
		weight   float64
		actual   *float64
		observed bool
		expect   float64
	}{
		{0.30, &stock.HeatComponents.PriceMove, true, clamp(stock.ChangePct / 10 * 100)},
		{0.25, stock.HeatComponents.RelativeVolume, stock.RelativeVolume != nil, relativeVolumeScore(stock.RelativeVolume)},
		{0.15, stock.HeatComponents.Turnover, stock.TurnoverPct != nil, turnoverScore(stock.TurnoverPct)},
		{0.20, stock.HeatComponents.Momentum30m, stock.Change30mPct != nil, momentumScore(stock.Change30mPct)},
		{0.10, stock.HeatComponents.NewHigh20d, stock.NewHigh20d != nil, newHighScore(stock.NewHigh20d)},
	}
	coverage, weighted := 0.0, 0.0
	for _, component := range components {
		if !component.observed {
			if component.actual != nil {
				return errors.New("radar heat component has no source observation")
			}
			continue
		}
		if component.actual == nil || !bounded(*component.actual, 0, 100) || math.Abs(*component.actual-component.expect) > 0.02 {
			return errors.New("radar heat component does not match methodology")
		}
		coverage += component.weight
		weighted += *component.actual * component.weight
	}
	if math.Abs(stock.DataCoverage-coverage) > 0.02 || math.Abs(stock.HeatScore-weighted/coverage) > 0.02 {
		return errors.New("radar stock heat does not match methodology")
	}
	return nil
}

func validateThemes(themes []Theme, stocks map[string]Stock) error {
	seen := make(map[string]struct{}, len(themes))
	for index, theme := range themes {
		if theme.Rank != index+1 || !plain(theme.Name, 40) || !bounded(theme.HeatScore, 0, 100) ||
			!bounded(theme.LeaderScore, 0, 100) || !bounded(theme.BreadthScore, 0, 100) ||
			!bounded(theme.DataCoverage, 0.3, 1) || !optionalBounded(theme.Acceleration30m, -100, 100) ||
			!optionalBounded(theme.Acceleration60m, -100, 100) {
			return errors.New("invalid radar theme")
		}
		if _, exists := seen[theme.Name]; exists {
			return errors.New("duplicate radar theme")
		}
		seen[theme.Name] = struct{}{}
		members := make([]Stock, 0)
		for _, stock := range stocks {
			if contains(stock.Themes, theme.Name) {
				members = append(members, stock)
			}
		}
		sort.Slice(members, func(i, j int) bool {
			if members[i].HeatScore == members[j].HeatScore {
				return members[i].Symbol < members[j].Symbol
			}
			return members[i].HeatScore > members[j].HeatScore
		})
		if len(members) == 0 || theme.ObservedBreadth != len(members) || len(theme.Leaders) != min(3, len(members)) {
			return errors.New("radar theme membership does not match stocks")
		}
		leaderScore := 0.0
		for leaderIndex, symbol := range theme.Leaders {
			if symbol != members[leaderIndex].Symbol {
				return errors.New("radar theme leaders do not match stocks")
			}
			leaderScore += members[leaderIndex].HeatScore
		}
		leaderScore /= float64(len(theme.Leaders))
		breadth := math.Min(100, float64(len(members))/5*100)
		coverage := 0.0
		for _, member := range members {
			coverage += member.DataCoverage
		}
		coverage /= float64(len(members))
		if math.Abs(theme.LeaderScore-leaderScore) > 0.02 || math.Abs(theme.BreadthScore-breadth) > 0.02 ||
			math.Abs(theme.DataCoverage-coverage) > 0.02 || math.Abs(theme.HeatScore-(leaderScore*0.70+breadth*0.30)) > 0.02 {
			return errors.New("radar theme heat does not match methodology")
		}
		if index > 0 && theme.HeatScore > themes[index-1].HeatScore+0.001 {
			return errors.New("radar themes are not heat-ranked")
		}
	}
	return nil
}

func validateSummary(summary Summary, stocks []Stock, themes []Theme) error {
	if len(stocks) == 0 {
		if summary.LeaderSymbol != nil {
			return errors.New("invalid empty radar summary")
		}
	} else if summary.LeaderSymbol == nil || *summary.LeaderSymbol != stocks[0].Symbol {
		return errors.New("invalid radar leader summary")
	}
	if len(themes) == 0 {
		if summary.HottestTheme != nil || summary.FastestRisingTheme != nil {
			return errors.New("invalid empty radar theme summary")
		}
		return nil
	}
	if summary.HottestTheme == nil || *summary.HottestTheme != themes[0].Name {
		return errors.New("invalid radar hottest theme summary")
	}
	var fastest *Theme
	for index := range themes {
		if themes[index].Acceleration30m == nil {
			continue
		}
		if fastest == nil || *themes[index].Acceleration30m > *fastest.Acceleration30m ||
			(*themes[index].Acceleration30m == *fastest.Acceleration30m &&
				(themes[index].HeatScore > fastest.HeatScore ||
					themes[index].HeatScore == fastest.HeatScore && themes[index].Name < fastest.Name)) {
			fastest = &themes[index]
		}
	}
	if fastest == nil {
		if summary.FastestRisingTheme != nil {
			return errors.New("invalid radar acceleration summary")
		}
	} else if summary.FastestRisingTheme == nil || *summary.FastestRisingTheme != fastest.Name {
		return errors.New("invalid radar acceleration summary")
	}
	return nil
}

func (r refreshHealthRecord) validate() (time.Time, error) {
	if r.SchemaVersion != SchemaVersion || (r.State != "running" && r.State != "succeeded" && r.State != "failed") {
		return time.Time{}, errors.New("unsupported radar refresh health state")
	}
	if _, err := time.Parse(time.RFC3339Nano, r.LastAttemptAt); err != nil || r.ConsecutiveFailures < 0 || r.ConsecutiveFailures > 1000 ||
		(r.LastSuccessAt == nil) != (r.LastSuccessBucket == nil) {
		return time.Time{}, errors.New("invalid radar refresh health")
	}
	var success time.Time
	if r.LastSuccessAt != nil {
		parsed, err := time.Parse(time.RFC3339Nano, *r.LastSuccessAt)
		if err != nil {
			return time.Time{}, errors.New("invalid radar success time")
		}
		if _, err := time.Parse("2006-01-02T15:04Z", *r.LastSuccessBucket); err != nil {
			return time.Time{}, errors.New("invalid radar success bucket")
		}
		success = parsed.UTC()
	}
	validError := r.LastErrorCode == nil || *r.LastErrorCode == "collection_failed" || *r.LastErrorCode == "publication_failed"
	if !validError || r.State == "succeeded" && (success.IsZero() || r.ConsecutiveFailures != 0 || r.LastErrorCode != nil) ||
		r.State == "failed" && (r.ConsecutiveFailures < 1 || r.LastErrorCode == nil) || r.State == "running" && r.LastErrorCode != nil {
		return time.Time{}, errors.New("inconsistent radar refresh health")
	}
	return success, nil
}

func relativeVolumeScore(value *float64) float64 {
	if value == nil {
		return 0
	}
	return clamp((*value - 1) / 3 * 100)
}

func turnoverScore(value *float64) float64 {
	if value == nil {
		return 0
	}
	return clamp(*value / 15 * 100)
}

func momentumScore(value *float64) float64 {
	if value == nil {
		return 0
	}
	return clamp(*value / 5 * 100)
}

func newHighScore(value *bool) float64 {
	if value != nil && *value {
		return 100
	}
	return 0
}

func clamp(value float64) float64 { return math.Max(0, math.Min(100, value)) }

func bounded(value, minimum, maximum float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0) && value >= minimum && value <= maximum
}

func optionalBounded(value *float64, minimum, maximum float64) bool {
	return value == nil || bounded(*value, minimum, maximum)
}

func plain(value string, maximum int) bool {
	trimmed := strings.TrimSpace(value)
	return trimmed != "" && trimmed == value && len(value) <= maximum && !strings.ContainsAny(value, "\r\n`<>")
}

func stringList(values []string, minimum, maximum, stringMaximum int) bool {
	if len(values) < minimum || len(values) > maximum {
		return false
	}
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		if !plain(value, stringMaximum) {
			return false
		}
		if _, exists := seen[value]; exists {
			return false
		}
		seen[value] = struct{}{}
	}
	return true
}

func httpsURL(value string) bool {
	parsed, err := url.Parse(value)
	return err == nil && parsed.Scheme == "https" && parsed.Hostname() != "" && parsed.User == nil &&
		parsed.Hostname() != "localhost" && parsed.Hostname() != "127.0.0.1" && parsed.Hostname() != "::1"
}

func validSHA256(value string) bool {
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded) == 32
}

func contains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}
