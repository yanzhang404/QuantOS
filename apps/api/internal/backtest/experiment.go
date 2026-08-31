package backtest

import (
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	maxRunArtifactBytes    = 2 << 20
	maxSeriesArtifactBytes = 64 << 20
	maxSeriesRows          = 2_000_000
)

var (
	ErrExperimentNotFound = errors.New("experiment not found")
	ErrExperimentInvalid  = errors.New("experiment artifacts are invalid")
)

type ExperimentMetrics struct {
	InitialEquity float64  `json:"initial_equity"`
	FinalEquity   float64  `json:"final_equity"`
	TotalReturn   float64  `json:"total_return"`
	SharpeRatio   *float64 `json:"sharpe_ratio"`
	MaxDrawdown   float64  `json:"max_drawdown"`
	TradeCount    int      `json:"trade_count"`
	FillCount     int      `json:"fill_count"`
	FeesPaid      float64  `json:"fees_paid"`
}

type ExperimentEquityPoint struct {
	Time     string  `json:"time"`
	Equity   float64 `json:"equity"`
	Drawdown float64 `json:"drawdown"`
	Position float64 `json:"position"`
}

type ExperimentFill struct {
	Time     string  `json:"time"`
	Side     string  `json:"side"`
	Price    float64 `json:"price"`
	Quantity float64 `json:"quantity"`
	Fee      float64 `json:"fee"`
	Reason   string  `json:"reason"`
}

type ExperimentBar struct {
	Time   string  `json:"time"`
	Open   float64 `json:"open"`
	High   float64 `json:"high"`
	Low    float64 `json:"low"`
	Close  float64 `json:"close"`
	Volume float64 `json:"volume"`
}

type ExperimentVisualization struct {
	SchemaVersion   string                  `json:"schema_version"`
	RunID           string                  `json:"run_id"`
	CreatedAt       time.Time               `json:"created_at"`
	Dataset         DatasetRef              `json:"dataset"`
	Strategy        StrategyRef             `json:"strategy"`
	Features        []FeatureLineage        `json:"features"`
	FeatureDatasets []FeatureDatasetLineage `json:"feature_datasets"`
	Config          Config                  `json:"config"`
	EngineVersion   string                  `json:"engine_version"`
	MetricsVersion  string                  `json:"metrics_version"`
	Metrics         ExperimentMetrics       `json:"metrics"`
	Bars            []ExperimentBar         `json:"bars"`
	Equity          []ExperimentEquityPoint `json:"equity"`
	Fills           []ExperimentFill        `json:"fills"`
}

type FeatureDatasetLineage struct {
	DatasetVersion           string  `json:"dataset_version"`
	SchemaVersion            string  `json:"schema_version"`
	AlignmentPolicyVersion   string  `json:"alignment_policy_version"`
	Series                   string  `json:"series"`
	Exchange                 string  `json:"exchange"`
	Symbol                   string  `json:"symbol"`
	SpotInterval             string  `json:"spot_interval"`
	DerivativePeriod         *string `json:"derivative_period"`
	SpotDatasetVersion       string  `json:"spot_dataset_version"`
	SpotContentSHA256        string  `json:"spot_content_sha256"`
	DerivativeDatasetVersion string  `json:"derivative_dataset_version"`
	DerivativeContentSHA256  string  `json:"derivative_content_sha256"`
	RequestedStart           string  `json:"requested_start"`
	RequestedEnd             string  `json:"requested_end"`
	MaxAgeMS                 int64   `json:"max_age_ms"`
	RowCount                 int     `json:"row_count"`
	MatchedCount             int     `json:"matched_count"`
	StaleCount               int     `json:"stale_count"`
	NoPriorCount             int     `json:"no_prior_count"`
	ContentSHA256            string  `json:"content_sha256"`
	CreatedAt                string  `json:"created_at"`
	Producer                 string  `json:"producer"`
	FileSHA256               string  `json:"file_sha256"`
}

type FeatureLineage struct {
	FeatureID            string         `json:"feature_id"`
	Instance             string         `json:"instance"`
	Version              string         `json:"version"`
	DefinitionSHA256     string         `json:"definition_sha256"`
	Implementation       string         `json:"implementation"`
	Inputs               []string       `json:"inputs"`
	Parameters           map[string]int `json:"parameters"`
	StrategyParameter    string         `json:"strategy_parameter"`
	WarmupBars           int            `json:"warmup_bars"`
	UsesCurrentClosedBar bool           `json:"uses_current_closed_bar"`
}

