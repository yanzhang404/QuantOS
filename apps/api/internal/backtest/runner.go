package backtest

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
)

type Runner interface {
	Run(context.Context, Submission) (RunResult, error)
}

type RunError struct {
	Code      string
	Message   string
	Retryable bool
}

func (e *RunError) Error() string {
	return e.Message
}

type CommandRunner struct {
	UVBinary     string
	WorkingDir   string
	DataRoot     string
	ArtifactRoot string
}

func (r CommandRunner) Run(ctx context.Context, request Submission) (RunResult, error) {
	dataset, err := r.resolveDataset(request.Dataset)
	if err != nil {
		return RunResult{}, err
	}
	featureDataset := ""
	if request.FeatureDatasetVersion != nil {
		featureDataset, err = r.resolveFeatureDataset(request)
		if err != nil {
			return RunResult{}, err
		}
	}
	arguments, err := commandArguments(request, dataset, featureDataset, r.ArtifactRoot)
	if err != nil {
		return RunResult{}, &RunError{
			Code:      "invalid_request",
			Message:   err.Error(),
			Retryable: false,
		}
	}
	command := exec.CommandContext(ctx, r.UVBinary, arguments...)
	command.Dir = r.WorkingDir
	output, err := command.Output()
	if err != nil {
		if errors.Is(ctx.Err(), context.Canceled) {
			return RunResult{}, &RunError{
				Code:      "task_cancelled",
				Message:   "The backtest was cancelled.",
				Retryable: true,
			}
		}
		return RunResult{}, &RunError{
			Code:      "worker_failed",
			Message:   "The historical backtest worker failed.",
			Retryable: false,
		}
	}
	var result RunResult
	if err := json.Unmarshal(output, &result); err != nil {
		return RunResult{}, &RunError{
			Code:      "invalid_worker_response",
			Message:   "The backtest worker returned an invalid response.",
			Retryable: false,
		}
	}
	if !hex16Pattern.MatchString(result.RunID) {
		return RunResult{}, &RunError{
			Code:      "invalid_worker_response",
			Message:   "The backtest worker returned an invalid Run ID.",
			Retryable: false,
		}
	}
	return result, nil
}

func (r CommandRunner) resolveFeatureDataset(request Submission) (string, error) {
	version := *request.FeatureDatasetVersion
	path := filepath.Join(
		r.DataRoot,
		"features",
		"derivatives-aligned",
		"series=funding-rate",
		"symbol="+request.Dataset.Symbol,
		"spot_interval="+request.Dataset.Interval,
		"version="+version,
	)
	handle, err := os.Open(filepath.Join(path, "manifest.json"))
	if err != nil {
		return "", &RunError{
			Code: "feature_dataset_not_found", Message: "The selected immutable feature dataset is unavailable.",
			Retryable: false,
		}
	}
	defer handle.Close()
	var manifest struct {
		DatasetVersion         string `json:"dataset_version"`
		SchemaVersion          string `json:"schema_version"`
		AlignmentPolicyVersion string `json:"alignment_policy_version"`
		Series                 string `json:"series"`
		Symbol                 string `json:"symbol"`
		SpotInterval           string `json:"spot_interval"`
		SpotDatasetVersion     string `json:"spot_dataset_version"`
		SpotContentSHA256      string `json:"spot_content_sha256"`
		ContentSHA256          string `json:"content_sha256"`
		FileSHA256             string `json:"file_sha256"`
		RowCount               int    `json:"row_count"`
		MatchedCount           int    `json:"matched_count"`
		StaleCount             int    `json:"stale_count"`
		NoPriorCount           int    `json:"no_prior_count"`
		MaxAgeMS               int64  `json:"max_age_ms"`
	}
	decoder := json.NewDecoder(io.LimitReader(handle, 1<<20))
	if err := decoder.Decode(&manifest); err != nil ||
		manifest.DatasetVersion != version ||
		manifest.SchemaVersion != "aligned-derivatives.v1" ||
		manifest.AlignmentPolicyVersion != "asof-closed-bar.v1" ||
		manifest.Series != "funding-rate" ||
		manifest.Symbol != request.Dataset.Symbol ||
		manifest.SpotInterval != request.Dataset.Interval ||
		manifest.SpotDatasetVersion != request.Dataset.Version ||
		manifest.SpotContentSHA256 != request.Dataset.ContentSHA256 ||
		!hex64Pattern.MatchString(manifest.ContentSHA256) ||
		manifest.ContentSHA256[:16] != manifest.DatasetVersion ||
		!hex64Pattern.MatchString(manifest.FileSHA256) ||
		manifest.RowCount < 1 ||
		manifest.MatchedCount < 0 || manifest.StaleCount < 0 || manifest.NoPriorCount < 0 ||
		manifest.MatchedCount+manifest.StaleCount+manifest.NoPriorCount != manifest.RowCount ||
		manifest.MaxAgeMS < 1 {
		return "", &RunError{
			Code: "feature_dataset_identity_mismatch", Message: "The selected feature dataset does not match the Spot input.",
			Retryable: false,
		}
	}
	if info, err := os.Stat(filepath.Join(path, "part-00000.parquet")); err != nil || !info.Mode().IsRegular() {
		return "", &RunError{
			Code: "feature_dataset_invalid", Message: "The selected feature dataset payload is unavailable.",
			Retryable: false,
		}
	}
	return path, nil
}

