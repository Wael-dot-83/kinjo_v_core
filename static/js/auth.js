/**
 * KinJo authentication runtime.
 * Handles login, logout, MFA, session refresh, and authenticated fetch helpers.
 */

const AUTH_CONFIG = {
  userKey: "kinjo_user",
  loginEndpoint: "/token",
  logoutEndpoint: "/api/auth/logout",
  refreshEndpoint: "/api/auth/refresh",
  meEndpoint: "/api/users/me",
  mfaSetupEndpoint: "/api/auth/mfa/setup",
  mfaVerifyEndpoint: "/api/auth/mfa/verify",
  mfaSetupPage: "/mfa/setup",
};

const CSRF_CONFIG = {
  cookieName: "kinjo_csrf_token",
};

const inMemoryMfaState = {
  mode: null,
};

function currentLanguage() {
  const lang = (document.documentElement.lang || "ar").toLowerCase();
  return lang.startsWith("en") ? "en" : "ar";
}

function t(arText, enText) {
  return currentLanguage() === "en" ? enText : arText;
}

function safeJsonParse(value, fallback = null) {
  try {
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}

function readMetaContent(name) {
  return (
    document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") ||
    ""
  );
}

function readCsrfToken() {
  return (
    AuthStorage.getCookie(CSRF_CONFIG.cookieName) ||
    readMetaContent("csrf-token") ||
    document.getElementById("csrfToken")?.value ||
    ""
  );
}

function normalizeLoginIdentifier(raw) {
  const value = String(raw || "").trim();
  if (!value) {
    return "";
  }

  const cleaned = value.replace(/[\s\-+]/g, "");
  let phone = cleaned;
  if (phone.startsWith("962") && phone.length === 12) {
    phone = `0${phone.slice(3)}`;
  } else if (phone.startsWith("00962") && phone.length === 14) {
    phone = `0${phone.slice(5)}`;
  }
  if (/^07\d{8}$/.test(phone)) {
    return phone;
  }
  return value;
}

class AuthStorage {
  constructor(rememberMe = false) {
    this.storage = rememberMe ? localStorage : sessionStorage;
  }

  static getActiveStorage() {
    if (localStorage.getItem(AUTH_CONFIG.userKey)) {
      return localStorage;
    }
    return sessionStorage;
  }

  setToken(_token, _tokenType = "bearer") {
    // Token storage in web storage is intentionally disabled.
    // The backend sets an HttpOnly 'kinjo_session' cookie on login/refresh;
    // that cookie is sent automatically by the browser with every same-origin request.
    // Storing the JWT in localStorage or sessionStorage would expose it to XSS.
  }

  setUser(user) {
    this.storage.setItem(AUTH_CONFIG.userKey, JSON.stringify(user));
  }

  static getToken() {
    // The real session token lives in the HttpOnly 'kinjo_session' cookie (not readable
    // from JS). Return the CSRF cookie value as a truthy sentinel so callers that test
    // `if (getToken())` still work correctly without exposing the JWT to JS.
    return AuthStorage.getCookie(CSRF_CONFIG.cookieName) || null;
  }

  static getTokenType() {
    return "bearer";
  }

  static getUser() {
    return safeJsonParse(
      localStorage.getItem(AUTH_CONFIG.userKey) ||
        sessionStorage.getItem(AUTH_CONFIG.userKey),
      null,
    );
  }

  static getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
      return parts.pop().split(";").shift();
    }
    return null;
  }

  static setPendingMfaMode(mode) {
    inMemoryMfaState.mode = mode || null;
  }

  static getMfaMode() {
    return inMemoryMfaState.mode;
  }

  static clearPendingMfa() {
    inMemoryMfaState.mode = null;
  }

  static clearAll() {
    // Remove any user profile data stored in web storage.
    [localStorage, sessionStorage].forEach((storage) => {
      storage.removeItem(AUTH_CONFIG.userKey);
    });
    AuthStorage.clearPendingMfa();
    // Expire any legacy plaintext cookie that older code may have set.
    document.cookie =
      "kinjo_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    // The HttpOnly kinjo_session and kinjo_csrf_token cookies are cleared by the
    // server /api/auth/logout endpoint via Set-Cookie headers.
  }

  static isAuthenticated() {
    // The HttpOnly session cookie is unreadable from JS; use the non-HttpOnly
    // CSRF cookie as the JS-visible signal that an active session exists.
    return Boolean(AuthStorage.getCookie(CSRF_CONFIG.cookieName));
  }

  static async ensureServerSession() {
    if (!AuthStorage.isAuthenticated()) {
      return false;
    }
    try {
      // The HttpOnly kinjo_session cookie is sent automatically by the browser.
      // No Authorization header is needed or safe to use here.
      const response = await fetch(AUTH_CONFIG.refreshEndpoint, {
        method: "POST",
      });
      return response.ok;
    } catch {
      return false;
    }
  }
}