type ExperimentSummary struct {
	SchemaVersion  string            `json:"schema_version"`
	RunID          string            `json:"run_id"`
	CreatedAt      time.Time         `json:"created_at"`
	ArchivedAt     *time.Time        `json:"archived_at"`
	Dataset        DatasetRef        `json:"dataset"`
	Strategy       StrategyRef       `json:"strategy"`
	Config         Config            `json:"config"`
	EngineVersion  string            `json:"engine_version"`
	MetricsVersion string            `json:"metrics_version"`
	Metrics        ExperimentMetrics `json:"metrics"`
}

type ExperimentFilters struct {
	Symbol       string
	Interval     string
	Strategy     string
	ArchivedMode string
	Limit        int
}

type experimentArtifact struct {
	ArtifactSchemaVersion string                  `json:"artifact_schema_version"`
	RunID                 string                  `json:"run_id"`
	Status                string                  `json:"status"`
	CreatedAt             time.Time               `json:"created_at"`
	Dataset               DatasetRef              `json:"dataset"`
	Strategy              StrategyRef             `json:"strategy"`
	Features              []FeatureLineage        `json:"features"`
	FeatureDatasets       []FeatureDatasetLineage `json:"feature_datasets"`
	Config                Config                  `json:"config"`
	EngineVersion         string                  `json:"engine_version"`
	MetricsVersion        string                  `json:"metrics_version"`
	Metrics               ExperimentMetrics       `json:"metrics"`
}

type ExperimentStore struct {
	root string
}

func NewExperimentStore(root string) *ExperimentStore {
	return &ExperimentStore{root: filepath.Clean(root)}
}

func (s *ExperimentStore) Get(runID string) (ExperimentVisualization, error) {
	artifact, err := s.readArtifact(runID)
	if err != nil {
		return ExperimentVisualization{}, err
	}
	features := artifact.Features
	if features == nil {
		features = []FeatureLineage{}
	}
	featureDatasets := artifact.FeatureDatasets
	if featureDatasets == nil {
		featureDatasets = []FeatureDatasetLineage{}
	}
	runPath := filepath.Join(s.root, runID, "run.json")
	directory := filepath.Dir(runPath)
	barsPath := filepath.Join(directory, "bars.csv")
	bars := []ExperimentBar{}
	if _, statErr := os.Stat(barsPath); statErr == nil {
		loadedBars, readErr := readExperimentBars(barsPath)
		if readErr != nil {
			return ExperimentVisualization{}, readErr
		}
		bars = loadedBars
	} else if !errors.Is(statErr, os.ErrNotExist) {
		return ExperimentVisualization{}, fmt.Errorf("%w: bars", ErrExperimentInvalid)
	}
	equity, err := readExperimentEquity(filepath.Join(directory, "equity.csv"))
	if err != nil {
		return ExperimentVisualization{}, err
	}
	fills, err := readExperimentFills(filepath.Join(directory, "fills.csv"))
	if err != nil {
		return ExperimentVisualization{}, err
	}
	return ExperimentVisualization{
		SchemaVersion:   SchemaVersion,
		RunID:           artifact.RunID,
		CreatedAt:       artifact.CreatedAt,
		Dataset:         artifact.Dataset,
		Strategy:        artifact.Strategy,
		Features:        features,
		FeatureDatasets: featureDatasets,
		Config:          artifact.Config,
		EngineVersion:   artifact.EngineVersion,
		MetricsVersion:  artifact.MetricsVersion,
		Metrics:         artifact.Metrics,
		Bars:            bars,
		Equity:          equity,
		Fills:           fills,
	}, nil
}

