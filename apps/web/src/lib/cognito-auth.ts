const COGNITO_STATE_STORAGE_KEY = "securecloudops.cognito.oauth-state";
const COGNITO_VERIFIER_STORAGE_KEY = "securecloudops.cognito.pkce-verifier";
const COGNITO_SESSION_STORAGE_KEY = "securecloudops.cognito.access-session";
const ACTIVE_WORKSPACE_STORAGE_KEY =
  "securecloudops.active-workspace-slug";
const ACTIVE_WORKSPACE_ROLE_STORAGE_KEY =
  "securecloudops.active-workspace-role";

export type WorkspaceRole = "admin" | "manager" | "engineer";

type CognitoConfiguration = {
  managedLoginBaseUrl: string;
  clientId: string;
  redirectUri: string;
};

type TokenEndpointResponse = {
  access_token?: unknown;
  expires_in?: unknown;
};

type StoredAccessSession = {
  accessToken: string;
  expiresAtMilliseconds: number;
};

function getCognitoConfiguration(): CognitoConfiguration {
  const managedLoginBaseUrl =
    process.env.NEXT_PUBLIC_COGNITO_MANAGED_LOGIN_BASE_URL?.replace(/\/$/, "");
  const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID;
  const redirectUri = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI;

  if (!managedLoginBaseUrl || !clientId || !redirectUri) {
    throw new Error("Cognito browser login is not configured.");
  }

  return {
    managedLoginBaseUrl,
    clientId,
    redirectUri,
  };
}

function toBase64Url(bytes: Uint8Array): string {
  let binaryValue = "";

  for (const byte of bytes) {
    binaryValue += String.fromCharCode(byte);
  }

  return btoa(binaryValue)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

function createRandomBase64Url(byteLength: number): string {
  const randomBytes = new Uint8Array(byteLength);
  crypto.getRandomValues(randomBytes);

  return toBase64Url(randomBytes);
}

async function createPkceChallenge(verifier: string): Promise<string> {
  const encodedVerifier = new TextEncoder().encode(verifier);
  const digest = await crypto.subtle.digest("SHA-256", encodedVerifier);

  return toBase64Url(new Uint8Array(digest));
}

function getStoredAccessSession(): StoredAccessSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawSession = window.sessionStorage.getItem(
    COGNITO_SESSION_STORAGE_KEY,
  );

  if (rawSession === null) {
    return null;
  }

  try {
    const parsedSession = JSON.parse(rawSession) as StoredAccessSession;

    if (
      typeof parsedSession.accessToken !== "string" ||
      !parsedSession.accessToken ||
      typeof parsedSession.expiresAtMilliseconds !== "number" ||
      Date.now() >= parsedSession.expiresAtMilliseconds - 30_000
    ) {
      window.sessionStorage.removeItem(COGNITO_SESSION_STORAGE_KEY);
      return null;
    }

    return parsedSession;
  } catch {
    window.sessionStorage.removeItem(COGNITO_SESSION_STORAGE_KEY);
    return null;
  }
}

export function isCognitoLoginConfigured(): boolean {
  try {
    getCognitoConfiguration();
    return true;
  } catch {
    return false;
  }
}

export function getApiAuthorizationHeaders(): Record<string, string> {
  const accessSession = getStoredAccessSession();

  return accessSession
    ? { Authorization: `Bearer ${accessSession.accessToken}` }
    : {};
}

export function getActiveWorkspaceSlug(): string | null {
  const storedWorkspaceSlug =
    typeof window === "undefined"
      ? null
      : window.sessionStorage.getItem(ACTIVE_WORKSPACE_STORAGE_KEY)?.trim();

  if (storedWorkspaceSlug) {
    return storedWorkspaceSlug;
  }

  return process.env.NEXT_PUBLIC_WORKSPACE_SLUG?.trim() || null;
}