class HttpInterceptor {
  static install() {
    if (window.__kinjoAuthFetchInstalled) {
      return;
    }
    window.__kinjoAuthFetchInstalled = true;

    const originalFetch = window.fetch.bind(window);
    window.fetch = async function patchedFetch(url, options = {}) {
      const method = (options.method || "GET").toUpperCase();
      const requestUrl = typeof url === "string" ? url : url?.url || "";

      options.headers = {
        Accept: "application/json",
        ...options.headers,
      };

      // Authorization header removed: session is carried by the HttpOnly kinjo_session
      // cookie which the browser sends automatically with every same-origin request.
      // Do not inject the JWT into an Authorization header; that would reintroduce
      // XSS-token-theft exposure.

      // Defensively drop an Authorization header that is really the CSRF sentinel.
      //
      // AuthStorage.getToken() deliberately returns the kinjo_csrf_token cookie as a
      // truthy sentinel, because the real JWT lives in the HttpOnly kinjo_session
      // cookie and is unreadable from JS. That is fine for the `if (!getToken())`
      // liveness checks it was designed for, but ~30 call sites across 18 templates
      // still do:
      //
      //     headers['Authorization'] = `Bearer ${AuthService.getToken()}`
      //
      // which presents the CSRF token as a credential. The server rejects it with 401
      // even though the session cookie accompanying the request is perfectly valid,
      // and the 401 branch below then clears local state and redirects to
      // /login?expired=true — silently logging the user out mid-action. Stripping the
      // header lets the session cookie authenticate the request, which is what every
      // one of those call sites actually intended.
      //
      // Only the exact sentinel value is removed, so a genuine bearer token (a JWT,
      // which never equals the CSRF cookie) still passes through untouched.
      const csrfSentinel = readCsrfToken();
      if (csrfSentinel) {
        for (const headerName of Object.keys(options.headers)) {
          if (headerName.toLowerCase() !== "authorization") continue;
          const headerValue = String(options.headers[headerName] ?? "").trim();
          if (
            headerValue === csrfSentinel ||
            headerValue === `Bearer ${csrfSentinel}`
          ) {
            delete options.headers[headerName];
          }
        }
      }

      if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
        const csrfToken = readCsrfToken();
        if (csrfToken) {
          options.headers["X-CSRF-Token"] = csrfToken;
        }
      }

      const response = await originalFetch(url, options);
      if (
        response.status === 401 &&
        !requestUrl.includes(AUTH_CONFIG.mfaVerifyEndpoint)
      ) {
        // Server has invalidated the session (cookie expired/revoked).
        // Clear any local state and redirect to login.
        AuthStorage.clearAll();
        if (!window.location.pathname.startsWith("/login")) {
          try {
            sessionStorage.setItem(
              "kinjo_last_identifier",
              document.getElementById("username")?.value || "",
            );
          } catch {
            // sessionStorage may be unavailable in some contexts
          }
          window.location.href = "/login?expired=true";
        }
      }
      return response;
    };
  }
}

class AuthGuard {
  static publicRoutes = [
    "/",
    "/login",
    "/register",
    "/mfa/setup",
    "/change-password",
    "/forgot-password",
    "/reset-password",
  ];