func (s *ExperimentStore) List(
	filters ExperimentFilters,
	archives map[string]time.Time,
) ([]ExperimentSummary, error) {
	entries, err := os.ReadDir(s.root)
	if errors.Is(err, os.ErrNotExist) {
		return []ExperimentSummary{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read experiment root: %w", err)
	}
	limit := filters.Limit
	if limit < 1 || limit > 200 {
		limit = 100
	}
	summaries := make([]ExperimentSummary, 0, min(limit, len(entries)))
	for _, entry := range entries {
		if !entry.IsDir() || !hex16Pattern.MatchString(entry.Name()) {
			continue
		}
		artifact, readErr := s.readArtifact(entry.Name())
		if readErr != nil {
			if errors.Is(readErr, ErrExperimentInvalid) ||
				errors.Is(readErr, ErrExperimentNotFound) {
				continue
			}
			return nil, readErr
		}
		archivedAt, archived := archives[artifact.RunID]
		if filters.Symbol != "" && artifact.Dataset.Symbol != filters.Symbol ||
			filters.Interval != "" && artifact.Dataset.Interval != filters.Interval ||
			filters.Strategy != "" && artifact.Strategy.Name != filters.Strategy ||
			filters.ArchivedMode == "exclude" && archived ||
			filters.ArchivedMode == "only" && !archived {
			continue
		}
		var archivedAtPointer *time.Time
		if archived {
			value := archivedAt
			archivedAtPointer = &value
		}
		summaries = append(summaries, ExperimentSummary{
			SchemaVersion: SchemaVersion, RunID: artifact.RunID,
			CreatedAt: artifact.CreatedAt, ArchivedAt: archivedAtPointer,
			Dataset: artifact.Dataset, Strategy: artifact.Strategy, Config: artifact.Config,
			EngineVersion: artifact.EngineVersion, MetricsVersion: artifact.MetricsVersion,
			Metrics: artifact.Metrics,
		})
	}
	sort.Slice(summaries, func(i, j int) bool {
		return summaries[i].CreatedAt.After(summaries[j].CreatedAt)
	})
	if len(summaries) > limit {
		summaries = summaries[:limit]
	}
	return summaries, nil
}

func (s *ExperimentStore) readArtifact(runID string) (experimentArtifact, error) {
	if !hex16Pattern.MatchString(runID) {
		return experimentArtifact{}, ErrExperimentNotFound
	}
	runPath := filepath.Join(s.root, runID, "run.json")
	var artifact experimentArtifact
	if err := decodeArtifactJSON(runPath, maxRunArtifactBytes, &artifact); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return experimentArtifact{}, ErrExperimentNotFound
		}
		return experimentArtifact{}, fmt.Errorf("%w: run metadata", ErrExperimentInvalid)
	}
	if artifact.RunID != runID ||
		(artifact.ArtifactSchemaVersion != "experiment-artifacts.v2" &&
			artifact.ArtifactSchemaVersion != "experiment-artifacts.v3" &&
			artifact.ArtifactSchemaVersion != "experiment-artifacts.v4") ||
		artifact.Status != "completed" ||
		artifact.CreatedAt.IsZero() ||
		artifact.Dataset.validate() != nil ||
		artifact.Strategy.validate() != nil ||
		validateFeatureLineage(artifact.Features) != nil ||
		validateFeatureDatasets(artifact) != nil ||
		artifact.Config.validate() != nil ||
		!semanticVersionPattern.MatchString(artifact.EngineVersion) ||
		!semanticVersionPattern.MatchString(artifact.MetricsVersion) ||
		!validExperimentMetrics(artifact.Metrics) {
		return experimentArtifact{}, fmt.Errorf("%w: run metadata", ErrExperimentInvalid)
	}
	return artifact, nil
}

func validateFeatureDatasets(artifact experimentArtifact) error {
	items := artifact.FeatureDatasets
	if artifact.ArtifactSchemaVersion != "experiment-artifacts.v4" && len(items) > 0 {
		return errors.New("external feature datasets require artifact schema v4")
	}
	if len(items) > 4 {
		return errors.New("too many feature datasets")
	}
	if artifact.Strategy.Name == "funding-filtered-ema" {
		if len(items) != 1 || items[0].Series != "funding-rate" {
			return errors.New("funding-filtered-ema requires one funding dataset")
		}
	} else if len(items) != 0 {
		return errors.New("strategy does not consume external feature datasets")
	}
	seen := make(map[string]struct{}, len(items))
	for _, item := range items {
		start, startErr := time.Parse(time.RFC3339, item.RequestedStart)
		end, endErr := time.Parse(time.RFC3339, item.RequestedEnd)
		_, createdErr := time.Parse(time.RFC3339, item.CreatedAt)
		if !hex16Pattern.MatchString(item.DatasetVersion) ||
			item.SchemaVersion != "aligned-derivatives.v1" ||
			item.AlignmentPolicyVersion != "asof-closed-bar.v1" ||
			(item.Series != "funding-rate" && item.Series != "open-interest") ||
			item.Exchange != "binance" || item.Symbol != artifact.Dataset.Symbol ||
			item.SpotInterval != artifact.Dataset.Interval ||
			item.SpotDatasetVersion != artifact.Dataset.Version ||
			item.SpotContentSHA256 != artifact.Dataset.ContentSHA256 ||
			!hex16Pattern.MatchString(item.DerivativeDatasetVersion) ||
			!hex64Pattern.MatchString(item.DerivativeContentSHA256) ||
			!hex64Pattern.MatchString(item.ContentSHA256) ||
			!hex64Pattern.MatchString(item.FileSHA256) ||
			startErr != nil || endErr != nil || createdErr != nil || !start.Before(end) ||
			item.MaxAgeMS < 1 || item.RowCount < 1 ||
			item.MatchedCount < 0 || item.StaleCount < 0 || item.NoPriorCount < 0 ||
			item.MatchedCount+item.StaleCount+item.NoPriorCount != item.RowCount ||
			item.Producer == "" {
			return errors.New("invalid feature dataset lineage")
		}
		if _, duplicate := seen[item.DatasetVersion]; duplicate {
			return errors.New("duplicate feature dataset lineage")
		}
		seen[item.DatasetVersion] = struct{}{}
	}
	return nil
}

