package backtest

import (
	"encoding/json"
	"testing"
)

func TestSubmissionRejectsStrategyExposureAboveRiskLimit(t *testing.T) {
	request := validSubmission()
	request.Config.MaxTargetExposure = "0.5"

	if err := request.Validate(); err == nil {
		t.Fatal("expected exposure boundary validation error")
	}
}

func TestSubmissionRejectsInvalidPeriodOrdering(t *testing.T) {
	request := validSubmission()
	request.Strategy.Parameters["entry_period"] = json.Number("20")
	request.Strategy.Parameters["exit_period"] = json.Number("21")

	if err := request.Validate(); err == nil {
		t.Fatal("expected invalid period ordering")
	}
}

func TestDatasetAcceptsResearchTimeframesAndRejectsUnknownValues(t *testing.T) {
	for _, interval := range []string{"5m", "15m", "1h", "4h", "1d"} {
		request := validSubmission()
		request.Dataset.Interval = interval
		if err := request.Dataset.validate(); err != nil {
			t.Fatalf("interval %s: %v", interval, err)
		}
	}
	request := validSubmission()
	request.Dataset.Interval = "30m"
	if err := request.Dataset.validate(); err == nil {
		t.Fatal("expected unsupported interval error")
	}
}

func TestSubmissionRejectsStrategyOnUnsupportedInterval(t *testing.T) {
	request := validSubmission()
	request.Dataset.Interval = "15m"

	if err := request.Validate(); err == nil {
		t.Fatal("expected strategy interval validation error")
	}
}

func TestFundingStrategyRequiresOnlyAnImmutableFeatureVersion(t *testing.T) {
	request := validSubmission()
	request.Strategy = StrategyRef{
		Name: "funding-filtered-ema", Version: "0.1.0",
		Parameters: map[string]any{
			"fast_period": json.Number("20"), "slow_period": json.Number("50"),
			"max_funding_rate": "-0.0001",
		},
	}
	if err := request.Validate(); err == nil {
		t.Fatal("expected missing feature version")
	}
	version := "1111222233334444"
	request.FeatureDatasetVersion = &version
	if err := request.Validate(); err != nil {
		t.Fatal(err)
	}

	request = validSubmission()
	request.FeatureDatasetVersion = &version
	if err := request.Validate(); err == nil {
		t.Fatal("expected ordinary strategy to reject external feature version")
	}
}