  static isValidRedirectUrl(url) {
    if (!url || typeof url !== "string") {
      return false;
    }
    if (!url.startsWith("/") || url.startsWith("//")) {
      return false;
    }
    // Prevent redirect loops: never redirect back to an auth/public page.
    const pathOnly = url.split("?")[0].toLowerCase();
    if (AuthGuard.publicRoutes.includes(pathOnly)) {
      return false;
    }
    const lowered = url.toLowerCase();
    if (
      lowered.includes("javascript:") ||
      lowered.includes("data:") ||
      lowered.includes("vbscript:")
    ) {
      return false;
    }
    try {
      const decoded = decodeURIComponent(url);
      return !decoded.startsWith("//") && !decoded.includes("://");
    } catch {
      return false;
    }
  }

  static getSafeRedirectFromQuery() {
    const redirectUrl = new URLSearchParams(window.location.search).get(
      "redirect",
    );
    if (!redirectUrl) {
      return null;
    }
    try {
      // URLSearchParams already performs one decode. A second decode is kept
      // for legacy double-encoded return URLs, but malformed input must never
      // interrupt a successful login.
      const decoded = decodeURIComponent(redirectUrl);
      return this.isValidRedirectUrl(decoded) ? decoded : null;
    } catch {
      return null;
    }
  }

  static redirectToDashboard(user) {
    const roleRedirects = {
      ADMIN: "/dashboard",
      MANAGER: "/dashboard",
      SUPERVISOR: "/supervisor/dashboard",
      PARENT: "/parent/dashboard",
    };
    window.location.href =
      (user && user.role && roleRedirects[user.role]) || "/dashboard";
  }

  static async verifySession() {
    try {
      const currentUser = await AuthService.getCurrentUser();
      if (currentUser) {
        const storage = AuthStorage.getActiveStorage();
        storage.setItem(AUTH_CONFIG.userKey, JSON.stringify(currentUser));
      }
      return currentUser;
    } catch {
      return null;
    }
  }

  static async check() {
    const currentPath = window.location.pathname;
    if (this.publicRoutes.includes(currentPath)) {
      // The kinjo_mfa_ticket cookie is HttpOnly and cannot be read from JS.
      // Use the in-memory MFA state or the ?mode= query parameter instead.
      if (currentPath === "/mfa/setup" && !inMemoryMfaState.mode && !new URLSearchParams(window.location.search).get("mode")) {
        window.location.href = "/login";
        return false;
      }
      // Only probe the server for an existing session when this browser shows
      // evidence of a PRIOR login (a cached user profile from a previous
      // successful sign-in). The CSRF cookie is NOT a valid signal here: the
      // CSRF middleware sets kinjo_csrf_token on every safe GET, so an
      // anonymous visitor to /login would otherwise trigger a needless
      // /api/auth/refresh that 401s and logs a console error on each load.
      if (AuthStorage.getUser() && currentPath === "/login") {
        const hasCookie = await AuthStorage.ensureServerSession();
        if (hasCookie) {
          const verifiedUser = await this.verifySession();
          if (verifiedUser) {
            const redirectUrl = this.getSafeRedirectFromQuery();
            if (redirectUrl) {
              window.location.href = redirectUrl;
            } else {
              this.redirectToDashboard(verifiedUser);
            }
            return false;
          }
        }
        AuthStorage.clearAll();
      }
      // Not redirecting — reveal the page now
      if (typeof window.__kinjoRevealPage === "function") {
        window.__kinjoRevealPage();
      }
      return true;
    }

    if (!AuthStorage.isAuthenticated()) {
      const redirect = encodeURIComponent(currentPath);
      window.location.href = `/login?redirect=${redirect}`;
      return false;
    }
    return true;
  }
}

function persistLanguage(userLang) {
  const safeLang = ["ar", "en"].includes(String(userLang || "").toLowerCase())
    ? String(userLang).toLowerCase()
    : "ar";
  localStorage.setItem("kinjo_lang", safeLang);
  localStorage.setItem("admin_language", safeLang);
  // kinjo_lang is written by the server only (see ui_language.py): a
  // host-only document.cookie write cannot overwrite the domain-wide
  // cookie, so both survived with different values and the language
  // rendered one step behind. Ask the server to set it instead.
  fetch("/api/ui-language", { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language: safeLang }) }).catch(function () {});
}