export function getActiveWorkspaceRole(): WorkspaceRole | null {
  const storedWorkspaceRole =
    typeof window === "undefined"
      ? null
      : window.sessionStorage.getItem(ACTIVE_WORKSPACE_ROLE_STORAGE_KEY);

  if (
    storedWorkspaceRole === "admin" ||
    storedWorkspaceRole === "manager" ||
    storedWorkspaceRole === "engineer"
  ) {
    return storedWorkspaceRole;
  }

  return null;
}

export function setActiveWorkspaceContext(
  workspaceSlug: string,
  workspaceRole: WorkspaceRole,
): void {
  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.setItem(
    ACTIVE_WORKSPACE_STORAGE_KEY,
    workspaceSlug.trim(),
  );
  window.sessionStorage.setItem(
    ACTIVE_WORKSPACE_ROLE_STORAGE_KEY,
    workspaceRole,
  );
}

export function getApiWorkspaceHeaders(): Record<string, string> {
  const workspaceSlug = getActiveWorkspaceSlug();

  return workspaceSlug
    ? { "X-Workspace-Slug": workspaceSlug }
    : {};
}

export async function beginCognitoSignIn(): Promise<void> {
  const configuration = getCognitoConfiguration();
  const state = createRandomBase64Url(32);
  const verifier = createRandomBase64Url(64);
  const challenge = await createPkceChallenge(verifier);

  // PKCE prevents a stolen authorization code from being exchanged elsewhere.
  window.sessionStorage.setItem(COGNITO_STATE_STORAGE_KEY, state);
  window.sessionStorage.setItem(COGNITO_VERIFIER_STORAGE_KEY, verifier);

  const authorizationUrl = new URL(
    "/oauth2/authorize",
    configuration.managedLoginBaseUrl,
  );
  authorizationUrl.searchParams.set("response_type", "code");
  authorizationUrl.searchParams.set("client_id", configuration.clientId);
  authorizationUrl.searchParams.set("redirect_uri", configuration.redirectUri);
  authorizationUrl.searchParams.set("scope", "openid email profile");
  authorizationUrl.searchParams.set("state", state);
  authorizationUrl.searchParams.set("code_challenge_method", "S256");
  authorizationUrl.searchParams.set("code_challenge", challenge);

  window.location.assign(authorizationUrl.toString());
}

export async function completeCognitoSignIn(
  authorizationCode: string,
  returnedState: string,
): Promise<void> {
  const configuration = getCognitoConfiguration();
  const expectedState = window.sessionStorage.getItem(
    COGNITO_STATE_STORAGE_KEY,
  );
  const verifier = window.sessionStorage.getItem(
    COGNITO_VERIFIER_STORAGE_KEY,
  );

  if (
    expectedState === null ||
    verifier === null ||
    returnedState !== expectedState
  ) {
    throw new Error("The sign-in response could not be validated.");
  }

  const formBody = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: configuration.clientId,
    code: authorizationCode,
    redirect_uri: configuration.redirectUri,
    code_verifier: verifier,
  });

  const response = await fetch(
    `${configuration.managedLoginBaseUrl}/oauth2/token`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: formBody,
    },
  );

  if (!response.ok) {
    throw new Error("Cognito could not complete sign-in. Please try again.");
  }

  const payload: TokenEndpointResponse = await response.json();

  if (
    typeof payload.access_token !== "string" ||
    !payload.access_token ||
    typeof payload.expires_in !== "number" ||
    payload.expires_in <= 0
  ) {
    throw new Error("Cognito returned an invalid access session.");
  }

  // Keep only the short-lived API token for this browser tab.
  window.sessionStorage.setItem(
    COGNITO_SESSION_STORAGE_KEY,
    JSON.stringify({
      accessToken: payload.access_token,
      expiresAtMilliseconds: Date.now() + payload.expires_in * 1_000,
    } satisfies StoredAccessSession),
  );

  window.sessionStorage.removeItem(ACTIVE_WORKSPACE_STORAGE_KEY);
  window.sessionStorage.removeItem(ACTIVE_WORKSPACE_ROLE_STORAGE_KEY);
  window.sessionStorage.removeItem(COGNITO_STATE_STORAGE_KEY);
  window.sessionStorage.removeItem(COGNITO_VERIFIER_STORAGE_KEY);
}
