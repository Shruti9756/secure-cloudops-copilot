"use client";

import { type FormEvent, useState } from "react";
import {
  getApiAuthorizationHeaders,
  getApiWorkspaceHeaders,
} from "@/lib/cognito-auth";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const DEFAULT_QUESTION =
  "Why did checkout latency increase after the deployment?";

type AnswerStatus =
  | "grounded"
  | "insufficient_evidence"
  | "structured_output_validation_failed"
  | "citation_validation_failed"
  | "safety_validation_failed";

type RetrievedSource = {
  source_identifier: string;
  document_title: string;
  cosine_distance: number;
};

type AskApiResponse = {
  status: AnswerStatus;
  answer: string;
  tenant: string;
  embedding_model: string;
  generation_model: string | null;
  sources: RetrievedSource[];
  structured_output_validation_passed: boolean | null;
  structured_output_validation_errors: string[];
  citation_validation_passed: boolean | null;
  citation_validation_errors: string[];
  safety_validation_passed: boolean | null;
  safety_validation_errors: string[];
  query_input_tokens: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
};

type CacheStatus = "HIT" | "MISS" | "BYPASS" | null;

type RateLimitStatus = {
  limit: number;
  remaining: number;
  resetAfterSeconds: number;
};

type AskResponse = AskApiResponse & {
  // This is read from the HTTP header, not from the API JSON body.
  cacheStatus: CacheStatus;
};

type ErrorResponse = {
  detail?: string;
};

function getStatusLabel(status: AnswerStatus): string {
  if (status === "grounded") {
    return "Grounded answer";
  }

  if (status === "insufficient_evidence") {
    return "Insufficient evidence";
  }
  if (status === "structured_output_validation_failed") {
    return "Model output withheld";
  }

  return "Answer withheld";
}

function getStatusClasses(status: AnswerStatus): string {
  if (status === "grounded") {
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-300";
  }

  if (status === "insufficient_evidence") {
    return "border-amber-400/30 bg-amber-400/10 text-amber-200";
  }

  return "border-rose-400/30 bg-rose-400/10 text-rose-200";
}

function getCacheStatus(headerValue: string | null): CacheStatus {
  if (
    headerValue === "HIT" ||
    headerValue === "MISS" ||
    headerValue === "BYPASS"
  ) {
    return headerValue;
  }

  return null;
}

function getCacheStatusClasses(cacheStatus: CacheStatus): string {
  if (cacheStatus === "HIT") {
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-300";
  }

  if (cacheStatus === "MISS") {
    return "border-amber-400/30 bg-amber-400/10 text-amber-200";
  }

  return "border-slate-600 bg-slate-800 text-slate-300";
}

function getHeaderInteger(headers: Headers, headerName: string): number | null {
  const rawValue = headers.get(headerName);

  if (rawValue === null) {
    return null;
  }

  const parsedValue = Number(rawValue);

  return Number.isInteger(parsedValue) && parsedValue >= 0
    ? parsedValue
    : null;
}

function getRateLimitStatus(headers: Headers): RateLimitStatus | null {
  const limit = getHeaderInteger(headers, "X-RateLimit-Limit");
  const remaining = getHeaderInteger(headers, "X-RateLimit-Remaining");
  const resetAfterSeconds = getHeaderInteger(headers, "X-RateLimit-Reset");

  if (limit === null || remaining === null || resetAfterSeconds === null) {
    return null;
  }

  return {
    limit,
    remaining,
    resetAfterSeconds,
  };
}

function getRetryAfterSeconds(headers: Headers): number | null {
  return getHeaderInteger(headers, "Retry-After");
}

function formatSeconds(seconds: number): string {
  return seconds === 1 ? "1 second" : `${seconds} seconds`;
}

function getErrorMessage(payload: unknown): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof (payload as ErrorResponse).detail === "string"
  ) {
    return (payload as ErrorResponse).detail as string;
  }

  return "The API returned an unexpected response. Please try again.";
}