function persistAuthenticatedSession(data, rememberMe = false) {
  if (!data) {
    return;
  }
  // The backend sets the HttpOnly kinjo_session cookie in its response headers.
  // We intentionally do NOT write the access_token to web storage here.
  const storage = new AuthStorage(rememberMe);
  if (data.user) {
    storage.setUser(data.user);
  }
  persistLanguage(data.user_lang);
  AuthStorage.clearPendingMfa();
  // Legacy: if a window.api wrapper exists, signal that authentication succeeded
  // but do not hand it a raw JWT string anymore.
  if (window.api && typeof window.api.setToken === "function") {
    window.api.setToken(null);
  }
}

class AuthService {
  static async login(username, password, rememberMe = false) {
    const formData = new URLSearchParams();
    formData.append("username", normalizeLoginIdentifier(username));
    formData.append("password", password);
    formData.append("grant_type", "password");
    formData.append("remember_me", rememberMe ? "true" : "false");
    if (typeof window.getCaptchaToken === "function") {
      formData.append("captcha_token", window.getCaptchaToken());
    }

    let response;
    try {
      response = await fetch(AUTH_CONFIG.loginEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: formData.toString(),
      });
    } catch (networkError) {
      // fetch() rejects only on a network/connectivity failure, never on an HTTP
      // error status. Tag it so the caller can show a distinct connectivity
      // message instead of the generic credentials message.
      const err = new Error("network");
      err.kind = "network";
      throw err;
    }

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      // Do not surface the backend detail verbatim: it is an English-only,
      // enumeration-safe string, so the localized message is chosen by status
      // in describeLoginError().
      const err = new Error(data.detail || "auth_failed");
      err.kind = "http";
      err.status = response.status;
      throw err;
    }
    return data;
  }

  static async beginMfaSetup() {
    const response = await fetch(AUTH_CONFIG.mfaSetupEndpoint, {
      method: "POST",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(
        data.detail ||
          t("تعذر تهيئة المصادقة الثنائية.", "Unable to start MFA setup."),
      );
    }
    return data;
  }

  static async verifyMfa(code) {
    const response = await fetch(AUTH_CONFIG.mfaVerifyEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(
        data.detail || t("رمز التحقق غير صحيح.", "Invalid verification code."),
      );
    }
    return data;
  }

  static async logout() {
    try {
      await fetch(AUTH_CONFIG.logoutEndpoint, { method: "POST" }).catch(
        () => {},
      );
    } finally {
      AuthStorage.clearAll();
      if (window.api && typeof window.api.setToken === "function") {
        window.api.setToken(null);
      }
      window.location.href = "/login";
    }
  }

  static async getCurrentUser() {
    const response = await fetch(AUTH_CONFIG.meEndpoint);
    if (!response.ok) {
      throw new Error(
        t("تعذر جلب بيانات المستخدم.", "Unable to fetch user profile."),
      );
    }
    return response.json();
  }

  static async refreshToken() {
    try {
      // The backend renews the HttpOnly cookie in its response Set-Cookie headers.
      // We only need to update the cached user profile if the server returns one.
      const response = await fetch(AUTH_CONFIG.refreshEndpoint, {
        method: "POST",
      });
      if (!response.ok) {
        return false;
      }
      const data = await response.json().catch(() => ({}));
      // Update the cached user profile in sessionStorage (non-sensitive metadata only).
      if (data.user) {
        const storage = AuthStorage.getActiveStorage();
        storage.setItem(AUTH_CONFIG.userKey, JSON.stringify(data.user));
      }
      return true;
    } catch {
      return false;
    }
  }

  static isAuthenticated() {
    return AuthStorage.isAuthenticated();
  }

  static hasRole(requiredRole) {
    return AuthStorage.getUser()?.role === requiredRole;
  }

  static hasAnyRole(roles) {
    const role = AuthStorage.getUser()?.role;
    return Boolean(role && roles.includes(role));
  }

  static getToken() {
    return AuthStorage.getToken();
  }
}

