"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { completeCognitoSignIn } from "@/lib/cognito-auth";

function CallbackFailure() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-100">
      <section className="max-w-md rounded-xl border border-rose-400/30 bg-slate-900 p-6">
        <h1 className="text-xl font-bold text-rose-200">Sign-in was not completed</h1>
        <p className="mt-3 text-sm leading-6 text-slate-300">
          Cognito returned an authentication error. Return to SecureCloudOps and
          try again.
        </p>
      </section>
    </main>
  );
}

function CompleteSignIn({
  authorizationCode,
  returnedState,
}: {
  authorizationCode: string;
  returnedState: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const hasStarted = useRef(false);

  useEffect(() => {
    if (hasStarted.current) {
      return;
    }

    hasStarted.current = true;

    void completeCognitoSignIn(authorizationCode, returnedState)
      .then(() => {
        window.location.replace("/");
      })
      .catch(() => {
        setError("Secure sign-in could not be completed. Return home and try again.");
      });
  }, [authorizationCode, returnedState]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-100">
      <section className="max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h1 className="text-xl font-bold">Completing secure sign-in</h1>
        <p className="mt-3 text-sm leading-6 text-slate-300">
          Verifying the authorization response and preparing your short-lived API
          access session.
        </p>

        {error ? (
          <p className="mt-4 text-sm leading-6 text-rose-300" role="alert">
            {error}
          </p>
        ) : null}
      </section>
    </main>
  );
}

function CognitoCallback() {
  const searchParams = useSearchParams();
  const authorizationCode = searchParams.get("code");
  const returnedState = searchParams.get("state");
  const authorizationError = searchParams.get("error");

  if (authorizationError || !authorizationCode || !returnedState) {
    return <CallbackFailure />;
  }

  return (
    <CompleteSignIn
      authorizationCode={authorizationCode}
      returnedState={returnedState}
    />
  );
}

export default function CognitoCallbackPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-slate-100">
          Preparing secure sign-in…
        </main>
      }
    >
      <CognitoCallback />
    </Suspense>
  );
}