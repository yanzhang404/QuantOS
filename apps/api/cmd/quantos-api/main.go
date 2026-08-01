package main

import (
	"context"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/yanzhang404/QuantOS/apps/api/internal/backtest"
	"github.com/yanzhang404/QuantOS/apps/api/internal/intelligence"
)

func main() {
	var (
		listen       = flag.String("listen", "127.0.0.1:8080", "HTTP listen address")
		dataRoot     = flag.String("data-root", "data", "trusted immutable dataset root")
		artifactRoot = flag.String(
			"artifact-root",
			"artifacts/experiments",
			"experiment artifact root",
		)
		stateRoot        = flag.String("state-root", "var/quantos/tasks", "durable task state root")
		intelligenceRoot = flag.String(
			"intelligence-root",
			"var/quantos/intelligence",
			"trusted daily intelligence snapshot root",
		)
		allowedOrigin = flag.String(
			"allowed-origin",
			"http://localhost:3000",
			"single allowed browser origin",
		)
		uvBinary  = flag.String("uv-binary", "uv", "uv executable")
		queueSize = flag.Int("queue-size", 32, "maximum queued tasks")
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
	rootHandler := http.NewServeMux()
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