function describeLoginError(error) {
  // Map a login failure to one localized, enumeration-safe message. Never echo
  // the raw backend detail (English-only) or a raw fetch TypeError.
  if (error && error.kind === "network") {
    return t(
      "تعذّر الاتصال بالخدمة. تحقق من اتصالك بالإنترنت وحاول مرة أخرى.",
      "Couldn't reach the service. Check your internet connection and try again.",
    );
  }
  const status = error && error.status;
  if (status === 423) {
    return t(
      "تم قفل الحساب مؤقتاً بعد عدة محاولات. حاول لاحقاً أو تواصل مع الدعم.",
      "This account is temporarily locked after several attempts. Try again later or contact support.",
    );
  }
  if (status === 429) {
    return t(
      "محاولات كثيرة جداً. انتظر قليلاً ثم حاول مرة أخرى.",
      "Too many attempts. Please wait a moment and try again.",
    );
  }
  if (status === 400 || status === 401) {
    return t(
      "تعذّر تسجيل الدخول. تحقق من بيانات الدخول وحاول مرة أخرى.",
      "Sign-in failed. Check your details and try again.",
    );
  }
  return t(
    "حدث خطأ غير متوقع. حاول مرة أخرى بعد قليل.",
    "Something went wrong. Please try again shortly.",
  );
}

async function handleLogin(event) {
  event.preventDefault();
  const form = event.target;
  if (!form.checkValidity()) {
    form.classList.add("was-validated");
    return;
  }

  const username = document.getElementById("username")?.value?.trim() || "";
  const password = document.getElementById("password")?.value || "";
  const rememberMe = document.getElementById("rememberMe")?.checked || false;
  const loginBtn = document.getElementById("loginBtn");
  const errorAlert = document.getElementById("loginError");
  const errorMessage = document.getElementById("loginErrorMessage");

  try {
    const attempts = parseInt(sessionStorage.getItem("kinjo_login_attempts") || "0", 10);
    if (attempts >= 5) {
      const lastAttempt = parseInt(sessionStorage.getItem("kinjo_login_last_attempt") || "0", 10);
      const now = Date.now();
      if (now - lastAttempt < 30000) {
        const waitSecs = Math.ceil((30000 - (now - lastAttempt)) / 1000);
        if (errorMessage && errorAlert) {
          errorMessage.textContent = t(
            "محاولات كثيرة جداً. انتظر " + waitSecs + " ثانية قبل المحاولة مرة أخرى.",
            "Too many failed attempts. Please wait " + waitSecs + " seconds before trying again.",
          );
          errorAlert.classList.remove("d-none");
        }
        if (loginBtn) {
          loginBtn.disabled = false;
          loginBtn.querySelector(".btn-text")?.classList.remove("d-none");
          loginBtn.querySelector(".btn-loading")?.classList.add("d-none");
        }
        return;
      }
    }
  } catch {
    // ignore storage errors
  }

  if (loginBtn) {
    loginBtn.disabled = true;
    loginBtn.querySelector(".btn-text")?.classList.add("d-none");
    loginBtn.querySelector(".btn-loading")?.classList.remove("d-none");
  }
  errorAlert?.classList.add("d-none");

  try {
    const data = await AuthService.login(username, password, rememberMe);
    try {
      sessionStorage.removeItem("kinjo_login_attempts");
    } catch {
      // ignore
    }
    persistLanguage(data.user_lang);

    if (data.mfa_required) {
      AuthStorage.setPendingMfaMode(
        data.mfa_setup_required ? "setup" : "challenge",
      );
      window.location.href =
        data.mfa_redirect || `${AUTH_CONFIG.mfaSetupPage}?mode=setup`;
      return;
    }

    persistAuthenticatedSession(data, rememberMe);
    if (data.user?.must_change_password) {
      window.location.href = "/change-password";
      return;
    }

    const redirectUrl = AuthGuard.getSafeRedirectFromQuery();
    if (redirectUrl) {
      window.location.href = redirectUrl;
    } else {
      AuthGuard.redirectToDashboard(data.user);
    }
  } catch (error) {
    try {
      const attempts = parseInt(sessionStorage.getItem("kinjo_login_attempts") || "0", 10) + 1;
      sessionStorage.setItem("kinjo_login_attempts", String(attempts));
      sessionStorage.setItem("kinjo_login_last_attempt", String(Date.now()));
    } catch {
      // ignore storage errors
    }
    const message = describeLoginError(error);
    if (errorAlert && errorMessage) {
      errorMessage.textContent = message;
      errorAlert.classList.remove("d-none");
    } else {
      alert(message);
    }
  } finally {
    if (loginBtn) {
      loginBtn.disabled = false;
      loginBtn.querySelector(".btn-text")?.classList.remove("d-none");
      loginBtn.querySelector(".btn-loading")?.classList.add("d-none");
    }
  }
}

