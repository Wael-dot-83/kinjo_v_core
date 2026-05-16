/**
 * KinJo authentication runtime.
 * Handles login, logout, MFA, session refresh, and authenticated fetch helpers.
 */

const AUTH_CONFIG = {
  tokenKey: "kinjo_token",
  tokenTypeKey: "kinjo_token_type",
  userKey: "kinjo_user",
  mfaTicketKey: "kinjo_mfa_ticket",
  mfaModeKey: "kinjo_mfa_mode",
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
  return document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") || "";
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
    if (localStorage.getItem(AUTH_CONFIG.tokenKey)) {
      return localStorage;
    }
    return sessionStorage;
  }

  setToken(token, tokenType = "bearer") {
    this.storage.setItem(AUTH_CONFIG.tokenKey, token);
    this.storage.setItem(AUTH_CONFIG.tokenTypeKey, tokenType);
  }

  setUser(user) {
    this.storage.setItem(AUTH_CONFIG.userKey, JSON.stringify(user));
  }

  static getToken() {
    return (
      localStorage.getItem(AUTH_CONFIG.tokenKey) ||
      sessionStorage.getItem(AUTH_CONFIG.tokenKey)
    );
  }

  static getTokenType() {
    return (
      localStorage.getItem(AUTH_CONFIG.tokenTypeKey) ||
      sessionStorage.getItem(AUTH_CONFIG.tokenTypeKey) ||
      "bearer"
    );
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

  static setPendingMfa(ticket, mode) {
    sessionStorage.setItem(AUTH_CONFIG.mfaTicketKey, ticket);
    sessionStorage.setItem(AUTH_CONFIG.mfaModeKey, mode);
  }

  static getMfaTicket() {
    return sessionStorage.getItem(AUTH_CONFIG.mfaTicketKey);
  }

  static getMfaMode() {
    return sessionStorage.getItem(AUTH_CONFIG.mfaModeKey);
  }

  static clearPendingMfa() {
    sessionStorage.removeItem(AUTH_CONFIG.mfaTicketKey);
    sessionStorage.removeItem(AUTH_CONFIG.mfaModeKey);
  }

  static clearAll() {
    [localStorage, sessionStorage].forEach((storage) => {
      storage.removeItem(AUTH_CONFIG.tokenKey);
      storage.removeItem(AUTH_CONFIG.tokenTypeKey);
      storage.removeItem(AUTH_CONFIG.userKey);
    });
    AuthStorage.clearPendingMfa();
    document.cookie = "kinjo_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    document.cookie = "kinjo_session=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  }

  static isAuthenticated() {
    return Boolean(AuthStorage.getToken());
  }

  static async ensureServerSession() {
    const token = AuthStorage.getToken();
    if (!token) {
      return false;
    }
    try {
      const response = await fetch(AUTH_CONFIG.refreshEndpoint, {
        method: "POST",
        headers: {
          Authorization: `${AuthStorage.getTokenType()} ${token}`,
        },
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
      const token = AuthStorage.getToken();
      const tokenType = AuthStorage.getTokenType();
      const method = (options.method || "GET").toUpperCase();
      const requestUrl = typeof url === "string" ? url : url?.url || "";
      const noAuthEndpoints = ["/token", "/api/auth/login"];
      const isLoginEndpoint = noAuthEndpoints.some((endpoint) =>
        requestUrl.includes(endpoint),
      );

      options.headers = {
        Accept: "application/json",
        ...options.headers,
      };

      if (token && !isLoginEndpoint) {
        options.headers.Authorization = `${tokenType} ${token}`;
      }

      if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
        const csrfToken = readCsrfToken();
        if (csrfToken) {
          options.headers["X-CSRF-Token"] = csrfToken;
        }
      }

      const response = await originalFetch(url, options);
      if (response.status === 401 && !requestUrl.includes(AUTH_CONFIG.mfaVerifyEndpoint)) {
        AuthStorage.clearAll();
        if (!window.location.pathname.startsWith("/login")) {
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
    "/help",
    "/privacy",
    "/terms",
  ];

  static isValidRedirectUrl(url) {
    if (!url || typeof url !== "string") {
      return false;
    }
    if (!url.startsWith("/") || url.startsWith("//")) {
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
    const redirectUrl = new URLSearchParams(window.location.search).get("redirect");
    if (!redirectUrl) {
      return null;
    }
    const decoded = decodeURIComponent(redirectUrl);
    return this.isValidRedirectUrl(decoded) ? decoded : null;
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
      if (currentPath === "/mfa/setup" && !AuthStorage.getMfaTicket()) {
        window.location.href = "/login";
        return false;
      }
      if (AuthStorage.isAuthenticated() && currentPath === "/login") {
        const hasCookie = await AuthStorage.ensureServerSession();
        const verifiedUser = await this.verifySession();
        if (verifiedUser && hasCookie) {
          const redirectUrl = this.getSafeRedirectFromQuery();
          if (redirectUrl) {
            window.location.href = redirectUrl;
          } else {
            this.redirectToDashboard(verifiedUser);
          }
          return false;
        }
        AuthStorage.clearAll();
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
  document.cookie = `kinjo_lang=${safeLang}; path=/; max-age=31536000; SameSite=Lax`;
}

function persistAuthenticatedSession(data, rememberMe = false) {
  if (!data || !data.access_token) {
    return;
  }
  const storage = new AuthStorage(rememberMe);
  storage.setToken(data.access_token, data.token_type || "bearer");
  storage.setUser(data.user);
  persistLanguage(data.user_lang);
  AuthStorage.clearPendingMfa();
  if (window.api && typeof window.api.setToken === "function") {
    window.api.setToken(data.access_token);
  }
}

class AuthService {
  static async login(username, password, rememberMe = false) {
    const formData = new URLSearchParams();
    formData.append("username", normalizeLoginIdentifier(username));
    formData.append("password", password);
    formData.append("grant_type", "password");
    formData.append("remember_me", rememberMe ? "true" : "false");

    const response = await fetch(AUTH_CONFIG.loginEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: formData.toString(),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(
        data.detail ||
          t(
            "تعذر تسجيل الدخول بالبيانات المدخلة.",
            "Unable to sign in with the provided credentials.",
          ),
      );
    }
    return data;
  }

  static async beginMfaSetup(ticket) {
    const response = await fetch(AUTH_CONFIG.mfaSetupEndpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ticket}`,
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || t("تعذر تهيئة المصادقة الثنائية.", "Unable to start MFA setup."));
    }
    return data;
  }

  static async verifyMfa(ticket, code) {
    const response = await fetch(AUTH_CONFIG.mfaVerifyEndpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ticket}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || t("رمز التحقق غير صحيح.", "Invalid verification code."));
    }
    return data;
  }

  static async logout() {
    try {
      await fetch(AUTH_CONFIG.logoutEndpoint, { method: "POST" }).catch(() => {});
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
      throw new Error(t("تعذر جلب بيانات المستخدم.", "Unable to fetch user profile."));
    }
    return response.json();
  }

  static async refreshToken() {
    try {
      const response = await fetch(AUTH_CONFIG.refreshEndpoint, { method: "POST" });
      if (!response.ok) {
        return false;
      }
      const data = await response.json().catch(() => ({}));
      if (!data.access_token) {
        return false;
      }
      const storage = AuthStorage.getActiveStorage();
      storage.setItem(AUTH_CONFIG.tokenKey, data.access_token);
      if (data.user) {
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

  if (loginBtn) {
    loginBtn.disabled = true;
    loginBtn.querySelector(".btn-text")?.classList.add("d-none");
    loginBtn.querySelector(".btn-loading")?.classList.remove("d-none");
  }
  errorAlert?.classList.add("d-none");

  try {
    const data = await AuthService.login(username, password, rememberMe);
    persistLanguage(data.user_lang);

    if (data.mfa_required) {
      AuthStorage.setPendingMfa(
        data.mfa_ticket,
        data.mfa_setup_required ? "setup" : "challenge",
      );
      window.location.href = data.mfa_redirect || `${AUTH_CONFIG.mfaSetupPage}?mode=setup`;
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
    if (errorAlert && errorMessage) {
      errorMessage.textContent = error.message;
      errorAlert.classList.remove("d-none");
    } else {
      alert(error.message);
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

  const ticket = AuthStorage.getMfaTicket();
  const mode = AuthStorage.getMfaMode() || new URLSearchParams(window.location.search).get("mode") || "setup";
  const errorBox = document.getElementById("mfaError");
  const errorText = document.getElementById("mfaErrorMessage");
  const form = document.getElementById("mfaVerifyForm");
  const codeInput = document.getElementById("mfaCode");
  const qrImage = document.getElementById("mfaQrImage");
  const manualKey = document.getElementById("mfaManualKey");
  const setupPanel = document.getElementById("mfaSetupPanel");
  const heading = document.getElementById("mfaHeading");
  const intro = document.getElementById("mfaIntro");

  if (!ticket) {
    window.location.href = "/login";
    return;
  }

  if (mode === "challenge") {
    setupPanel?.classList.add("d-none");
    if (heading) {
      heading.textContent = t("أدخل رمز التحقق", "Enter your verification code");
    }
    if (intro) {
      intro.textContent = t(
        "أدخل الرمز المكون من 6 أرقام من تطبيق المصادقة لإكمال تسجيل الدخول.",
        "Enter the 6-digit code from your authenticator app to finish signing in.",
      );
    }
  } else {
    try {
      const setupData = await AuthService.beginMfaSetup(ticket);
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
      const data = await AuthService.verifyMfa(ticket, code);
      persistAuthenticatedSession(data, false);
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
  if (confirm(t("هل أنت متأكد من تسجيل الخروج؟", "Are you sure you want to sign out?"))) {
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
    throw new Error(response.statusText || "Request failed");
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
      document.getElementById("sessionExpiredAlert")?.classList.remove("d-none");
    }
  }

  await initMfaPage();

  if (AuthStorage.isAuthenticated()) {
    const user = AuthStorage.getUser();
    if (user) {
      updateUserUI(user);
    }
    window.setInterval(() => {
      AuthService.refreshToken().catch(() => {});
    }, 25 * 60 * 1000);
  }
}

window.AuthStorage = AuthStorage;
window.AuthService = AuthService;
window.AuthGuard = AuthGuard;
window.handleLogin = handleLogin;
window.handleLogout = handleLogout;
window.fetchWithAuth = fetchWithAuth;

document.addEventListener("DOMContentLoaded", () => {
  initAuth().catch((error) => {
    console.error("Auth initialization failed:", error);
  });
});
