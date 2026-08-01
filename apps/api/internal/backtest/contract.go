package backtest

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strconv"
	"time"
)

const SchemaVersion = "1.0"

var (
	hex16Pattern           = regexp.MustCompile(`^[0-9a-f]{16}$`)
	hex64Pattern           = regexp.MustCompile(`^[0-9a-f]{64}$`)
	symbolPattern          = regexp.MustCompile(`^[A-Z0-9]{5,20}$`)
	idempotencyPattern     = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$`)
	decimalPattern         = regexp.MustCompile(`^(0|[1-9][0-9]*)(\.[0-9]+)?$`)
	semanticVersionPattern = regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`)
)

type DatasetRef struct {
	BundleVersion string  `json:"bundle_version,omitempty"`
	Version       string  `json:"version"`
	ContentSHA256 string  `json:"content_sha256"`
	Symbol        string  `json:"symbol"`
	Interval      string  `json:"interval"`
	DataStart     *string `json:"data_start,omitempty"`
	DataEnd       *string `json:"data_end,omitempty"`
}

type StrategyRef struct {
	Name       string         `json:"name"`
	Version    string         `json:"version"`
	Parameters map[string]any `json:"parameters"`
}

type Config struct {
	InitialCash       string `json:"initial_cash"`
	FeeBPS            string `json:"fee_bps"`
	SlippageBPS       string `json:"slippage_bps"`
	MaxTargetExposure string `json:"max_target_exposure"`
	LiquidateAtEnd    bool   `json:"liquidate_at_end"`
}

type Submission struct {
	SchemaVersion  string      `json:"schema_version"`
	IdempotencyKey string      `json:"idempotency_key"`
	Label          *string     `json:"label,omitempty"`
	Note           *string     `json:"note,omitempty"`
	Dataset        DatasetRef  `json:"dataset"`
	Strategy       StrategyRef `json:"strategy"`
	Config         Config      `json:"config"`
}

type TaskError struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable"`
}

type Task struct {
	SchemaVersion string     `json:"schema_version"`
	TaskID        string     `json:"task_id"`
	Status        string     `json:"status"`
	CreatedAt     time.Time  `json:"created_at"`
	StartedAt     *time.Time `json:"started_at"`
	FinishedAt    *time.Time `json:"finished_at"`
	Request       Submission `json:"request"`
	RunID         *string    `json:"run_id"`
	Reused        *bool      `json:"reused"`
	Error         *TaskError `json:"error"`
}

type RunResult struct {
	RunID   string         `json:"run_id"`
	Reused  bool           `json:"reused"`
	Metrics map[string]any `json:"metrics"`
}

func (s Submission) Validate() error {
	if s.SchemaVersion != SchemaVersion {
		return fmt.Errorf("schema_version must be %s", SchemaVersion)
	}
	if !idempotencyPattern.MatchString(s.IdempotencyKey) {
		return errors.New("idempotency_key has an invalid format")
	}
	if err := optionalText(s.Label, "label", 120); err != nil {
		return err
	}
	if err := optionalText(s.Note, "note", 500); err != nil {
		return err
	}
	if err := s.Dataset.validate(); err != nil {
		return err
	}
	if err := s.Strategy.validate(); err != nil {
		return err
	}
	if !strategySupportsInterval(s.Strategy.Name, s.Dataset.Interval) {
		return errors.New("strategy does not support dataset.interval")
	}
	if err := s.Config.validate(); err != nil {
		return err
	}
	return s.validateExposureBoundary()
}

func strategySupportsInterval(strategy, interval string) bool {
	switch strategy {
	case "buy-and-hold":
		return supportedInterval(interval)
	case "ema-cross":
		return interval != "5m" && supportedInterval(interval)
	case "donchian-atr":
		return interval == "1h" || interval == "4h" || interval == "1d"
	default:
		return false
	}
}

func knownStrategy(value string) bool {
	switch value {
	case "buy-and-hold", "ema-cross", "donchian-atr":
		return true
	default:
		return false
	}
}

func (s Submission) validateExposureBoundary() error {
	maximum, _ := strconv.ParseFloat(s.Config.MaxTargetExposure, 64)
	var strategyMaximum float64
	switch s.Strategy.Name {
	case "buy-and-hold":
		strategyMaximum, _ = strconv.ParseFloat(
			s.Strategy.Parameters["target_exposure"].(string),
			64,
		)
	case "donchian-atr":
		strategyMaximum, _ = strconv.ParseFloat(
			s.Strategy.Parameters["max_exposure"].(string),
			64,
		)
	default:
		strategyMaximum = 1
	}
	if strategyMaximum > maximum {
		return errors.New("strategy exposure cannot exceed config.max_target_exposure")
	}
	return nil
}

func (d DatasetRef) validate() error {
	if d.BundleVersion != "" && !hex16Pattern.MatchString(d.BundleVersion) {
		return errors.New("dataset.bundle_version must be 16 lowercase hex characters")
	}
	if !hex16Pattern.MatchString(d.Version) {
		return errors.New("dataset.version must be 16 lowercase hex characters")
	}
	if !hex64Pattern.MatchString(d.ContentSHA256) {
		return errors.New("dataset.content_sha256 must be 64 lowercase hex characters")
	}
	if !symbolPattern.MatchString(d.Symbol) {
		return errors.New("dataset.symbol must be uppercase alphanumeric")
	}
	if !supportedInterval(d.Interval) {
		return errors.New("dataset.interval must be 5m, 15m, 1h, 4h, or 1d")
	}
	if (d.DataStart == nil) != (d.DataEnd == nil) {
		return errors.New("dataset.data_start and data_end must be provided together")
	}
	if d.DataStart != nil {
		start, err := time.Parse(time.RFC3339, *d.DataStart)
		if err != nil {
			return errors.New("dataset.data_start must be RFC 3339")
		}
		end, err := time.Parse(time.RFC3339, *d.DataEnd)
		if err != nil {
			return errors.New("dataset.data_end must be RFC 3339")
		}
		if !start.Before(end) {
			return errors.New("dataset.data_start must be earlier than data_end")
		}
	}
	return nil
}

