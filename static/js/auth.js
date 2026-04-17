/**
 * KinJo Authentication Module
 * Comprehensive authentication handling for the frontend
 * Fixes: Token storage, HTTP interceptor, Auth guard, Session management
 */

// ============================================================================
// Auth Configuration
// ============================================================================

const AUTH_CONFIG = {
  tokenKey: "kinjo_token",
  tokenTypeKey: "kinjo_token_type",
  userKey: "kinjo_user",
  loginEndpoint: "/token",
  logoutEndpoint: "/api/auth/logout",
  refreshEndpoint: "/api/auth/refresh",
  meEndpoint: "/api/users/me",
  sessionTimeout: 30 * 60 * 1000, // 30 minutes in milliseconds
  rememberMeMaxAgeSeconds: 7 * 24 * 60 * 60, // 7 days
  tokenRefreshBuffer: 5 * 60 * 1000, // Refresh 5 minutes before expiry
};
const CSRF_CONFIG = {
  cookieName: "kinjo_csrf_token",
  tokenLengthBytes: 32,
};

// ============================================================================
// Auth Storage Manager
// ============================================================================

class AuthStorage {
  constructor(rememberMe = false) {
    this.storage = rememberMe ? localStorage : sessionStorage;
    this.rememberMe = rememberMe;
  }

  static getActiveStorage() {
    // Check localStorage first, then sessionStorage
    if (localStorage.getItem(AUTH_CONFIG.tokenKey)) {
      return localStorage;
    }
    return sessionStorage;
  }

  setToken(token, tokenType = "bearer") {
    this.storage.setItem(AUTH_CONFIG.tokenKey, token);
    this.storage.setItem(AUTH_CONFIG.tokenTypeKey, tokenType);
    const maxAge = this.rememberMe
      ? AUTH_CONFIG.rememberMeMaxAgeSeconds
      : Math.floor(AUTH_CONFIG.sessionTimeout / 1000);
    const isSecure = window.location.protocol === "https:";
    const secureFlag = isSecure ? "; Secure" : "";
    const csrfToken = AuthStorage.generateCsrfToken();
    AuthStorage.setCookie(CSRF_CONFIG.cookieName, csrfToken, maxAge, secureFlag);
  }