func (r CommandRunner) resolveDataset(reference DatasetRef) (string, error) {
	if reference.BundleVersion != "" {
		if err := r.verifyBundleMembership(reference); err != nil {
			return "", err
		}
	}
	path := filepath.Join(
		r.DataRoot,
		"market",
		"spot",
		"exchange=binance",
		"symbol="+reference.Symbol,
		"interval="+reference.Interval,
		"version="+reference.Version,
	)
	manifestPath := filepath.Join(path, "manifest.json")
	handle, err := os.Open(manifestPath)
	if err != nil {
		return "", &RunError{
			Code:      "dataset_not_found",
			Message:   "The selected immutable dataset is unavailable.",
			Retryable: false,
		}
	}
	defer handle.Close()
	var manifest struct {
		DatasetVersion string `json:"dataset_version"`
		ContentSHA256  string `json:"content_sha256"`
		Symbol         string `json:"symbol"`
		Interval       string `json:"interval"`
	}
	decoder := json.NewDecoder(io.LimitReader(handle, 1<<20))
	if err := decoder.Decode(&manifest); err != nil {
		return "", &RunError{
			Code:      "dataset_invalid",
			Message:   "The selected dataset manifest is invalid.",
			Retryable: false,
		}
	}
	if manifest.DatasetVersion != reference.Version ||
		manifest.ContentSHA256 != reference.ContentSHA256 ||
		manifest.Symbol != reference.Symbol ||
		manifest.Interval != reference.Interval {
		return "", &RunError{
			Code:      "dataset_identity_mismatch",
			Message:   "The selected dataset does not match its immutable identity.",
			Retryable: false,
		}
	}
	return path, nil
}

func (r CommandRunner) verifyBundleMembership(reference DatasetRef) error {
	manifestPath := filepath.Join(
		r.DataRoot,
		"bundles",
		"market",
		"spot",
		"exchange=binance",
		"version="+reference.BundleVersion,
		"manifest.json",
	)
	handle, err := os.Open(manifestPath)
	if err != nil {
		return &RunError{
			Code:      "bundle_not_found",
			Message:   "The selected immutable dataset bundle is unavailable.",
			Retryable: false,
		}
	}
	defer handle.Close()
	var manifest struct {
		BundleVersion string `json:"bundle_version"`
		Members       []struct {
			Symbol         string `json:"symbol"`
			Interval       string `json:"interval"`
			DatasetVersion string `json:"dataset_version"`
			ContentSHA256  string `json:"content_sha256"`
		} `json:"members"`
	}
	decoder := json.NewDecoder(io.LimitReader(handle, 1<<20))
	if err := decoder.Decode(&manifest); err != nil ||
		manifest.BundleVersion != reference.BundleVersion {
		return &RunError{
			Code:      "bundle_invalid",
			Message:   "The selected dataset bundle manifest is invalid.",
			Retryable: false,
		}
	}
	for _, member := range manifest.Members {
		if member.Symbol == reference.Symbol &&
			member.Interval == reference.Interval &&
			member.DatasetVersion == reference.Version &&
			member.ContentSHA256 == reference.ContentSHA256 {
			return nil
		}
	}
	return &RunError{
		Code:      "dataset_bundle_mismatch",
		Message:   "The selected dataset is not a member of the immutable bundle.",
		Retryable: false,
	}
}