func validateFeatureLineage(features []FeatureLineage) error {
	if len(features) > 8 {
		return errors.New("too many feature lineage records")
	}
	seen := make(map[string]struct{}, len(features))
	allowedInputs := map[string]bool{"open": true, "high": true, "low": true, "close": true, "volume": true}
	for _, feature := range features {
		if feature.FeatureID == "" || feature.Instance == "" || feature.Implementation == "" ||
			feature.StrategyParameter == "" || !semanticVersionPattern.MatchString(feature.Version) ||
			len(feature.DefinitionSHA256) != 64 || len(feature.Inputs) < 1 || len(feature.Inputs) > 8 ||
			feature.WarmupBars < 1 || feature.Parameters["period"] != feature.WarmupBars {
			return errors.New("invalid feature lineage")
		}
		if _, duplicate := seen[feature.Instance]; duplicate {
			return errors.New("duplicate feature lineage instance")
		}
		seen[feature.Instance] = struct{}{}
		for _, input := range feature.Inputs {
			if !allowedInputs[input] {
				return errors.New("invalid feature lineage input")
			}
		}
		for _, character := range feature.DefinitionSHA256 {
			if !strings.ContainsRune("0123456789abcdef", character) {
				return errors.New("invalid feature lineage hash")
			}
		}
	}
	return nil
}

func readExperimentBars(path string) ([]ExperimentBar, error) {
	records, err := openArtifactCSV(
		path,
		[]string{"open_time", "open", "high", "low", "close", "volume"},
	)
	if err != nil {
		return nil, err
	}
	if len(records) == 0 || len(records) > 2000 {
		return nil, fmt.Errorf("%w: bar count", ErrExperimentInvalid)
	}
	bars := make([]ExperimentBar, 0, len(records))
	for _, record := range records {
		timestamp, err := parseArtifactTime(record[0])
		if err != nil {
			return nil, fmt.Errorf("%w: bar timestamp", ErrExperimentInvalid)
		}
		values := make([]float64, 5)
		for index := range values {
			values[index], err = parseFiniteFloat(record[index+1])
			if err != nil {
				return nil, fmt.Errorf("%w: bar value", ErrExperimentInvalid)
			}
		}
		if values[0] <= 0 || values[1] <= 0 || values[2] <= 0 ||
			values[3] <= 0 || values[4] < 0 ||
			values[1] < max(values[0], values[2], values[3]) ||
			values[2] > min(values[0], values[1], values[3]) {
			return nil, fmt.Errorf("%w: bar OHLCV", ErrExperimentInvalid)
		}
		bars = append(bars, ExperimentBar{
			Time: timestamp, Open: values[0], High: values[1], Low: values[2],
			Close: values[3], Volume: values[4],
		})
	}
	return bars, nil
}

func decodeArtifactJSON(path string, maximum int64, target any) error {
	handle, err := os.Open(path)
	if err != nil {
		return err
	}
	defer handle.Close()
	info, err := handle.Stat()
	if err != nil || info.Size() > maximum {
		return fmt.Errorf("%w: artifact size", ErrExperimentInvalid)
	}
	decoder := json.NewDecoder(io.LimitReader(handle, maximum+1))
	decoder.UseNumber()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	return ensureEOF(decoder)
}

func readExperimentEquity(path string) ([]ExperimentEquityPoint, error) {
	records, err := openArtifactCSV(
		path,
		[]string{"timestamp", "cash", "position_quantity", "market_price", "equity"},
	)
	if err != nil {
		return nil, err
	}
	points := make([]ExperimentEquityPoint, 0, len(records))
	peak := 0.0
	for _, record := range records {
		timestamp, err := parseArtifactTime(record[0])
		if err != nil {
			return nil, fmt.Errorf("%w: equity timestamp", ErrExperimentInvalid)
		}
		position, err := parseFiniteFloat(record[2])
		if err != nil {
			return nil, fmt.Errorf("%w: equity position", ErrExperimentInvalid)
		}
		equity, err := parseFiniteFloat(record[4])
		if err != nil || equity <= 0 {
			return nil, fmt.Errorf("%w: equity value", ErrExperimentInvalid)
		}
		if equity > peak {
			peak = equity
		}
		points = append(points, ExperimentEquityPoint{
			Time:     timestamp,
			Equity:   equity,
			Drawdown: equity/peak - 1,
			Position: position,
		})
	}
	if len(points) == 0 {
		return nil, fmt.Errorf("%w: empty equity series", ErrExperimentInvalid)
	}
	return points, nil
}