  static generateCsrfToken() {
    const array = new Uint8Array(CSRF_CONFIG.tokenLengthBytes);
    window.crypto.getRandomValues(array);
    return Array.from(array, (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  static setCookie(name, value, maxAge, secureFlag) {
    document.cookie = `${name}=${value}; path=/; max-age=${maxAge}; SameSite=Strict${secureFlag}`;
  }

  static getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
      return parts.pop().split(";").shift();
    }
    return null;
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

  setUser(user) {
    this.storage.setItem(AUTH_CONFIG.userKey, JSON.stringify(user));
  }

  static getToken() {
    return (
      localStorage.getItem(AUTH_CONFIG.tokenKey) || sessionStorage.getItem(AUTH_CONFIG.tokenKey)
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
    const userStr =
      localStorage.getItem(AUTH_CONFIG.userKey) || sessionStorage.getItem(AUTH_CONFIG.userKey);
    try {
      return userStr ? JSON.parse(userStr) : null;
    } catch {
      return null;
    }
  }

  static clearAll() {
    // Clear from both storages
    [localStorage, sessionStorage].forEach((storage) => {
      storage.removeItem(AUTH_CONFIG.tokenKey);
      storage.removeItem(AUTH_CONFIG.tokenTypeKey);
      storage.removeItem(AUTH_CONFIG.userKey);
    });
    // Clear cookie
    document.cookie = "kinjo_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    document.cookie = "kinjo_session=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    document.cookie = `${CSRF_CONFIG.cookieName}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  }

  static isAuthenticated() {
    return !!AuthStorage.getToken();
  }
}

// ============================================================================
// HTTP Interceptor - Automatically adds auth headers
// ============================================================================

class HttpInterceptor {
  static install() {
    const originalFetch = window.fetch;

    window.fetch = async function (url, options = {}) {
      const token = AuthStorage.getToken();
      const tokenType = AuthStorage.getTokenType();

      // Don't add auth header to login/register endpoints
      const noAuthEndpoints = [
        "/token",
        "/api/auth/login",
        "/api/auth/register",
        "/register/parent",
      ];
      const isAuthEndpoint = noAuthEndpoints.some((endpoint) => url.includes(endpoint));

      if (token && !isAuthEndpoint) {
        options.headers = {
          ...options.headers,
          Authorization: `${tokenType} ${token}`,
        };
      }

      const method = (options.method || "GET").toUpperCase();
      if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
        const csrfToken = AuthStorage.getCookie(CSRF_CONFIG.cookieName);
        if (csrfToken) {
          options.headers = {
            ...options.headers,
            "X-CSRF-Token": csrfToken,
          };
        }
      }

      try {
        const response = await originalFetch(url, options);

        // Handle 401 Unauthorized
        if (response.status === 401 && !isAuthEndpoint) {
          console.warn("Authentication expired, redirecting to login");
          AuthStorage.clearAll();

          // Don't redirect if already on login page
          if (!window.location.pathname.includes("/login")) {
            window.location.href = "/login?expired=true";
          }
        }

        return response;
      } catch (error) {
        console.error("Fetch error:", error);
        throw error;
      }
    };

    console.log("HTTP Interceptor installed");
  }
}

// ============================================================================
// Auth Guard - Protects routes that require authentication
// ============================================================================

class AuthGuard {
  static publicRoutes = [
    "/login",
    "/register",
    "/change-password",
    "/forgot-password",
    "/reset-password",
    "/help",
    "/privacy",
    "/terms",
    "/",
  ];

  static roleRoutes = {
    ADMIN: ["/admin", "/dashboard", "/kindergartens", "/users", "/kpi", "/reports"],
    MANAGER: [
      "/manager",
      "/dashboard",
      "/kindergartens",
      "/staff",
      "/children",
      "/attendance",
      "/reports",
      "/kpi",
    ],
    SUPERVISOR: ["/supervisor", "/dashboard", "/children", "/attendance", "/reports"],
    PARENT: ["/parent", "/dashboard", "/children", "/reports"],
  };

  static async check() {
    const currentPath = window.location.pathname;
    const isAuthenticated = AuthStorage.isAuthenticated();
    const user = AuthStorage.getUser();

    // Allow public routes
    if (this.publicRoutes.includes(currentPath)) {
      // If authenticated and on login page, redirect to dashboard
      if (isAuthenticated && currentPath === "/login") {
        const hasCookie = await AuthStorage.ensureServerSession();
        const verifiedUser = await this.verifySession();

        if (verifiedUser && hasCookie) {
          const redirectUrl = this.getSafeRedirectFromQuery();
          if (redirectUrl) {
            window.location.href = redirectUrl;
          } else {
            this.redirectToDashboard(verifiedUser || user);
          }
          return false;
        }

        if (verifiedUser && !hasCookie) {
          console.warn("Token present but auth cookie missing; clearing session.");
          AuthStorage.clearAll();
        } else if (!verifiedUser) {
          AuthStorage.clearAll();
        }
      }
      return true;
    }

    // Require authentication for other routes
    if (!isAuthenticated) {
      const redirect = encodeURIComponent(currentPath);
      window.location.href = `/login?redirect=${redirect}`;
      return false;
    }

    // Check role-based access (optional)
    // This can be uncommented for strict role-based routing
    /*
        if (user && user.role) {
            const allowedRoutes = this.roleRoutes[user.role] || [];
            const hasAccess = allowedRoutes.some(route => currentPath.startsWith(route));
            
            if (!hasAccess && !currentPath.startsWith('/dashboard')) {
                console.warn(`Access denied for role ${user.role} to ${currentPath}`);
                this.redirectToDashboard(user);
                return false;
            }
        }
        */

    return true;
  }

  static getSafeRedirectFromQuery() {
    const urlParams = new URLSearchParams(window.location.search);
    const redirectUrl = urlParams.get("redirect");
    if (!redirectUrl) {
      return null;
    }

    const decodedUrl = decodeURIComponent(redirectUrl);
    if (!AuthGuard.isValidRedirectUrl(decodedUrl)) {
      console.warn("Invalid redirect URL blocked:", decodedUrl);
      return null;
    }

    return decodedUrl;
  }

  static async verifySession() {
    try {
      const currentUser = await AuthService.getCurrentUser();
      if (currentUser) {
        const storage = AuthStorage.getActiveStorage();
        storage.setItem(AUTH_CONFIG.userKey, JSON.stringify(currentUser));
      }
      return currentUser;
    } catch (error) {
      console.warn("Session validation failed:", error);
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

    const redirectUrl = user && user.role ? roleRedirects[user.role] || "/dashboard" : "/dashboard";

    window.location.href = redirectUrl;
  }

  /**
   * Validate redirect URL to prevent open redirect attacks
   * Only allows relative URLs starting with / (not //)
   */
  static isValidRedirectUrl(url) {
    if (!url || typeof url !== "string") {
      return false;
    }

    // Must start with single forward slash (relative URL)
    // Reject protocol-relative URLs (//), absolute URLs, and javascript:
    if (!url.startsWith("/") || url.startsWith("//")) {
      return false;
    }

    // Block javascript: and data: schemes that might bypass the above
    const lowerUrl = url.toLowerCase();
    if (
      lowerUrl.includes("javascript:") ||
      lowerUrl.includes("data:") ||
      lowerUrl.includes("vbscript:")
    ) {
      return false;
    }

    // Ensure it's a valid path (no encoded dangerous characters)
    try {
      const decoded = decodeURIComponent(url);
      if (decoded.startsWith("//") || decoded.includes("://")) {
        return false;
      }
    } catch {
      return false;
    }

    return true;
  }
}

// ============================================================================
// Auth Service - Main authentication functions
// ============================================================================

class AuthService {
  /**
   * Login user with credentials
   */
  static async login(username, password, rememberMe = false) {
    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);
    formData.append("grant_type", "password");
    formData.append("remember_me", rememberMe ? "true" : "false");

    const response = await fetch(AUTH_CONFIG.loginEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Accept: "application/json",
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "فشل تسجيل الدخول. يرجى التحقق من البيانات.");
    }

    const data = await response.json();

    // Store auth data
    const storage = new AuthStorage(rememberMe);
    storage.setToken(data.access_token, data.token_type || "bearer");
    storage.setUser(data.user);

    // Persist UI language globally from server preference (fallback to existing value).
    const serverLang = typeof data.user_lang === "string" ? data.user_lang.toLowerCase() : "";
    const currentLang =
      localStorage.getItem("kinjo_lang") || localStorage.getItem("admin_language") || "";
    const safeLang = ["ar", "en"].includes(serverLang)
      ? serverLang
      : ["ar", "en"].includes(currentLang)
        ? currentLang
        : "ar";
    localStorage.setItem("kinjo_lang", safeLang);
    localStorage.setItem("admin_language", safeLang);
    document.cookie = `kinjo_lang=${safeLang}; path=/; max-age=31536000; SameSite=Lax`;

    // Update the global api object if exists
    if (window.api && typeof window.api.setToken === "function") {
      window.api.setToken(data.access_token);
    }

    return data;
  }

  /**
   * Logout user and clear session
   */
  static async logout() {
    try {
      // Call logout endpoint if available
      await fetch(AUTH_CONFIG.logoutEndpoint, {
        method: "POST",
        headers: {
          Authorization: `${AuthStorage.getTokenType()} ${AuthStorage.getToken()}`,
        },
      }).catch(() => {});
    } finally {
      // Always clear local storage
      AuthStorage.clearAll();

      // Clear api token if exists
      if (window.api && typeof window.api.setToken === "function") {
        window.api.setToken(null);
      }

      window.location.href = "/login";
    }
  }

  /**
   * Get current user info from API
   */
  static async getCurrentUser() {
    const response = await fetch(AUTH_CONFIG.meEndpoint, {
      headers: {
        Authorization: `${AuthStorage.getTokenType()} ${AuthStorage.getToken()}`,
      },
    });

    if (!response.ok) {
      throw new Error("تعذر جلب بيانات المستخدم");
    }

    return await response.json();
  }

  /**
   * Refresh token before expiry
   */
  static async refreshToken() {
    try {
      const response = await fetch(AUTH_CONFIG.refreshEndpoint, {
        method: "POST",
        headers: {
          Authorization: `${AuthStorage.getTokenType()} ${AuthStorage.getToken()}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        const storage = AuthStorage.getActiveStorage();
        storage.setItem(AUTH_CONFIG.tokenKey, data.access_token);
        return true;
      }
    } catch (error) {
      console.error("Token refresh failed:", error);
    }
    return false;
  }

  /**
   * Check if user is currently authenticated
   */
  static isAuthenticated() {
    return AuthStorage.isAuthenticated();
  }

  /**
   * Check if user has specific role
   */
  static hasRole(requiredRole) {
    const user = AuthStorage.getUser();
    return user && user.role === requiredRole;
  }

  /**
   * Check if user has any of the specified roles
   */
  static hasAnyRole(roles) {
    const user = AuthStorage.getUser();
    return user && roles.includes(user.role);
  }

  /**
   * Get the current authentication token
   */
  static getToken() {
    return AuthStorage.getToken();
  }
}

// ============================================================================
// Login Form Handler
// ============================================================================

async function handleLogin(event) {
  event.preventDefault();

  const form = event.target;
  if (!form.checkValidity()) {
    form.classList.add("was-validated");
    return;
  }

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const rememberMe = document.getElementById("rememberMe")?.checked || false;

  const loginBtn = document.getElementById("loginBtn");
  const errorAlert = document.getElementById("loginError");
  const errorMessage = document.getElementById("loginErrorMessage");

  // Show loading state
  if (loginBtn) {
    const btnText = loginBtn.querySelector(".btn-text");
    const btnLoading = loginBtn.querySelector(".btn-loading");
    if (btnText) btnText.classList.add("d-none");
    if (btnLoading) btnLoading.classList.remove("d-none");
    loginBtn.disabled = true;
  }

  if (errorAlert) {
    errorAlert.classList.add("d-none");
  }

  try {
    const data = await AuthService.login(username, password, rememberMe);

    console.log("Login successful:", data.user);

    // Check if password change is required
    if (data.user.must_change_password) {
      console.log("Password change required, redirecting...");

      // Store auth data temporarily
      const storage = new AuthStorage(rememberMe);
      storage.setToken(data.access_token, data.token_type || "bearer");
      storage.setUser(data.user);

      // Redirect to password change page
      window.location.href = "/change-password";
      return;
    }

    // Show success briefly
    if (typeof showToast === "function") {
      showToast("تم تسجيل الدخول بنجاح!", "success");
    }

    // Redirect based on role or original destination
    const urlParams = new URLSearchParams(window.location.search);
    const redirectUrl = urlParams.get("redirect");

    if (redirectUrl) {
      // Security: Validate redirect URL to prevent open redirect attacks
      const decodedUrl = decodeURIComponent(redirectUrl);
      if (AuthGuard.isValidRedirectUrl(decodedUrl)) {
        window.location.href = decodedUrl;
      } else {
        console.warn("Invalid redirect URL blocked:", decodedUrl);
        AuthGuard.redirectToDashboard(data.user);
      }
    } else {
      AuthGuard.redirectToDashboard(data.user);
    }
  } catch (error) {
    console.error("Login failed:", error);

    // Show error
    if (errorMessage && errorAlert) {
      errorMessage.textContent = error.message;
      errorAlert.classList.remove("d-none");
    } else if (typeof showToast === "function") {
      showToast(error.message, "error");
    } else {
      alert(error.message);
    }

    // Reset button
    if (loginBtn) {
      const btnText = loginBtn.querySelector(".btn-text");
      const btnLoading = loginBtn.querySelector(".btn-loading");
      if (btnText) btnText.classList.remove("d-none");
      if (btnLoading) btnLoading.classList.add("d-none");
      loginBtn.disabled = false;
    }
  }
}

// ============================================================================
// Logout Handler
// ============================================================================

function handleLogout(event) {
  if (event) event.preventDefault();

  if (confirm("هل أنت متأكد من تسجيل الخروج؟")) {
    AuthService.logout();
  }
}

// ============================================================================
// Initialization
// ============================================================================

async function initAuth() {
  // Install HTTP interceptor
  HttpInterceptor.install();

  // Check authentication on protected pages
  if (!(await AuthGuard.check())) {
    return; // Redirect happened, don't continue
  }

  // Attach login form handler if on login page
  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", handleLogin);

    // Check for expired session message
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("expired") === "true") {
      const expiredAlert = document.getElementById("sessionExpiredAlert");
      if (expiredAlert) {
        expiredAlert.classList.remove("d-none");
      }
    }
  }

  // Attach logout handlers
  document.querySelectorAll('[data-action="logout"], .logout-btn, #logoutBtn').forEach((btn) => {
    btn.addEventListener("click", handleLogout);
  });

  // Update UI with user info if authenticated
  if (AuthStorage.isAuthenticated()) {
    const user = AuthStorage.getUser();
    if (user) {
      updateUserUI(user);
    }
  }

  // Setup token refresh interval (every 25 minutes)
  if (AuthStorage.isAuthenticated()) {
    setInterval(
      () => {
        AuthService.refreshToken();
      },
      25 * 60 * 1000
    );
  }

  console.log("Auth module initialized");
}

