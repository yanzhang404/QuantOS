package main

import (
	"context"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"github.com/yanzhang404/QuantOS/apps/api/internal/backtest"
	"github.com/yanzhang404/QuantOS/apps/api/internal/intelligence"
	"github.com/yanzhang404/QuantOS/apps/api/internal/readiness"
)

func main() {
	var (
		listen       = flag.String("listen", defaultListen(), "HTTP listen address")
		dataRoot     = flag.String("data-root", envOrDefault("QUANTOS_DATA_ROOT", "data"), "trusted immutable dataset root")
		artifactRoot = flag.String(
			"artifact-root",
			envOrDefault("QUANTOS_ARTIFACT_ROOT", "artifacts/experiments"),
			"experiment artifact root",
		)
		stateRoot        = flag.String("state-root", envOrDefault("QUANTOS_STATE_ROOT", "var/quantos/tasks"), "durable task state root")
		intelligenceRoot = flag.String(
			"intelligence-root",
			envOrDefault("QUANTOS_INTELLIGENCE_ROOT", "var/quantos/intelligence"),
			"trusted daily intelligence snapshot root",
		)
		allowedOrigin = flag.String(
			"allowed-origin",
			envOrDefault("QUANTOS_ALLOWED_ORIGIN", "http://localhost:3000"),
			"single allowed browser origin",
		)
		uvBinary       = flag.String("uv-binary", envOrDefault("QUANTOS_UV_BINARY", "uv"), "uv executable")
		queueSize      = flag.Int("queue-size", envIntOrDefault("QUANTOS_QUEUE_SIZE", 32), "maximum queued tasks")
		requiredBundle = flag.String("required-bundle", os.Getenv("QUANTOS_REQUIRED_BUNDLE"), "bundle version required for readiness")
	)
	flag.Parse()

	workingDirectory, err := os.Getwd()
	if err != nil {
		log.Fatalf("resolve working directory: %v", err)
	}
	store, err := backtest.OpenTaskStore(filepath.Clean(*stateRoot), nil)
	if err != nil {
		log.Fatalf("open task store: %v", err)
	}
	runner := backtest.CommandRunner{
		UVBinary:     *uvBinary,
		WorkingDir:   workingDirectory,
		DataRoot:     filepath.Clean(*dataRoot),
		ArtifactRoot: filepath.Clean(*artifactRoot),
	}
	orchestrator := backtest.NewOrchestrator(store, runner, *queueSize, nil)
	defer orchestrator.Close()
	experiments := backtest.NewExperimentStore(filepath.Clean(*artifactRoot))
	for _, root := range []string{*artifactRoot, *intelligenceRoot} {
		if err := os.MkdirAll(filepath.Clean(root), 0o755); err != nil {
			log.Fatalf("create persistence root %s: %v", root, err)
		}
	}
	rootHandler := http.NewServeMux()
	ready := readiness.Checker{
		DataRoot:         filepath.Clean(*dataRoot),
		ArtifactRoot:     filepath.Clean(*artifactRoot),
		StateRoot:        filepath.Clean(*stateRoot),
		IntelligenceRoot: filepath.Clean(*intelligenceRoot),
		UVBinary:         *uvBinary,
		RequiredBundle:   *requiredBundle,
	}
	rootHandler.HandleFunc("/readyz", ready.Handler)
	rootHandler.Handle(
		"/api/v1/intelligence/",
		intelligence.NewHTTPHandler(
			intelligence.NewStore(filepath.Clean(*intelligenceRoot)),
			*allowedOrigin,
		),
	)
	rootHandler.Handle(
		"/",
		backtest.NewHTTPHandler(orchestrator, experiments, *allowedOrigin),
	)

	server := &http.Server{
		Addr:              *listen,
		Handler:           rootHandler,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    1 << 20,
	}
	shutdownContext, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()
	go func() {
		<-shutdownContext.Done()
		context, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := server.Shutdown(context); err != nil {
			log.Printf("shutdown API: %v", err)
		}
	}()

	log.Printf("QuantOS API listening on http://%s", *listen)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("serve API: %v", err)
	}
}

func defaultListen() string {
	if configured := os.Getenv("QUANTOS_LISTEN"); configured != "" {
		return configured
	}
	if port := os.Getenv("PORT"); port != "" {
		return "0.0.0.0:" + port
	}
	return "127.0.0.1:8080"
}

func envOrDefault(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func envIntOrDefault(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil || parsed < 1 {
		return fallback
	}
	return parsed
}