func commandArguments(request Submission, dataset, featureDataset, artifactRoot string) ([]string, error) {
	arguments := []string{
		"run",
		"quantos",
		"backtest",
		"run",
		"--dataset",
		dataset,
		"--strategy",
		request.Strategy.Name,
		"--initial-cash",
		request.Config.InitialCash,
		"--fee-bps",
		request.Config.FeeBPS,
		"--slippage-bps",
		request.Config.SlippageBPS,
		"--max-target-exposure",
		request.Config.MaxTargetExposure,
		"--output-root",
		artifactRoot,
	}
	if request.Dataset.DataStart != nil {
		arguments = append(
			arguments,
			"--start",
			*request.Dataset.DataStart,
			"--end",
			*request.Dataset.DataEnd,
		)
	}
	switch request.Strategy.Name {
	case "buy-and-hold":
		arguments = append(
			arguments,
			"--target-exposure",
			request.Strategy.Parameters["target_exposure"].(string),
		)
	case "ema-cross":
		fast, _ := integerRange(request.Strategy.Parameters["fast_period"], "fast_period", 1, 1000)
		slow, _ := integerRange(request.Strategy.Parameters["slow_period"], "slow_period", 2, 2000)
		arguments = append(
			arguments,
			"--fast",
			fmt.Sprint(fast),
			"--slow",
			fmt.Sprint(slow),
		)
	case "funding-filtered-ema":
		fast, _ := integerRange(request.Strategy.Parameters["fast_period"], "fast_period", 1, 1000)
		slow, _ := integerRange(request.Strategy.Parameters["slow_period"], "slow_period", 2, 2000)
		if featureDataset == "" {
			return nil, errors.New("funding-filtered-ema requires a feature dataset")
		}
		arguments = append(
			arguments,
			"--fast", fmt.Sprint(fast),
			"--slow", fmt.Sprint(slow),
			"--max-funding-rate", request.Strategy.Parameters["max_funding_rate"].(string),
			"--feature-dataset", featureDataset,
		)
	case "donchian-atr":
		entry, _ := integerRange(
			request.Strategy.Parameters["entry_period"],
			"entry_period",
			2,
			2000,
		)
		exit, _ := integerRange(
			request.Strategy.Parameters["exit_period"],
			"exit_period",
			1,
			2000,
		)
		atr, _ := integerRange(
			request.Strategy.Parameters["atr_period"],
			"atr_period",
			2,
			2000,
		)
		arguments = append(
			arguments,
			"--entry-period",
			fmt.Sprint(entry),
			"--exit-period",
			fmt.Sprint(exit),
			"--atr-period",
			fmt.Sprint(atr),
			"--target-annual-volatility",
			request.Strategy.Parameters["target_annual_volatility"].(string),
			"--rebalance-threshold",
			request.Strategy.Parameters["rebalance_threshold"].(string),
			"--strategy-max-exposure",
			request.Strategy.Parameters["max_exposure"].(string),
		)
	default:
		return nil, fmt.Errorf("unsupported strategy: %s", request.Strategy.Name)
	}
	if !request.Config.LiquidateAtEnd {
		arguments = append(arguments, "--no-liquidate")
	}
	return arguments, nil
}

func truncate(value string, maximum int) string {
	if len(value) <= maximum {
		return value
	}
	return value[:maximum]
}
