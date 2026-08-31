"use client";

import { type ChangeEvent, useState } from "react";

import {
  getActiveWorkspaceSlug,
  getApiAuthorizationHeaders,
  setActiveWorkspaceSlug,
} from "@/lib/cognito-auth";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type WorkspaceRole = "admin" | "manager" | "engineer";

type Workspace = {
  slug: string;
  name: string;
  role: WorkspaceRole;
};

type WorkspaceListResponse = {
  workspaces: Workspace[];
};

export function WorkspaceSelector() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspaceSlug, setSelectedWorkspaceSlug] =
    useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadWorkspaces() {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workspaces`, {
        headers: getApiAuthorizationHeaders(),
      });
      const payload: unknown = await response.json();

      if (!response.ok) {
        throw new Error(
          "Unable to load your workspaces. Sign in and try again.",
        );
      }

      const availableWorkspaces = (
        payload as WorkspaceListResponse
      ).workspaces;
      const storedWorkspaceSlug = getActiveWorkspaceSlug();
      const selectedWorkspace =
        availableWorkspaces.find(
          (workspace) => workspace.slug === storedWorkspaceSlug,
        ) ?? availableWorkspaces[0];

      setWorkspaces(availableWorkspaces);

      if (selectedWorkspace) {
        setSelectedWorkspaceSlug(selectedWorkspace.slug);
        setActiveWorkspaceSlug(selectedWorkspace.slug);
      }
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Unable to load your workspaces. Sign in and try again.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  function handleWorkspaceChange(event: ChangeEvent<HTMLSelectElement>) {
    const workspaceSlug = event.target.value;

    setSelectedWorkspaceSlug(workspaceSlug);
    setActiveWorkspaceSlug(workspaceSlug);

    // Existing answers and document lists might belong to the prior workspace.
    // Reload so every visible result is fetched under the newly selected scope.
    window.location.reload();
  }

  const selectedWorkspace =
    workspaces.find(
      (workspace) => workspace.slug === selectedWorkspaceSlug,
    ) ?? null;

  return (
    <div className="flex flex-col items-end gap-2">
      {workspaces.length === 0 ? (
        <button
          className="rounded-lg border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-300 transition hover:border-cyan-400 hover:text-cyan-300 disabled:cursor-not-allowed disabled:text-slate-500"
          disabled={isLoading}
          onClick={() => void loadWorkspaces()}
          type="button"
        >
          {isLoading ? "Loading workspaces..." : "Choose workspace"}
        </button>
      ) : (
        <>
          <label
            className="text-xs font-medium text-slate-400"
            htmlFor="workspace-selector"
          >
            Active workspace
          </label>

          <select
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-semibold text-slate-200"
            id="workspace-selector"
            onChange={handleWorkspaceChange}
            value={selectedWorkspaceSlug}
          >
            {workspaces.map((workspace) => (
              <option key={workspace.slug} value={workspace.slug}>
                {workspace.name}
              </option>
            ))}
          </select>

          {selectedWorkspace ? (
            <p className="text-xs text-slate-500">
              Role: {selectedWorkspace.role}
            </p>
          ) : null}
        </>
      )}

      {error ? (
        <p className="max-w-56 text-right text-xs text-rose-300" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}