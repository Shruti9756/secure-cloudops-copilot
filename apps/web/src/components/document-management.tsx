"use client";

import { type ChangeEvent, type FormEvent, useState } from "react";
import { getApiAuthorizationHeaders } from "@/lib/cognito-auth";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const MAX_DOCUMENT_UPLOAD_BYTES = 1_000_000;

type DocumentIngestionStatus = "pending" | "chunked" | "embedded";

type DocumentStatusItem = {
  source_path: string;
  title: string;
  ingestion_status: DocumentIngestionStatus;
};

type DocumentStatusListResponse = {
  tenant: string;
  documents: DocumentStatusItem[];
};

type DocumentUploadResponse = {
  status: "accepted";
  action: "created" | "updated" | "unchanged";
  tenant: string;
  source_path: string;
};

type ErrorResponse = {
  detail?: string;
};

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

function getStatusClasses(status: DocumentIngestionStatus): string {
  if (status === "embedded") {
    return "border-emerald-400/30 bg-emerald-400/10 text-emerald-300";
  }

  if (status === "chunked") {
    return "border-cyan-400/30 bg-cyan-400/10 text-cyan-300";
  }

  return "border-amber-400/30 bg-amber-400/10 text-amber-200";
}

function isSupportedDocumentFile(file: File): boolean {
  const normalizedName = file.name.toLowerCase();

  return (
    normalizedName.endsWith(".md") ||
    normalizedName.endsWith(".txt") ||
    normalizedName.endsWith(".pdf") ||
    normalizedName.endsWith(".docx")
  );
}

export function DocumentManagement() {
  const [documents, setDocuments] = useState<DocumentStatusItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] =
    useState<DocumentUploadResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [hasLoadedDocuments, setHasLoadedDocuments] = useState(false);

  async function loadDocumentStatuses() {
    setIsLoadingDocuments(true);
    setStatusError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/documents`, {
        headers: getApiAuthorizationHeaders(),
      });
      const payload: unknown = await response.json();

      if (!response.ok) {
        throw new Error(getErrorMessage(payload));
      }

      // The API returns safe status data, never document bodies or vectors.
      setDocuments((payload as DocumentStatusListResponse).documents);
      setHasLoadedDocuments(true);
    } catch (caughtError) {
      setStatusError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to contact the API. Check that the local API is running.",
      );
    } finally {
      setIsLoadingDocuments(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;

    setSelectedFile(file);
    setUploadResult(null);
    setUploadError(null);

    if (file === null) {
      return;
    }

    // Browser checks improve feedback; the API remains the security authority.
    if (!isSupportedDocumentFile(file)) {
      setUploadError("Choose a Markdown (.md) or plain-text (.txt) file.");
      return;
    }

    if (file.size > MAX_DOCUMENT_UPLOAD_BYTES) {
      setUploadError("Choose a file smaller than 1 MB.");
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (selectedFile === null) {
      setUploadError("Choose a supported document before uploading.");
      return;
    }

    if (!isSupportedDocumentFile(selectedFile)) {
      setUploadError("Choose a supported document file (.md, .txt, .pdf, .docx).");
      return;
    }

    if (selectedFile.size > MAX_DOCUMENT_UPLOAD_BYTES) {
      setUploadError("Choose a file smaller than 1 MB.");
      return;
    }

    const form = event.currentTarget;
    const formData = new FormData();

    // This must match FastAPI's `uploaded_file: UploadFile` parameter name.
    formData.append("uploaded_file", selectedFile);

    setIsUploading(true);
    setUploadError(null);
    setUploadResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/documents`, {
        method: "POST",
        headers: getApiAuthorizationHeaders(),
        // Do not set Content-Type: the browser adds the multipart boundary safely.
        body: formData,
      });
      const payload: unknown = await response.json();

      if (!response.ok) {
        throw new Error(getErrorMessage(payload));
      }

      setUploadResult(payload as DocumentUploadResponse);
      setSelectedFile(null);
      form.reset();

      // Show the newly accepted document and its initial pending status.
      await loadDocumentStatuses();
    } catch (caughtError) {
      setUploadError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to contact the API. Check that the local API is running.",
      );
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <section
      className="rounded-2xl border border-slate-800 bg-slate-900 p-6"
      id="knowledge-documents"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold">Knowledge documents</h2>
          <p className="mt-1 text-sm leading-6 text-slate-400">
            Upload Markdown, text, digital PDF, or DOCX documents. The API extracts
text, validates it, and redacts secrets before storage.
          </p>
        </div>

        <button
          className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-300 disabled:cursor-not-allowed disabled:text-slate-500"
          disabled={isLoadingDocuments}
          onClick={() => void loadDocumentStatuses()}
          type="button"
        >
          {isLoadingDocuments ? "Refreshing..." : "Refresh statuses"}
        </button>
      </div>

      <form className="mt-5 space-y-3" onSubmit={handleUpload}>
        <label
          className="block text-sm font-medium text-slate-300"
          htmlFor="knowledge-file"
        >
          Knowledge document
        </label>

        <input
          accept=".md,.txt,.pdf,.docx,text/markdown,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="block w-full cursor-pointer rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-cyan-400 file:px-3 file:py-2 file:text-sm file:font-semibold file:text-slate-950 hover:file:bg-cyan-300"
          disabled={isUploading}
          id="knowledge-file"
          onChange={handleFileChange}
          type="file"
        />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            Accepted: .md, .txt, .pdf, and .docx · Maximum size: 1 MB
          </p>

          <button
            className="rounded-lg bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            disabled={isUploading || selectedFile === null}
            type="submit"
          >
            {isUploading ? "Uploading..." : "Upload document"}
          </button>
        </div>
      </form>

      {uploadError ? (
        <p
          className="mt-4 rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-200"
          role="alert"
        >
          {uploadError}
        </p>
      ) : null}

      {uploadResult ? (
        <p
          className="mt-4 rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-200"
          role="status"
        >
          Upload {uploadResult.action}: {uploadResult.source_path}. Processing
          status starts as pending.
        </p>
      ) : null}

      {statusError ? (
        <p
          className="mt-4 rounded-lg border border-rose-400/30 bg-rose-400/10 p-3 text-sm text-rose-200"
          role="alert"
        >
          Unable to load document statuses: {statusError}
        </p>
      ) : null}

      <div className="mt-5">
        <p className="text-sm font-medium text-slate-300">
          Processing status
        </p>

        {isLoadingDocuments ? (
          <p className="mt-3 text-sm text-slate-400">
            Loading document statuses...
          </p>
        ) : null}

        {!isLoadingDocuments && !hasLoadedDocuments && !statusError ? (
          <p className="mt-3 text-sm text-slate-400">
            Select Refresh statuses to load the tenant&apos;s knowledge
            documents.
          </p>
        ) : null}

        {!isLoadingDocuments &&
        hasLoadedDocuments &&
        documents.length === 0 ? (
          <p className="mt-3 text-sm text-slate-400">
            No knowledge documents are available yet.
          </p>
        ) : null}

        {!isLoadingDocuments && documents.length > 0 ? (
          <ul className="mt-3 space-y-2">
            {documents.map((document) => (
              <li
                className="rounded-lg border border-slate-800 bg-slate-950 p-3"
                key={document.source_path}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-200">
                      {document.title}
                    </p>
                    <p className="mt-1 break-all text-xs text-slate-500">
                      {document.source_path}
                    </p>
                  </div>

                  <span
                    className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${getStatusClasses(
                      document.ingestion_status,
                    )}`}
                  >
                    {document.ingestion_status}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}