/**
 * Update UI elements with user information
 */
function updateUserUI(user) {
  // Update username displays
  document.querySelectorAll(".user-name, #userName").forEach((el) => {
    el.textContent = user.username || user.email;
  });

  // Update role displays
  document.querySelectorAll(".user-role, #userRole").forEach((el) => {
    const roleMap = {
      ADMIN: "مدير النظام",
      MANAGER: "مدير روضة",
      SUPERVISOR: "مشرف",
      PARENT: "ولي أمر",
    };
    el.textContent = roleMap[user.role] || user.role;
  });

  // Show/hide role-specific elements
  document.querySelectorAll("[data-role]").forEach((el) => {
    const allowedRoles = el.dataset.role.split(",");
    if (allowedRoles.includes(user.role)) {
      el.classList.remove("d-none");
    } else {
      el.classList.add("d-none");
    }
  });
}

// ============================================================================
// Export and Initialize
// ============================================================================

// Make classes available globally
window.AuthStorage = AuthStorage;
window.AuthService = AuthService;
window.AuthGuard = AuthGuard;
window.handleLogin = handleLogin;
window.handleLogout = handleLogout;

// ============================================================================
// Authenticated Fetch Helper
// ============================================================================

/**
 * Fetch with automatic authentication headers and 401 handling
 * @param {string} url - The URL to fetch
 * @param {object} options - Fetch options
 * @returns {Promise<Response|null>} - The response or null if redirected
 */
async function fetchWithAuth(url, options = {}) {
  const token = AuthStorage.getToken();
  if (!token) {
    window.location.href = "/login";
    return null;
  }

  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    ...options.headers,
  };

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    // Token expired, redirect to login
    window.location.href = "/login";
    return null;
  }

  if (!response.ok) {
    console.error("API Error:", response.statusText);
    throw new Error(response.statusText);
  }

  return response;
}

// Make fetchWithAuth globally available
window.fetchWithAuth = fetchWithAuth;

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  initAuth().catch((error) => {
    console.error("Auth initialization failed:", error);
  });
});

// Also run immediately if DOM is already loaded
if (document.readyState !== "loading") {
  initAuth().catch((error) => {
    console.error("Auth initialization failed:", error);
  });
}
