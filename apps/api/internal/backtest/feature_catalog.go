package backtest

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"time"
)

var (
	ErrFeatureDatasetNotFound = errors.New("feature dataset not found")
	ErrFeatureDatasetInvalid  = errors.New("feature dataset is invalid")
)

type FeatureDatasetManifest struct {
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

type FeatureDatasetStore struct {
	root string
}

func NewFeatureDatasetStore(root string) *FeatureDatasetStore {
	return &FeatureDatasetStore{root: filepath.Clean(root)}
}

func (s *FeatureDatasetStore) List(series string, spot DatasetRef) ([]FeatureDatasetManifest, error) {
	parent, err := s.parent(series, spot)
	if err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(parent)
	if errors.Is(err, os.ErrNotExist) {
		return []FeatureDatasetManifest{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read feature catalog: %w", err)
	}
	result := make([]FeatureDatasetManifest, 0, min(len(entries), 100))
	for _, entry := range entries {
		if !entry.IsDir() || entry.Type()&os.ModeSymlink != 0 {
			continue
		}
		name := entry.Name()
		if len(name) != len("version=")+16 || name[:len("version=")] != "version=" {
			continue
		}
		manifest, readErr := s.resolve(series, spot, name[len("version="):])
		if readErr == nil {
			result = append(result, manifest)
		}
	}
	sort.Slice(result, func(i, j int) bool {
		return result[i].CreatedAt > result[j].CreatedAt
	})
	if len(result) > 100 {
		result = result[:100]
	}
	return result, nil
}

func (s *FeatureDatasetStore) Resolve(
	series string,
	spot DatasetRef,
	version string,
) (string, FeatureDatasetManifest, error) {
	manifest, err := s.resolve(series, spot, version)
	if err != nil {
		return "", FeatureDatasetManifest{}, err
	}
	parent, _ := s.parent(series, spot)
	return filepath.Join(parent, "version="+version), manifest, nil
}

func (s *FeatureDatasetStore) resolve(
	series string,
	spot DatasetRef,
	version string,
) (FeatureDatasetManifest, error) {
	if !hex16Pattern.MatchString(version) {
		return FeatureDatasetManifest{}, ErrFeatureDatasetNotFound
	}
	parent, err := s.parent(series, spot)
	if err != nil {
		return FeatureDatasetManifest{}, err
	}
	path := filepath.Join(parent, "version="+version)
	handle, err := os.Open(filepath.Join(path, "manifest.json"))
	if err != nil {
		return FeatureDatasetManifest{}, ErrFeatureDatasetNotFound
	}
	defer handle.Close()
	var manifest FeatureDatasetManifest
	decoder := json.NewDecoder(io.LimitReader(handle, 1<<20))
	if err := decoder.Decode(&manifest); err != nil || validateFeatureManifest(manifest, series, spot) != nil {
		return FeatureDatasetManifest{}, ErrFeatureDatasetInvalid
	}
	if info, err := os.Stat(filepath.Join(path, "part-00000.parquet")); err != nil ||
		!info.Mode().IsRegular() {
		return FeatureDatasetManifest{}, ErrFeatureDatasetInvalid
	}
	return manifest, nil
}

func (s *FeatureDatasetStore) parent(series string, spot DatasetRef) (string, error) {
	if series != "funding-rate" || !symbolPattern.MatchString(spot.Symbol) ||
		!supportedInterval(spot.Interval) || !hex16Pattern.MatchString(spot.Version) ||
		!hex64Pattern.MatchString(spot.ContentSHA256) {
		return "", ErrFeatureDatasetInvalid
	}
	return filepath.Join(
		s.root, "features", "derivatives-aligned", "series="+series,
		"symbol="+spot.Symbol, "spot_interval="+spot.Interval,
	), nil
}

func validateFeatureManifest(manifest FeatureDatasetManifest, series string, spot DatasetRef) error {
	start, startErr := time.Parse(time.RFC3339, manifest.RequestedStart)
	end, endErr := time.Parse(time.RFC3339, manifest.RequestedEnd)
	_, createdErr := time.Parse(time.RFC3339, manifest.CreatedAt)
	if !hex16Pattern.MatchString(manifest.DatasetVersion) ||
		manifest.SchemaVersion != "aligned-derivatives.v1" ||
		manifest.AlignmentPolicyVersion != "asof-closed-bar.v1" ||
		manifest.Series != series || manifest.Exchange != "binance" ||
		manifest.Symbol != spot.Symbol || manifest.SpotInterval != spot.Interval ||
		manifest.SpotDatasetVersion != spot.Version ||
		manifest.SpotContentSHA256 != spot.ContentSHA256 ||
		!hex16Pattern.MatchString(manifest.DerivativeDatasetVersion) ||
		!hex64Pattern.MatchString(manifest.DerivativeContentSHA256) ||
		!hex64Pattern.MatchString(manifest.ContentSHA256) ||
		manifest.ContentSHA256[:16] != manifest.DatasetVersion ||
		!hex64Pattern.MatchString(manifest.FileSHA256) ||
		startErr != nil || endErr != nil || createdErr != nil || !start.Before(end) ||
		manifest.MaxAgeMS < 1 || manifest.RowCount < 1 || manifest.MatchedCount < 0 ||
		manifest.StaleCount < 0 || manifest.NoPriorCount < 0 ||
		manifest.MatchedCount+manifest.StaleCount+manifest.NoPriorCount != manifest.RowCount ||
		manifest.Producer == "" {
		return ErrFeatureDatasetInvalid
	}
	return nil
}
