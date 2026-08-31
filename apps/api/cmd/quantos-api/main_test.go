package main

import "testing"

func TestDefaultListenUsesHostPort(t *testing.T) {
	t.Setenv("QUANTOS_LISTEN", "")
	t.Setenv("PORT", "9000")
	if got := defaultListen(); got != "0.0.0.0:9000" {
		t.Fatalf("expected host port binding, got %q", got)
	}
}

func TestDefaultListenPrefersExplicitAddress(t *testing.T) {
	t.Setenv("QUANTOS_LISTEN", "127.0.0.1:9001")
	t.Setenv("PORT", "9000")
	if got := defaultListen(); got != "127.0.0.1:9001" {
		t.Fatalf("expected explicit binding, got %q", got)
	}
}

func TestEnvironmentDefaultsStayBounded(t *testing.T) {
	t.Setenv("QUANTOS_QUEUE_SIZE", "0")
	if got := envIntOrDefault("QUANTOS_QUEUE_SIZE", 32); got != 32 {
		t.Fatalf("expected invalid queue size to use fallback, got %d", got)
	}
	t.Setenv("QUANTOS_QUEUE_SIZE", "8")
	if got := envIntOrDefault("QUANTOS_QUEUE_SIZE", 32); got != 8 {
		t.Fatalf("expected configured queue size, got %d", got)
	}
}
