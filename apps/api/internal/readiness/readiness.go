// Package readiness implements deployment readiness for the stateful research API.
package readiness

import (
	"encoding/json"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
)

var bundleVersionPattern = regexp.MustCompile(`^[a-f0-9]{16}$`)

// Checker verifies only trusted server configuration. It never downloads data.
type Checker struct {
	DataRoot         string
	ArtifactRoot     string
	StateRoot        string
	IntelligenceRoot string
	RobustnessRoot   string
	CandidateRoot    string
	UVBinary         string
	RequiredBundle   string
}

// Handler returns a Kubernetes- and container-host-compatible readiness route.
func (checker Checker) Handler(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("Content-Type", "application/json")
	if request.Method != http.MethodGet {
		response.WriteHeader(http.StatusMethodNotAllowed)
		_ = json.NewEncoder(response).Encode(map[string]string{"status": "method_not_allowed"})
		return
	}

	checks := checker.Check()
	status := http.StatusOK
	state := "ready"
	for _, passed := range checks {
		if !passed {
			status = http.StatusServiceUnavailable
			state = "not_ready"
			break
		}
	}
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(map[string]any{
		"status": state,
		"checks": checks,
	})
}

// Check reports non-sensitive deployment prerequisites.
func (checker Checker) Check() map[string]bool {
	checks := map[string]bool{
		"artifact_root":     directoryExists(checker.ArtifactRoot),
		"candidate_root":    directoryExists(checker.CandidateRoot),
		"data_root":         directoryExists(checker.DataRoot),
		"intelligence_root": directoryExists(checker.IntelligenceRoot),
		"robustness_root":   directoryExists(checker.RobustnessRoot),
		"state_root":        directoryExists(checker.StateRoot),
		"uv_binary":         executableExists(checker.UVBinary),
	}
	if checker.RequiredBundle != "" {
		checks["required_bundle"] = bundleExists(checker.DataRoot, checker.RequiredBundle)
	}
	return checks
}

func directoryExists(path string) bool {
	info, err := os.Stat(filepath.Clean(path))
	return err == nil && info.IsDir()
}

func executableExists(binary string) bool {
	_, err := exec.LookPath(binary)
	return err == nil
}

func bundleExists(dataRoot, version string) bool {
	if !bundleVersionPattern.MatchString(version) {
		return false
	}
	manifest := filepath.Join(
		filepath.Clean(dataRoot),
		"bundles",
		"market",
		"spot",
		"exchange=binance",
		"version="+version,
		"manifest.json",
	)
	info, err := os.Stat(manifest)
	return err == nil && info.Mode().IsRegular()
}
