"use client";

import { useEffect, useState } from "react";
import { listRobustnessReviews, type RobustnessSummary } from "./robustness-api";

type Locale = "en" | "zh";

const copy = {
  en: {
    eyebrow: "Promotion evidence",
    title: "Robustness gates",
    pass: "Evidence gate passed",
    fail: "Evidence insufficient",
    empty: "No robustness review has been published yet.",
    emptyHint: "Run the deterministic robustness command to create the first review.",
    labels: {
      walk_forward: "Walk-forward",
      neighboring_parameters: "Neighboring parameters",
      doubled_costs: "Doubled costs",
      multiple_markets: "Multiple markets",
    },
    warning: "A pass supports human review; it never promotes or trades automatically.",
  },
  zh: {
    eyebrow: "晋级证据",
    title: "稳健性门槛",
    pass: "证据门槛通过",
    fail: "证据不足",
    empty: "还没有发布稳健性评审。",
    emptyHint: "运行确定性 robustness 命令后，这里会展示第一份评审。",
    labels: {
      walk_forward: "滚动前向验证",
      neighboring_parameters: "邻近参数",
      doubled_costs: "双倍成本",
      multiple_markets: "多市场",
    },
    warning: "通过只代表可以进入人工评审；不会自动晋级或交易。",
  },
} as const;

export function RobustnessEvidence({ locale }: { locale: Locale }) {
  const [review, setReview] = useState<RobustnessSummary>();
  const [connected, setConnected] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const t = copy[locale];

  useEffect(() => {
    const controller = new AbortController();
    void listRobustnessReviews(controller.signal)
      .then((reviews) => {
        setReview(reviews[0]);
        setConnected(true);
        setLoaded(true);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setConnected(false);
          setLoaded(true);
        }
      });
    return () => controller.abort();
  }, []);

  if (!loaded || !connected) return null;
  if (!review) {
    return (
      <section className="robustness-empty">
        <div>
          <p className="eyebrow">{t.eyebrow}</p>
          <strong>{t.empty}</strong>
        </div>
        <p>{t.emptyHint}</p>
      </section>
    );
  }

  return (
    <section className={`robustness-evidence ${review.passed ? "passed" : "failed"}`}>
      <header>
        <div>
          <p className="eyebrow">{t.eyebrow}</p>
          <h3>{t.title}</h3>
          <span>
            EMA({review.strategy.winner.fast_period}, {review.strategy.winner.slow_period}) ·{" "}
            {review.datasets.map((dataset) => dataset.symbol.replace("USDT", "")).join(" / ")} ·{" "}
            {review.datasets[0]?.interval}
          </span>
        </div>
        <div className="robustness-overall">
          <i />
          <strong>{review.passed ? t.pass : t.fail}</strong>
          <code>{review.review_id}</code>
        </div>
      </header>
      <div className="robustness-gates">
        {review.gates.map((gate) => (
          <article className={gate.passed ? "passed" : "failed"} key={gate.name}>
            <span>{gate.passed ? "PASS" : "FAIL"}</span>
            <strong>{t.labels[gate.name]}</strong>
            <p>{gate.reason}</p>
          </article>
        ))}
      </div>
      <p className="robustness-warning">{t.warning}</p>
    </section>
  );
}