func supportedInterval(value string) bool {
	switch value {
	case "5m", "15m", "1h", "4h", "1d":
		return true
	default:
		return false
	}
}

func (s StrategyRef) validate() error {
	if s.Version != "1.0.0" {
		return errors.New("strategy.version must be 1.0.0")
	}
	switch s.Name {
	case "buy-and-hold":
		if err := exactKeys(s.Parameters, "target_exposure"); err != nil {
			return err
		}
		return decimalRange(s.Parameters["target_exposure"], "target_exposure", 0, 1, false)
	case "ema-cross":
		if err := exactKeys(s.Parameters, "fast_period", "slow_period"); err != nil {
			return err
		}
		fast, err := integerRange(s.Parameters["fast_period"], "fast_period", 1, 1000)
		if err != nil {
			return err
		}
		slow, err := integerRange(s.Parameters["slow_period"], "slow_period", 2, 2000)
		if err != nil {
			return err
		}
		if fast >= slow {
			return errors.New("fast_period must be less than slow_period")
		}
		return nil
	case "donchian-atr":
		if err := exactKeys(
			s.Parameters,
			"entry_period",
			"exit_period",
			"atr_period",
			"target_annual_volatility",
			"max_exposure",
			"rebalance_threshold",
		); err != nil {
			return err
		}
		entry, err := integerRange(s.Parameters["entry_period"], "entry_period", 2, 2000)
		if err != nil {
			return err
		}
		exit, err := integerRange(s.Parameters["exit_period"], "exit_period", 1, 2000)
		if err != nil {
			return err
		}
		if exit > entry {
			return errors.New("exit_period must not exceed entry_period")
		}
		if _, err := integerRange(s.Parameters["atr_period"], "atr_period", 2, 2000); err != nil {
			return err
		}
		if err := decimalRange(
			s.Parameters["target_annual_volatility"],
			"target_annual_volatility",
			0,
			2,
			false,
		); err != nil {
			return err
		}
		if err := decimalRange(s.Parameters["max_exposure"], "max_exposure", 0, 1, false); err != nil {
			return err
		}
		return decimalRange(
			s.Parameters["rebalance_threshold"],
			"rebalance_threshold",
			0,
			1,
			true,
		)
	default:
		return fmt.Errorf("unsupported strategy: %s", s.Name)
	}
}

func (c Config) validate() error {
	if err := decimalRange(c.InitialCash, "config.initial_cash", 0, 1e15, false); err != nil {
		return err
	}
	if err := decimalRange(c.FeeBPS, "config.fee_bps", 0, 1000, true); err != nil {
		return err
	}
	if err := decimalRange(c.SlippageBPS, "config.slippage_bps", 0, 1000, true); err != nil {
		return err
	}
	return decimalRange(
		c.MaxTargetExposure,
		"config.max_target_exposure",
		0,
		1,
		false,
	)
}

func sameSubmission(a, b Submission) bool {
	left, _ := json.Marshal(a)
	right, _ := json.Marshal(b)
	return bytes.Equal(left, right)
}

func exactKeys(parameters map[string]any, expected ...string) error {
	if len(parameters) != len(expected) {
		return errors.New("strategy parameters contain missing or unknown fields")
	}
	for _, key := range expected {
		if _, ok := parameters[key]; !ok {
			return fmt.Errorf("strategy parameter %s is required", key)
		}
	}
	return nil
}

func integerRange(value any, name string, minimum, maximum int64) (int64, error) {
	number, ok := value.(json.Number)
	if !ok {
		return 0, fmt.Errorf("%s must be an integer", name)
	}
	parsed, err := strconv.ParseInt(number.String(), 10, 64)
	if err != nil {
		return 0, fmt.Errorf("%s must be an integer", name)
	}
	if parsed < minimum || parsed > maximum {
		return 0, fmt.Errorf("%s must be in [%d, %d]", name, minimum, maximum)
	}
	return parsed, nil
}

func decimalRange(
	value any,
	name string,
	minimum, maximum float64,
	minimumInclusive bool,
) error {
	text, ok := value.(string)
	if !ok || !decimalPattern.MatchString(text) {
		return fmt.Errorf("%s must be a plain decimal string", name)
	}
	parsed, err := strconv.ParseFloat(text, 64)
	if err != nil {
		return fmt.Errorf("%s must be a plain decimal string", name)
	}
	minimumValid := parsed > minimum
	if minimumInclusive {
		minimumValid = parsed >= minimum
	}
	if !minimumValid || parsed > maximum {
		return fmt.Errorf("%s is outside the allowed range", name)
	}
	return nil
}

func optionalText(value *string, name string, maximum int) error {
	if value != nil && (len(*value) == 0 || len(*value) > maximum) {
		return fmt.Errorf("%s must contain 1 to %d characters", name, maximum)
	}
	return nil
}
