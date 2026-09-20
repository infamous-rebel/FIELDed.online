/**
 * Authentication helpers for the frontend.
 *
 * Provides functions for managing auth state,
 * checking authentication, and handling token lifecycle.
 */

import {
  auth,
  storeTokens,
  clearTokens,
  getStoredToken,
  getStoredRefreshToken,
  type UserResponse,
} from "./api-client";

export interface AuthState {
  isAuthenticated: boolean;
  user: UserResponse | null;
}

/**
 * Check if the user is currently authenticated.
 */
export function isAuthenticated(): boolean {
  return getStoredToken() !== null;
}

/**
 * Login and store tokens.
 */
export async function login(email: string, password: string): Promise<UserResponse> {
  const tokens = await auth.login({ email, password });
  storeTokens(tokens);
  const user = await auth.me();
  return user;
}

/**
 * Register a new account, login, and store tokens.
 */
export async function register(
  email: string,
  password: string,
  firstName: string,
  lastName: string,
): Promise<UserResponse> {
  await auth.register({ email, password, first_name: firstName, last_name: lastName });
  return login(email, password);
}

/**
 * Logout and clear tokens.
 */
export async function logout(): Promise<void> {
  try {
    const refreshToken = getStoredRefreshToken();
    await auth.logout(refreshToken || undefined);
  } catch {
    // Ignore errors — we're clearing tokens regardless
  } finally {
    clearTokens();
  }
}

/**
 * Get the current user's info (requires stored token).
 */
export async function getCurrentUser(): Promise<UserResponse> {
  return auth.me();
}
