"use client";

import { useEffect, useMemo, useState } from "react";
import {
  listCandidateDrafts,
  listCandidates,
  type CandidateDraft,
  type CandidateRecord,
  type CandidateStatus,
} from "./candidate-api";

type Locale = "en" | "zh";

const stages: CandidateStatus[] = ["proposed", "implemented", "review_ready", "approved"];

const copy = {
  en: {
    eyebrow: "Candidate queue",
    note: "Agent proposals require tests, robustness review, and owner approval.",
    empty: "No Agent proposal yet",
    disconnected: "Candidate records are available when the research API is connected.",
    latest: "Latest candidate",
    parameters: "parameters",
    weeklySlots: "weekly draft slots",
    status: {
      proposed: "Proposed",
      implemented: "Implemented",
      review_ready: "Review ready",
      approved: "Approved",
      rejected: "Rejected",
    },
  },
  zh: {
    eyebrow: "候选策略队列",
    note: "Agent 提案必须通过测试、稳健性评审和所有者批准。",
    empty: "暂无 Agent 提案",
    disconnected: "连接研究 API 后可读取候选策略记录。",
    latest: "最新候选策略",
    parameters: "个参数",
    weeklySlots: "本周草案名额",
    status: {
      proposed: "已提案",
      implemented: "已实现",
      review_ready: "待人工评审",
      approved: "已批准",
      rejected: "已拒绝",
    },
  },
} as const;

export function CandidateQueue({ locale }: { locale: Locale }) {
  const [records, setRecords] = useState<CandidateRecord[]>([]);
  const [drafts, setDrafts] = useState<CandidateDraft[]>([]);
  const [connected, setConnected] = useState<boolean>();
  const t = copy[locale];

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      listCandidates(controller.signal),
      listCandidateDrafts(controller.signal),
    ])
      .then(([candidates, candidateDrafts]) => {
        setRecords(candidates);
        setDrafts(candidateDrafts);
        setConnected(true);
      })
      .catch(() => {
        if (!controller.signal.aborted) setConnected(false);
      });
    return () => controller.abort();
  }, []);

  const latest = records[0];
  const latestDraft = drafts[0];
  const weeklyDraftCount = latestDraft
    ? drafts.filter((draft) => draft.iso_week === latestDraft.iso_week).length
    : 0;
  const counts = useMemo(
    () =>
      records.reduce<Partial<Record<CandidateStatus, number>>>((result, record) => {
        result[record.status] = (result[record.status] ?? 0) + 1;
        return result;
      }, {}),
    [records],
  );

  return (
    <article className="panel overview-status-card candidate-card">
      <p className="eyebrow">{t.eyebrow}</p>
      <div className="candidate-summary">
        <strong>{connected === undefined ? "-" : String(records.length).padStart(2, "0")}</strong>
        <div>
          <span>{latest ? t.latest : t.empty}</span>
          {latest ? <b>{latest.proposal.title}</b> : null}
        </div>
      </div>
      {latest ? (
        <div className="candidate-stages" aria-label={t.note}>
          {latestDraft ? (
            <span className="scheduled">
              {t.weeklySlots} {weeklyDraftCount}/{latestDraft.weekly_limit}
            </span>
          ) : null}
          {stages.map((stage) => (
            <span
              className={(counts[stage] ?? 0) > 0 ? "active" : ""}
              key={stage}
              title={`${counts[stage] ?? 0}`}
            >
              {t.status[stage]} {counts[stage] ?? 0}
            </span>
          ))}
          {(counts.rejected ?? 0) > 0 ? (
            <span className="rejected">{t.status.rejected} {counts.rejected}</span>
          ) : null}
        </div>
      ) : null}
      {latest ? (
        <p>
          {latest.proposal.supported_intervals.join(" · ")} · {latest.proposal.parameters.length}{" "}
          {t.parameters} · <code>{latest.proposal_id}</code>
        </p>
      ) : (
        <p>{connected === false ? t.disconnected : t.note}</p>
      )}
    </article>
  );
}
