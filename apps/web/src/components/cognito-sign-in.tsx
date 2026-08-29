"use client";

import { useState } from "react";

import {
  beginCognitoSignIn,
  isCognitoLoginConfigured,
} from "@/lib/cognito-auth";

export function CognitoSignIn() {
  const [error, setError] = useState<string | null>(null);

  if (!isCognitoLoginConfigured()) {
    return null;
  }

  async function handleSignIn() {
    setError(null);

    try {
      await beginCognitoSignIn();
    } catch {
      setError("Secure sign-in could not be started. Please try again.");
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <button
        className="rounded-lg border border-cyan-400/60 px-4 py-2 text-sm font-semibold text-cyan-200 transition hover:bg-cyan-400/10"
        onClick={() => void handleSignIn()}
        type="button"
      >
        Sign in
      </button>

      {error ? (
        <p className="max-w-56 text-right text-xs text-rose-300" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}