func readExperimentFills(path string) ([]ExperimentFill, error) {
	records, err := openArtifactCSV(
		path,
		[]string{"timestamp", "symbol", "quantity", "price", "notional", "fee", "reason"},
	)
	if err != nil {
		return nil, err
	}
	fills := make([]ExperimentFill, 0, len(records))
	for _, record := range records {
		timestamp, err := parseArtifactTime(record[0])
		if err != nil {
			return nil, fmt.Errorf("%w: fill timestamp", ErrExperimentInvalid)
		}
		quantity, err := parseFiniteFloat(record[2])
		if err != nil || quantity == 0 {
			return nil, fmt.Errorf("%w: fill quantity", ErrExperimentInvalid)
		}
		price, err := parseFiniteFloat(record[3])
		if err != nil || price <= 0 {
			return nil, fmt.Errorf("%w: fill price", ErrExperimentInvalid)
		}
		fee, err := parseFiniteFloat(record[5])
		if err != nil || fee < 0 {
			return nil, fmt.Errorf("%w: fill fee", ErrExperimentInvalid)
		}
		reason := strings.TrimSpace(record[6])
		if reason == "" || len(reason) > 500 {
			return nil, fmt.Errorf("%w: fill reason", ErrExperimentInvalid)
		}
		side := "buy"
		if quantity < 0 {
			side = "sell"
		}
		fills = append(fills, ExperimentFill{
			Time:     timestamp,
			Side:     side,
			Price:    price,
			Quantity: math.Abs(quantity),
			Fee:      fee,
			Reason:   reason,
		})
	}
	return fills, nil
}

func openArtifactCSV(path string, expectedHeader []string) ([][]string, error) {
	handle, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("%w: missing series", ErrExperimentInvalid)
	}
	defer handle.Close()
	info, err := handle.Stat()
	if err != nil || info.Size() > maxSeriesArtifactBytes {
		return nil, fmt.Errorf("%w: series size", ErrExperimentInvalid)
	}
	reader := csv.NewReader(io.LimitReader(handle, maxSeriesArtifactBytes+1))
	reader.FieldsPerRecord = len(expectedHeader)
	header, err := reader.Read()
	if err != nil || !equalStrings(header, expectedHeader) {
		return nil, fmt.Errorf("%w: series header", ErrExperimentInvalid)
	}
	records := make([][]string, 0, 1024)
	for len(records) <= maxSeriesRows {
		record, err := reader.Read()
		if errors.Is(err, io.EOF) {
			return records, nil
		}
		if err != nil {
			return nil, fmt.Errorf("%w: series row", ErrExperimentInvalid)
		}
		records = append(records, record)
	}
	return nil, fmt.Errorf("%w: series row limit", ErrExperimentInvalid)
}

func equalStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func parseArtifactTime(value string) (string, error) {
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return "", err
	}
	return parsed.UTC().Format(time.RFC3339Nano), nil
}

func parseFiniteFloat(value string) (float64, error) {
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil || math.IsNaN(parsed) || math.IsInf(parsed, 0) {
		return 0, errors.New("value must be finite")
	}
	return parsed, nil
}

func validExperimentMetrics(metrics ExperimentMetrics) bool {
	values := []float64{
		metrics.InitialEquity,
		metrics.FinalEquity,
		metrics.TotalReturn,
		metrics.MaxDrawdown,
		metrics.FeesPaid,
	}
	if metrics.SharpeRatio != nil {
		values = append(values, *metrics.SharpeRatio)
	}
	for _, value := range values {
		if math.IsNaN(value) || math.IsInf(value, 0) {
			return false
		}
	}
	return metrics.InitialEquity > 0 &&
		metrics.FinalEquity > 0 &&
		metrics.MaxDrawdown >= 0 &&
		metrics.MaxDrawdown <= 1 &&
		metrics.TradeCount >= 0 &&
		metrics.FillCount >= 0 &&
		metrics.FeesPaid >= 0
}
