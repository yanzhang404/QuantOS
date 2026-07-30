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

type ExperimentVisualization struct {
	SchemaVersion  string                  `json:"schema_version"`
	RunID          string                  `json:"run_id"`
	CreatedAt      time.Time               `json:"created_at"`
	Dataset        DatasetRef              `json:"dataset"`
	Strategy       StrategyRef             `json:"strategy"`
	Config         Config                  `json:"config"`
	EngineVersion  string                  `json:"engine_version"`
	MetricsVersion string                  `json:"metrics_version"`
	Metrics        ExperimentMetrics       `json:"metrics"`
	Equity         []ExperimentEquityPoint `json:"equity"`
	Fills          []ExperimentFill        `json:"fills"`
}

type ExperimentStore struct {
	root string
}

func NewExperimentStore(root string) *ExperimentStore {
	return &ExperimentStore{root: filepath.Clean(root)}
}

func (s *ExperimentStore) Get(runID string) (ExperimentVisualization, error) {
	if !hex16Pattern.MatchString(runID) {
		return ExperimentVisualization{}, ErrExperimentNotFound
	}
	runPath := filepath.Join(s.root, runID, "run.json")
	var artifact struct {
		RunID          string            `json:"run_id"`
		Status         string            `json:"status"`
		CreatedAt      time.Time         `json:"created_at"`
		Dataset        DatasetRef        `json:"dataset"`
		Strategy       StrategyRef       `json:"strategy"`
		Config         Config            `json:"config"`
		EngineVersion  string            `json:"engine_version"`
		MetricsVersion string            `json:"metrics_version"`
		Metrics        ExperimentMetrics `json:"metrics"`
	}
	if err := decodeArtifactJSON(runPath, maxRunArtifactBytes, &artifact); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return ExperimentVisualization{}, ErrExperimentNotFound
		}
		return ExperimentVisualization{}, fmt.Errorf("%w: run metadata", ErrExperimentInvalid)
	}
	if artifact.RunID != runID ||
		artifact.Status != "completed" ||
		artifact.CreatedAt.IsZero() ||
		artifact.Dataset.validate() != nil ||
		artifact.Strategy.validate() != nil ||
		artifact.Config.validate() != nil ||
		!semanticVersionPattern.MatchString(artifact.EngineVersion) ||
		!semanticVersionPattern.MatchString(artifact.MetricsVersion) ||
		!validExperimentMetrics(artifact.Metrics) {
		return ExperimentVisualization{}, fmt.Errorf("%w: run metadata", ErrExperimentInvalid)
	}
	directory := filepath.Dir(runPath)
	equity, err := readExperimentEquity(filepath.Join(directory, "equity.csv"))
	if err != nil {
		return ExperimentVisualization{}, err
	}
	fills, err := readExperimentFills(filepath.Join(directory, "fills.csv"))
	if err != nil {
		return ExperimentVisualization{}, err
	}
	return ExperimentVisualization{
		SchemaVersion:  SchemaVersion,
		RunID:          artifact.RunID,
		CreatedAt:      artifact.CreatedAt,
		Dataset:        artifact.Dataset,
		Strategy:       artifact.Strategy,
		Config:         artifact.Config,
		EngineVersion:  artifact.EngineVersion,
		MetricsVersion: artifact.MetricsVersion,
		Metrics:        artifact.Metrics,
		Equity:         equity,
		Fills:          fills,
	}, nil
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