async function initMfaPage() {
  const root = document.getElementById("mfaSetupApp");
  if (!root) {
    return;
  }

  const mode =
    AuthStorage.getMfaMode() ||
    new URLSearchParams(window.location.search).get("mode") ||
    "setup";
  const errorBox = document.getElementById("mfaError");
  const errorText = document.getElementById("mfaErrorMessage");
  const form = document.getElementById("mfaVerifyForm");
  const codeInput = document.getElementById("mfaCode");
  const qrImage = document.getElementById("mfaQrImage");
  const manualKey = document.getElementById("mfaManualKey");
  const setupPanel = document.getElementById("mfaSetupPanel");
  const heading = document.getElementById("mfaHeading");
  const intro = document.getElementById("mfaIntro");

  if (mode === "challenge") {
    setupPanel?.classList.add("d-none");
    if (heading) {
      heading.textContent = t(
        "أدخل رمز التحقق",
        "Enter your verification code",
      );
    }
    if (intro) {
      intro.textContent = t(
        "أدخل الرمز المكون من 6 أرقام من تطبيق المصادقة لإكمال تسجيل الدخول.",
        "Enter the 6-digit code from your authenticator app to finish signing in.",
      );
    }
  } else {
    try {
      const setupData = await AuthService.beginMfaSetup();
      const spinner = document.getElementById("mfaQrSpinner");
      if (qrImage) {
        qrImage.src = setupData.qr_code_data_url;
        qrImage.classList.remove("d-none");
      }
      if (spinner) {
        spinner.classList.add("d-none");
      }
      if (manualKey) {
        manualKey.textContent = setupData.manual_key;
      }
    } catch (error) {
      const spinner = document.getElementById("mfaQrSpinner");
      if (spinner) {
        spinner.classList.add("d-none");
      }
      if (errorBox && errorText) {
        errorText.textContent = error.message;
        errorBox.classList.remove("d-none");
      }
    }
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const code = codeInput?.value?.trim() || "";
    if (!code) {
      return;
    }
    errorBox?.classList.add("d-none");
    try {
      const data = await AuthService.verifyMfa(code);
      // MFA is a second step of the original login, so preserve its Remember
      // Me choice when choosing profile storage. Otherwise the persistent
      // HttpOnly session outlives the sessionStorage profile and cannot be
      // restored after a browser restart.
      persistAuthenticatedSession(data, data.remember_me === true);
      if (data.user?.must_change_password) {
        window.location.href = "/change-password";
        return;
      }
      AuthGuard.redirectToDashboard(data.user);
    } catch (error) {
      if (errorBox && errorText) {
        errorText.textContent = error.message;
        errorBox.classList.remove("d-none");
      }
    }
  });
}

function handleLogout(event) {
  if (event) {
    event.preventDefault();
  }
  if (
    confirm(
      t("هل أنت متأكد من تسجيل الخروج؟", "Are you sure you want to sign out?"),
    )
  ) {
    AuthService.logout();
  }
}

function updateUserUI(user) {
  document.querySelectorAll(".user-name, #userName").forEach((element) => {
    element.textContent = user.username || user.email || "";
  });
}

