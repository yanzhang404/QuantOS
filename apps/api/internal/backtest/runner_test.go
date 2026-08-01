package backtest

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"slices"
	"testing"
)

func TestCommandArgumentsPreserveStrategyAndRangeParameters(t *testing.T) {
	request := validSubmission()
	arguments, err := commandArguments(request, "/trusted/dataset", "/trusted/artifacts")
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{
		"/trusted/dataset",
		"/trusted/artifacts",
		"--start",
		"2025-01-01T00:00:00Z",
		"--entry-period",
		"55",
		"--strategy-max-exposure",
		"1",
	} {
		if !slices.Contains(arguments, expected) {
			t.Fatalf("arguments missing %q: %v", expected, arguments)
		}
	}
}

func TestCommandRunnerResolvesOnlyMatchingImmutableDataset(t *testing.T) {
	root := t.TempDir()
	request := validSubmission()
	dataset := filepath.Join(
		root,
		"market",
		"spot",
		"exchange=binance",
		"symbol=BTCUSDT",
		"interval=4h",
		"version=024f23d9a629502e",
	)
	if err := os.MkdirAll(dataset, 0o700); err != nil {
		t.Fatal(err)
	}
	manifest := map[string]string{
		"dataset_version": request.Dataset.Version,
		"content_sha256":  request.Dataset.ContentSHA256,
		"symbol":          request.Dataset.Symbol,
		"interval":        request.Dataset.Interval,
	}
	payload, _ := json.Marshal(manifest)
	if err := os.WriteFile(filepath.Join(dataset, "manifest.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	runner := CommandRunner{DataRoot: root}
	resolved, err := runner.resolveDataset(request.Dataset)
	if err != nil {
		t.Fatal(err)
	}
	if resolved != dataset {
		t.Fatalf("resolved dataset = %s", resolved)
	}

	mismatch := request.Dataset
	mismatch.ContentSHA256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	if _, err := runner.resolveDataset(mismatch); err == nil {
		t.Fatal("expected identity mismatch")
	}
}

func TestCommandRunnerVerifiesDatasetBundleMembership(t *testing.T) {
	root := t.TempDir()
	request := validSubmission()
	request.Dataset.BundleVersion = "47a8b29be444e2ba"
	bundle := filepath.Join(
		root,
		"bundles",
		"market",
		"spot",
		"exchange=binance",
		"version="+request.Dataset.BundleVersion,
	)
	if err := os.MkdirAll(bundle, 0o700); err != nil {
		t.Fatal(err)
	}
	manifest := map[string]any{
		"bundle_version": request.Dataset.BundleVersion,
		"members": []any{map[string]string{
			"dataset_version": request.Dataset.Version,
			"content_sha256":  request.Dataset.ContentSHA256,
			"symbol":          request.Dataset.Symbol,
			"interval":        request.Dataset.Interval,
		}},
	}
	payload, _ := json.Marshal(manifest)
	if err := os.WriteFile(filepath.Join(bundle, "manifest.json"), payload, 0o600); err != nil {
		t.Fatal(err)
	}
	runner := CommandRunner{DataRoot: root}
	if err := runner.verifyBundleMembership(request.Dataset); err != nil {
		t.Fatal(err)
	}

	mismatch := request.Dataset
	mismatch.Version = "aaaaaaaaaaaaaaaa"
	_, err := runner.resolveDataset(mismatch)
	var runError *RunError
	if !errors.As(err, &runError) || runError.Code != "dataset_bundle_mismatch" {
		t.Fatalf("expected dataset_bundle_mismatch, got %v", err)
	}
}
