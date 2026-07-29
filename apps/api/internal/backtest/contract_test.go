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