async function fetchWithAuth(url, options = {}) {
  if (!AuthStorage.isAuthenticated()) {
    window.location.href = "/login";
    return null;
  }
  const response = await fetch(url, options);
  if (response.status === 401) {
    AuthStorage.clearAll();
    window.location.href = "/login?expired=true";
    return null;
  }
  if (!response.ok) {
    // Read the real backend error detail (e.g. "Username already exists")
    // before throwing -- previously this threw response.statusText only
    // ("Conflict", "Bad Request"), discarding the JSON body entirely, so
    // every admin page showed a meaningless generic error on every failed
    // POST/PUT/PATCH/DELETE regardless of what the backend actually said.
    let message = response.statusText || "Request failed";
    let fields = null;
    try {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const data = await response.json();
        if (data.error && typeof data.error.message === "string") {
          // Standardized APIError envelope (admin_security.py's
          // create_error_response): {"error": {"code","message","fields",...}}
          message = data.error.message;
          fields = data.error.fields || null;
        } else if (typeof data.detail === "string") {
          // Plain FastAPI HTTPException(detail="...")
          message = data.detail;
        } else if (Array.isArray(data.detail) && data.detail.length) {
          // Pydantic 422 validation error array
          message = data.detail
            .map((item) => (item && typeof item === "object" ? item.msg : item))
            .filter(Boolean)
            .join("; ") || message;
        } else if (typeof data.message === "string") {
          message = data.message;
        }
      }
    } catch (e) {
      // Body unreadable/not JSON -- fall back to statusText set above.
    }
    const error = new Error(message);
    error.status = response.status;
    if (fields) {
      error.fields = fields;
    }
    throw error;
  }
  return response;
}

async function initAuth() {
  if (window.__kinjoAuthInitialized) {
    return;
  }
  window.__kinjoAuthInitialized = true;

  HttpInterceptor.install();
  if (!(await AuthGuard.check())) {
    return;
  }

  document
    .querySelectorAll('[data-action="logout"], .logout-btn, #logoutBtn')
    .forEach((btn) => btn.addEventListener("click", handleLogout));

  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", handleLogin);
      if (new URLSearchParams(window.location.search).get("expired") === "true") {
        document
          .getElementById("sessionExpiredAlert")
          ?.classList.remove("d-none");
        try {
          const lastId = sessionStorage.getItem("kinjo_last_identifier");
          const usernameInput = document.getElementById("username");
          if (lastId && usernameInput) {
            usernameInput.value = lastId;
          }
          sessionStorage.removeItem("kinjo_last_identifier");
        } catch {
          // ignore
        }
      }
  }

  await initMfaPage();

  if (AuthStorage.isAuthenticated()) {
    const user = AuthStorage.getUser();
    if (user) {
      updateUserUI(user);
    }
    window.setInterval(
      () => {
        AuthService.refreshToken().catch(() => {});
      },
      25 * 60 * 1000,
    );
  }
}

window.AuthStorage = AuthStorage;
window.AuthService = AuthService;
window.AuthGuard = AuthGuard;
window.handleLogin = handleLogin;
window.handleLogout = handleLogout;
window.fetchWithAuth = fetchWithAuth;
window.currentLanguage = currentLanguage;
window.t = t;

// Install the fetch interceptor NOW, at script-evaluation time, rather than
// waiting for initAuth() on DOMContentLoaded.
//
// auth.js is a classic script at the end of <body>, so it evaluates before
// DOMContentLoaded fires — but inline page scripts higher up the document
// register their own DOMContentLoaded handlers first, and listeners run in
// registration order. Any page that fetched during its own DOMContentLoaded
// handler (communication/modals/new_message.html's initMessageForm is the
// clearest case) therefore ran against the *unpatched* fetch: no CSRF header,
// no 401 handling, and no chance for the interceptor to strip a stale
// Authorization header. Installing here closes that window; the call left in
// initAuth() is harmless because install() is guarded by
// __kinjoAuthFetchInstalled.
HttpInterceptor.install();

document.addEventListener("DOMContentLoaded", () => {
  initAuth().catch((error) => {
    console.error("Auth initialization failed:", error);
  });
});