export function AskCopilot() {
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [rateLimit, setRateLimit] = useState<RateLimitStatus | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!question.trim()) {
      setError("Enter an investigation question before submitting.");
      return;
    }

    setIsLoading(true);
    setError(null);
    setAnswer(null);
    setRateLimit(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getApiAuthorizationHeaders(),
          ...getApiWorkspaceHeaders(),
        },
        // The browser can submit only the question and a safe retrieval limit.
        // Tenant selection and all RAG security decisions remain on the API.
        body: JSON.stringify({
          question,
          limit: 2,
        }),
      });

      const payload: unknown = await response.json();

            // These headers are safe observability metadata exposed through CORS.
      setRateLimit(getRateLimitStatus(response.headers));

      if (!response.ok) {
        const apiMessage = getErrorMessage(payload);
        const retryAfterSeconds = getRetryAfterSeconds(response.headers);

        if (response.status === 429 && retryAfterSeconds !== null) {
          throw new Error(
            `${apiMessage} Try again in ${formatSeconds(retryAfterSeconds)}.`,
          );
        }

        throw new Error(apiMessage);
      }

      setAnswer({
        ...(payload as AskApiResponse),
        // The API explicitly exposes X-Cache through CORS for this UI indicator.
        cacheStatus: getCacheStatus(response.headers.get("X-Cache")),
      });
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to contact the API. Check that the local API is running.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="mt-8 rounded-xl border border-slate-700 bg-slate-950 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-cyan-300">
            Ask the incident copilot
          </p>
          <p className="mt-1 text-sm leading-6 text-slate-400">
            Answers use tenant-scoped evidence and pass citation and safety checks.
          </p>
        </div>

        <span className="rounded-md border border-slate-700 px-2.5 py-1 text-xs font-medium text-slate-400">
          Read-only
        </span>
      </div>

      <form className="mt-5 space-y-3" onSubmit={handleSubmit}>
        <label className="block text-sm font-medium text-slate-300" htmlFor="question">
          Investigation question
        </label>

        <textarea
          className="min-h-28 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-3 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20"
          disabled={isLoading}
          id="question"
          maxLength={2000}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about a deployment, runbook, or incident signal..."
          value={question}
        />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            Answers use tenant-scoped evidence and pass citation and safety checks.
          </p>

          <button
            className="rounded-lg bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            disabled={isLoading || !question.trim()}
            type="submit"
          >
            {isLoading ? "Investigating..." : "Ask copilot"}
          </button>
        </div>
      </form>

      {error ? (
        <div
          className="mt-5 rounded-lg border border-rose-400/30 bg-rose-400/10 p-4 text-sm leading-6 text-rose-200"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {rateLimit ? (
        <p className="mt-4 text-xs leading-6 text-slate-400">
          Request budget: {rateLimit.remaining} / {rateLimit.limit} remaining
          {" · "}resets in {formatSeconds(rateLimit.resetAfterSeconds)}
        </p>
      ) : null}

      {answer ? (
        <div className="mt-5 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full border px-3 py-1 text-xs font-semibold ${getStatusClasses(
                answer.status,
              )}`}
            >
              {getStatusLabel(answer.status)}
            </span>

            <span className="text-xs text-slate-500">
              Workspace: {answer.tenant}
            </span>
              {answer.cacheStatus ? (
            <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${getCacheStatusClasses(
                  answer.cacheStatus,
                )}`}
              >
                Redis cache: {answer.cacheStatus}
              </span>
            ) : null}
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <p className="whitespace-pre-wrap text-sm leading-7 text-slate-200">
              {answer.answer}
            </p>
          </div>
          {answer.structured_output_validation_passed !== null ? (
            <p className="text-xs text-slate-400">
              Structured output validation:{" "}
              <span
                className={
                  answer.structured_output_validation_passed
                    ? "text-emerald-300"
                    : "text-rose-300"
                }
              >
                {answer.structured_output_validation_passed
                  ? "passed"
                  : "failed"}
              </span>
            </p>
          ) : null}

          {answer.structured_output_validation_errors.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-rose-200">
              {answer.structured_output_validation_errors.map(
                (validationError) => (
                  <li key={validationError}>{validationError}</li>
                ),
              )}
            </ul>
          ) : null}
          {answer.citation_validation_passed !== null ? (
            <p className="text-xs text-slate-400">
              Citation validation:{" "}
              <span
                className={
                  answer.citation_validation_passed
                    ? "text-emerald-300"
                    : "text-rose-300"
                }
              >
                {answer.citation_validation_passed ? "passed" : "failed"}
              </span>
            </p>
          ) : null}

          {answer.citation_validation_errors.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-rose-200">
              {answer.citation_validation_errors.map((validationError) => (
                <li key={validationError}>{validationError}</li>
              ))}
            </ul>
          ) : null}

          {answer.safety_validation_passed !== null ? (
            <p className="text-xs text-slate-400">
              Safety validation:{" "}
              <span
                className={
                  answer.safety_validation_passed
                    ? "text-emerald-300"
                    : "text-rose-300"
                }
              >
                {answer.safety_validation_passed ? "passed" : "failed"}
              </span>
            </p>
          ) : null}

          {answer.safety_validation_errors.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-rose-200">
              {answer.safety_validation_errors.map((validationError) => (
                <li key={validationError}>{validationError}</li>
              ))}
            </ul>
          ) : null}

          {answer.sources.length > 0 ? (
            <div>
              <p className="text-sm font-medium text-slate-300">
                Retrieved sources
              </p>

              <ul className="mt-2 space-y-2">
                {answer.sources.map((source) => (
                  <li
                    className="rounded-md border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300"
                    key={source.source_identifier}
                  >
                    <p className="font-medium text-cyan-300">
                      {source.source_identifier}
                    </p>
                    <p className="mt-1 text-slate-400">
                      {source.document_title} · distance{" "}
                      {source.cosine_distance.toFixed(4)}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <p className="text-xs text-slate-500">
            Models: {answer.embedding_model}
            {answer.generation_model
              ? ` + ${answer.generation_model}`
              : " only"}
          </p>
        </div>
      ) : null}
    </section>
  );
}