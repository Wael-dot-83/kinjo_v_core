/**
 * KinJo Admin Component Library
 * Reusable JavaScript Components for Professional Admin Interface
 *
 * Version: 2.0
 * Date: February 2026
 */

/**
 * Admin Component Library
 * Provides reusable UI components for the admin interface
 */
class AdminComponents {
  constructor(options = {}) {
    this.options = {
      language: options.language || "en",
      direction: options.direction || "ltr",
      ...options,
    };

    this.init();
  }

  init() {
    this.setupEventListeners();
    this.initializeComponents();
  }

  setupEventListeners() {
    // Global event delegation for dynamic components
    document.addEventListener("click", this.handleGlobalClick.bind(this));
    document.addEventListener("keydown", this.handleGlobalKeydown.bind(this));
  }

  initializeComponents() {
    // Initialize existing components on page load
    this.initDropdowns();
    this.initTooltips();
    this.initTabs();
  }

  initModals() {
    // Placeholder: modals are created programmatically via createModal()
  }

  initNotifications() {
    // Placeholder: notifications are shown programmatically via showNotification()
  }

  // ============================================================================
  // BUTTON COMPONENT
  // ============================================================================

  /**
   * Create a standardized admin button
   */
  createButton(options = {}) {
    const {
      text = "",
      variant = "primary",
      size = "md",
      icon = null,
      disabled = false,
      onClick = null,
      type = "button",
      classes = [],
    } = options;

    const button = document.createElement("button");
    button.type = type;
    button.className = `admin-btn admin-btn-${variant} admin-btn-${size} ${classes.join(" ")}`;
    button.disabled = disabled;

    if (icon) {
      const iconElement = document.createElement("span");
      iconElement.className = `admin-btn-icon ${icon}`;
      button.appendChild(iconElement);
    }

    if (text) {
      const textElement = document.createElement("span");
      textElement.textContent = text;
      button.appendChild(textElement);
    }

    if (onClick) {
      button.addEventListener("click", onClick);
    }

    return button;
  }

  // ============================================================================
  // MODAL COMPONENT
  // ============================================================================

  /**
   * Create and manage modal dialogs
   */
  createModal(options = {}) {
    const {
      title = "",
      content = "",
      size = "md",
      closable = true,
      buttons = [],
      onClose = null,
    } = options;

    const titleId = `admin-modal-title-${Date.now()}`;

    // Create modal overlay
    const overlay = document.createElement("div");
    overlay.className = "admin-modal-overlay";
    overlay.setAttribute("role", "presentation");
    overlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1050;
      opacity: 0;
      transition: opacity 0.25s ease;
    `;

    // Create modal dialog with proper ARIA roles
    const modal = document.createElement("div");
    modal.className = `admin-modal admin-modal-${size}`;
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    if (title) modal.setAttribute("aria-labelledby", titleId);
    modal.tabIndex = -1;
    modal.style.cssText = `
      background: white;
      border-radius: 12px;
      box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
      max-width: 90vw;
      max-height: 90vh;
      overflow: hidden;
      transform: scale(0.9);
      transition: transform 0.25s ease;
      display: flex;
      flex-direction: column;
      outline: none;
    `;

    // Modal header
    if (title || closable) {
      const header = document.createElement("div");
      header.className = "admin-modal-header";
      header.style.cssText = `
        padding: 24px;
        border-bottom: 1px solid #e2e8f0;
        display: flex;
        align-items: center;
        justify-content: space-between;
      `;

      if (title) {
        const titleElement = document.createElement("h3");
        titleElement.id = titleId;
        titleElement.className = "admin-modal-title";
        titleElement.textContent = title;
        titleElement.style.cssText = `
          margin: 0;
          font-size: 18px;
          font-weight: 600;
          color: #1f2937;
        `;
        header.appendChild(titleElement);
      }

      if (closable) {
        const closeButton = this.createButton({
          icon: "admin-icon-close",
          variant: "ghost",
          size: "sm",
          onClick: () => this.closeModal(modal),
        });
        closeButton.style.cssText += `
          margin-left: auto;
          width: 32px;
          height: 32px;
        `;
        header.appendChild(closeButton);
      }

      modal.appendChild(header);
    }

    // Modal body
    const body = document.createElement("div");
    body.className = "admin-modal-body";
    body.style.cssText = `
      padding: 24px;
      flex: 1;
      overflow-y: auto;
    `;

    if (typeof content === "string") {
      body.innerHTML = content;
    } else if (content instanceof HTMLElement) {
      body.appendChild(content);
    }

    modal.appendChild(body);

    // Modal footer
    if (buttons.length > 0) {
      const footer = document.createElement("div");
      footer.className = "admin-modal-footer";
      footer.style.cssText = `
        padding: 24px;
        border-top: 1px solid #e2e8f0;
        display: flex;
        gap: 12px;
        justify-content: flex-end;
      `;

      buttons.forEach((buttonOptions) => {
        const button = this.createButton(buttonOptions);
        footer.appendChild(button);
      });

      modal.appendChild(footer);
    }

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Animate in and shift focus into the modal
    requestAnimationFrame(() => {
      overlay.style.opacity = "1";
      modal.style.transform = "scale(1)";
      modal.focus();
    });

    // Focus trap: keep Tab/Shift+Tab inside the modal
    const FOCUSABLE = 'a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])';
    const trapFocus = (e) => {
      if (e.key !== "Tab") return;
      const focusable = Array.from(modal.querySelectorAll(FOCUSABLE));
      if (!focusable.length) { e.preventDefault(); return; }
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey ? document.activeElement === first : document.activeElement === last) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      }
    };
    modal.addEventListener("keydown", trapFocus);

    // Store modal data
    modal._adminModal = { overlay, onClose, trapFocus };

    return modal;
  }

  closeModal(modal) {
    const { overlay, onClose, trapFocus } = modal._adminModal;

    // Remove focus trap listener
    if (trapFocus) modal.removeEventListener("keydown", trapFocus);

    // Animate out
    overlay.style.opacity = "0";
    modal.style.transform = "scale(0.9)";

    setTimeout(() => {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      if (onClose) onClose();
    }, 250);
  }

  // ============================================================================
  // NOTIFICATION SYSTEM
  // ============================================================================

  /**
   * Show toast notifications
   */
  showNotification(options = {}) {
    const {
      type = "info",
      title = "",
      message = "",
      duration = 5000,
      closable = true,
    } = options;

    // Create notification container if it doesn't exist
    let container = document.querySelector(".admin-notifications");
    if (!container) {
      const isRtl = document.documentElement.dir === "rtl";
      container = document.createElement("div");
      container.className = "admin-notifications";
      container.setAttribute("role", "region");
      container.setAttribute("aria-live", "polite");
      container.setAttribute("aria-label", isRtl ? "الإشعارات" : "Notifications");
      container.style.cssText = `
        position: fixed;
        top: 24px;
        ${isRtl ? "left" : "right"}: 24px;
        z-index: 1070;
        display: flex;
        flex-direction: column;
        gap: 12px;
        max-width: 400px;
      `;
      document.body.appendChild(container);
    }

    // Create notification
    const notification = document.createElement("div");
    notification.className = `admin-notification admin-notification-${type}`;
    const isRtl = document.documentElement.dir === "rtl";
    const slideOut = isRtl ? "translateX(-100%)" : "translateX(100%)";
    notification.style.cssText = `
      background: white;
      border-radius: 8px;
      box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
      padding: 16px;
      display: flex;
      align-items: flex-start;
      gap: 12px;
      transform: ${slideOut};
      transition: transform 0.3s ease;
      border-${isRtl ? "right" : "left"}: 4px solid;
    `;

    // Set border color based on type
    const colors = {
      success: "#10b981",
      warning: "#f59e0b",
      error: "#ef4444",
      info: "#0EA5E9",
    };
    notification.style.borderLeftColor = colors[type] || colors.info;

    // Icon
    const icon = document.createElement("div");
    icon.className = `admin-notification-icon`;
    icon.innerHTML = this.getNotificationIcon(type);
    icon.style.cssText = `
      width: 20px;
      height: 20px;
      flex-shrink: 0;
      margin-top: 2px;
    `;
    notification.appendChild(icon);

    // Content
    const content = document.createElement("div");
    content.className = "admin-notification-content";
    content.style.cssText = `flex: 1;`;

    if (title) {
      const titleElement = document.createElement("div");
      titleElement.className = "admin-notification-title";
      titleElement.textContent = title;
      titleElement.style.cssText = `
        font-weight: 600;
        color: #1f2937;
        margin-bottom: 4px;
      `;
      content.appendChild(titleElement);
    }

    if (message) {
      const messageElement = document.createElement("div");
      messageElement.className = "admin-notification-message";
      messageElement.textContent = message;
      messageElement.style.cssText = `
        color: #6b7280;
        font-size: 14px;
      `;
      content.appendChild(messageElement);
    }

    notification.appendChild(content);

    // Close button
    if (closable) {
      const closeButton = this.createButton({
        icon: "admin-icon-close",
        variant: "ghost",
        size: "sm",
        onClick: () => this.removeNotification(notification),
      });
      closeButton.style.cssText += `
        width: 24px;
        height: 24px;
        margin-left: auto;
      `;
      notification.appendChild(closeButton);
    }

    container.appendChild(notification);

    // Animate in
    requestAnimationFrame(() => {
      notification.style.transform = "translateX(0)";
    });

    // Auto remove
    if (duration > 0) {
      setTimeout(() => {
        this.removeNotification(notification);
      }, duration);
    }

    return notification;
  }

  removeNotification(notification) {
    const isRtl = document.documentElement.dir === "rtl";
    notification.style.transform = isRtl ? "translateX(-100%)" : "translateX(100%)";
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, 300);
  }

  getNotificationIcon(type) {
    const icons = {
      success: `<svg fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>`,
      warning: `<svg fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg>`,
      error: `<svg fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path></svg>`,
      info: `<svg fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path></svg>`,
    };
    return icons[type] || icons.info;
  }

  // ============================================================================
  // DROPDOWN COMPONENT
  // ============================================================================

  /**
   * Initialize dropdown components
   */
  initDropdowns() {
    const dropdowns = document.querySelectorAll(".admin-dropdown");
    dropdowns.forEach((dropdown) => {
      this.setupDropdown(dropdown);
    });
  }

  setupDropdown(dropdown) {
    const trigger = dropdown.querySelector(".admin-dropdown-trigger");
    const menu = dropdown.querySelector(".admin-dropdown-menu");

    if (!trigger || !menu) return;

    // Set ARIA attributes
    trigger.setAttribute("aria-haspopup", "true");
    trigger.setAttribute("aria-expanded", "false");

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      this.toggleDropdown(dropdown);
      trigger.setAttribute("aria-expanded", dropdown.classList.contains("open") ? "true" : "false");
    });

    // Outside-click and Escape are handled by the shared global listeners in
    // setupEventListeners / handleGlobalClick / handleGlobalKeydown — no extra
    // document listeners needed here to avoid listener accumulation.
  }

  toggleDropdown(dropdown) {
    const isOpen = dropdown.classList.contains("open");
    this.closeAllDropdowns();

    if (!isOpen) {
      dropdown.classList.add("open");
    }
  }

  closeDropdown(dropdown) {
    dropdown.classList.remove("open");
  }

  closeAllDropdowns() {
    document.querySelectorAll(".admin-dropdown.open").forEach((dropdown) => {
      this.closeDropdown(dropdown);
    });
  }

  // ============================================================================
  // TABS COMPONENT
  // ============================================================================

  /**
   * Initialize tab components
   */
  initTabs() {
    const tabGroups = document.querySelectorAll(".admin-tabs");
    tabGroups.forEach((tabs) => {
      this.setupTabs(tabs);
    });
  }

  setupTabs(tabs) {
    const tabButtons = tabs.querySelectorAll(".admin-tab-button");
    const tabPanels  = tabs.querySelectorAll(".admin-tab-panel");

    // Wire up ARIA roles on first setup
    tabs.setAttribute("role", "tablist");
    tabButtons.forEach((button, index) => {
      const panelId = `admin-tab-panel-${Date.now()}-${index}`;
      const btnId   = `admin-tab-btn-${Date.now()}-${index}`;
      button.setAttribute("role", "tab");
      button.id = btnId;
      button.setAttribute("aria-selected", index === 0 ? "true" : "false");
      if (tabPanels[index]) {
        tabPanels[index].setAttribute("role", "tabpanel");
        tabPanels[index].id = panelId;
        tabPanels[index].setAttribute("aria-labelledby", btnId);
      }
      button.addEventListener("click", () => this.activateTab(tabs, index));
    });
  }

  activateTab(tabs, index) {
    const tabButtons = tabs.querySelectorAll(".admin-tab-button");
    const tabPanels  = tabs.querySelectorAll(".admin-tab-panel");

    tabButtons.forEach((button, i) => {
      button.classList.toggle("active", i === index);
      button.setAttribute("aria-selected", i === index ? "true" : "false");
    });
    tabPanels.forEach((panel, i) => panel.classList.toggle("active", i === index));
  }

  // ============================================================================
  // TOOLTIP COMPONENT
  // ============================================================================

  /**
   * Initialize tooltip components
   */
  initTooltips() {
    const tooltips = document.querySelectorAll("[data-tooltip]");
    tooltips.forEach((element) => {
      this.setupTooltip(element);
    });
  }

  setupTooltip(element) {
    let tooltip = null;

    element.addEventListener("mouseenter", () => {
      tooltip = this.showTooltip(element);
    });

    element.addEventListener("mouseleave", () => {
      if (tooltip) {
        this.hideTooltip(tooltip);
      }
    });
  }

  showTooltip(element) {
    const text = element.getAttribute("data-tooltip");
    if (!text) return null;

    const tooltip = document.createElement("div");
    tooltip.className = "admin-tooltip";
    tooltip.textContent = text;
    tooltip.style.cssText = `
      position: absolute;
      background: #1f2937;
      color: white;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 12px;
      white-space: nowrap;
      z-index: 1070;
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.2s ease;
    `;

    document.body.appendChild(tooltip);

    // Position tooltip
    const rect = element.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();

    let top = rect.top - tooltipRect.height - 8;
    let left = rect.left + rect.width / 2 - tooltipRect.width / 2;

    // Adjust if tooltip goes off screen
    if (top < 8) {
      top = rect.bottom + 8;
    }

    if (left < 8) {
      left = 8;
    } else if (left + tooltipRect.width > window.innerWidth - 8) {
      left = window.innerWidth - tooltipRect.width - 8;
    }

    tooltip.style.top = `${top}px`;
    tooltip.style.left = `${left}px`;
    tooltip.style.opacity = "1";

    return tooltip;
  }

  hideTooltip(tooltip) {
    if (tooltip) {
      tooltip.style.opacity = "0";
      setTimeout(() => {
        if (tooltip.parentNode) {
          tooltip.parentNode.removeChild(tooltip);
        }
      }, 200);
    }
  }

  // ============================================================================
  // UTILITY METHODS
  // ============================================================================

  /**
   * Global click handler for component interactions
   */
  handleGlobalClick(event) {
    // Close dropdowns when clicking outside
    if (!event.target.closest(".admin-dropdown")) {
      this.closeAllDropdowns();
    }

    // Handle modal overlay clicks
    if (event.target.classList.contains("admin-modal-overlay")) {
      const modal = event.target.querySelector(".admin-modal");
      if (modal) {
        this.closeModal(modal);
      }
    }
  }

  /**
   * Global keydown handler for accessibility
   */
  handleGlobalKeydown(event) {
    // Close modals with escape
    if (event.key === "Escape") {
      const openModal = document.querySelector(".admin-modal-overlay");
      if (openModal) {
        const modal = openModal.querySelector(".admin-modal");
        if (modal) {
          this.closeModal(modal);
        }
      }
    }
  }

  /**
   * Debounce utility for performance
   */
  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  /**
   * Throttle utility for performance
   */
  throttle(func, limit) {
    let inThrottle;
    return function () {
      const args = arguments;
      const context = this;
      if (!inThrottle) {
        func.apply(context, args);
        inThrottle = true;
        setTimeout(() => (inThrottle = false), limit);
      }
    };
  }
}

// ============================================================================
// INITIALIZATION
// ============================================================================


// ============================================================================
// GLOBAL showToast FUNCTION
// Provides toast notification functionality for admin templates (wraps
// AdminComponents.showNotification for compatibility with kinjo-app.js style calls)
// ============================================================================

window.showToast = function(message, type) {
  type = type || 'info';
  if (window.AdminComponents && typeof window.AdminComponents.showNotification === 'function') {
    window.AdminComponents.showNotification({ type: type, title: '', message: message });
    return;
  }
  var isRtl = document.documentElement.dir === 'rtl';
  var container = document.querySelector('.admin-notifications');
  if (!container) {
    container = document.createElement('div');
    container.className = 'admin-notifications';
    container.setAttribute('role', 'region');
    container.setAttribute('aria-live', 'polite');
    container.style.cssText = 'position:fixed;top:24px;' + (isRtl ? 'left' : 'right') + ':24px;z-index:1070;display:flex;flex-direction:column;gap:12px;max-width:400px;';
    document.body.appendChild(container);
  }
  var colors = { success: '#10b981', warning: '#f59e0b', error: '#ef4444', info: '#0EA5E9' };
  var notification = document.createElement('div');
  notification.className = 'admin-notification admin-notification-' + type;
  var slideOut = isRtl ? 'translateX(-100%)' : 'translateX(100%)';
  notification.style.cssText = 'background:white;border-radius:8px;box-shadow:0 10px 15px -3px rgba(0,0,0,0.1);padding:16px;transform:' + slideOut + ';transition:transform 0.3s ease;border-' + (isRtl ? 'right' : 'left') + ':4px solid;';
  if (colors[type]) { notification.style.borderLeftColor = colors[type]; }
  var contentDiv = document.createElement('div');
  contentDiv.textContent = message;
  contentDiv.style.cssText = 'flex:1;color:#1f2937;';
  notification.appendChild(contentDiv);
  container.appendChild(notification);
  requestAnimationFrame(function() { notification.style.transform = 'translateX(0)'; });
  setTimeout(function() {
    notification.style.transform = isRtl ? 'translateX(-100%)' : 'translateX(100%)';
    setTimeout(function() { if (notification.parentNode) notification.parentNode.removeChild(notification); }, 300);
  }, 5000);
};


// Initialize components when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  window.AdminComponents = new AdminComponents({
    language: document.documentElement.lang || "en",
    direction: document.documentElement.dir || "ltr",
  });
});

// Export for module usage
if (typeof module !== "undefined" && module.exports) {
  module.exports = AdminComponents;
}

// ============================================================================
// OFFLINE BANNER
// Displays a non-dismissible banner when the browser loses connectivity.
// Retries connectivity automatically every 10 seconds.
// ============================================================================

(function initOfflineBanner() {
  const BANNER_ID = "kinjo-offline-banner";
  const RETRY_INTERVAL_MS = 10_000;

  function _createBanner() {
    const banner = document.createElement("div");
    banner.id = BANNER_ID;
    banner.setAttribute("role", "alert");
    banner.setAttribute("aria-live", "assertive");
    banner.style.cssText = [
      "position:fixed",
      "top:0",
      "left:0",
      "right:0",
      "z-index:99999",
      "background:#b91c1c",
      "color:#fff",
      "text-align:center",
      "padding:10px 16px",
      "font-size:14px",
      "font-weight:600",
      "display:none",
      "align-items:center",
      "justify-content:center",
      "gap:12px",
    ].join(";");

    const msg = document.createElement("span");
    msg.textContent = window.AdminI18n
      ? window.AdminI18n.translate("components.connectivity_error", "Cannot connect to server. Retrying…")
      : "Cannot connect to server. Retrying…";

    const retryBtn = document.createElement("button");
    retryBtn.textContent = window.AdminI18n
      ? window.AdminI18n.translate("components.retry_now", "Retry now")
      : "Retry now";
    retryBtn.style.cssText =
      "background:rgba(255,255,255,0.25);border:1px solid #fff;border-radius:4px;" +
      "color:#fff;cursor:pointer;font-size:13px;padding:2px 10px;";
    retryBtn.addEventListener("click", () => _checkConnectivity());

    banner.appendChild(msg);
    banner.appendChild(retryBtn);
    document.body.prepend(banner);
    return banner;
  }

  function _getBanner() {
    return document.getElementById(BANNER_ID) || _createBanner();
  }

  function _showBanner() {
    const b = _getBanner();
    b.style.display = "flex";
  }

  function _hideBanner() {
    const b = document.getElementById(BANNER_ID);
    if (b) b.style.display = "none";
  }

  function _checkConnectivity() {
    fetch("/api/health", { method: "HEAD", cache: "no-store" })
      .then((r) => {
        if (r.ok) _hideBanner();
        else _showBanner();
      })
      .catch(() => _showBanner());
  }

  window.addEventListener("offline", _showBanner);
  window.addEventListener("online", _checkConnectivity);

  if (!navigator.onLine) {
    _showBanner();
  }

  setInterval(_checkConnectivity, RETRY_INTERVAL_MS);
})();

// ============================================================================
// SESSION TIMEOUT
// After SESSION_TIMEOUT_MINUTES minutes of inactivity, redirect to /login.
// The timeout resets on any mouse/keyboard/touch event.
// ============================================================================

(function initSessionTimeout() {
  // Server-side setting injected via a meta tag:
  //   <meta name="session-timeout-minutes" content="30">
  // Falls back to 30 minutes if not present.
  const metaEl = document.querySelector('meta[name="session-timeout-minutes"]');
  const TIMEOUT_MS = parseInt(metaEl ? metaEl.getAttribute("content") : "30", 10) * 60 * 1000;
  const WARNING_BEFORE_MS = 60_000; // show warning 60 s before logout
  const WARNING_BANNER_ID = "kinjo-session-warning";

  let _logoutTimer = null;
  let _warningTimer = null;

  function _clearTimers() {
    if (_logoutTimer) clearTimeout(_logoutTimer);
    if (_warningTimer) clearTimeout(_warningTimer);
  }

  function _hideWarning() {
    const el = document.getElementById(WARNING_BANNER_ID);
    if (el) el.style.display = "none";
  }

  function _showWarning() {
    let el = document.getElementById(WARNING_BANNER_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = WARNING_BANNER_ID;
      el.setAttribute("role", "alert");
      const _isRtl = document.documentElement.dir === "rtl";
      el.style.cssText = [
        "position:fixed",
        "bottom:24px",
        (_isRtl ? "left:24px" : "right:24px"),
        "z-index:99998",
        "background:#92400e",
        "color:#fff",
        "border-radius:8px",
        "padding:14px 20px",
        "font-size:14px",
        "font-weight:600",
        "box-shadow:0 4px 12px rgba(0,0,0,0.3)",
        "display:flex",
        "align-items:center",
        "gap:12px",
      ].join(";");

      const msg = document.createElement("span");
      msg.textContent = window.AdminI18n
        ? window.AdminI18n.translate("components.session_warning", "Your session will expire in 1 minute due to inactivity.")
        : "Your session will expire in 1 minute due to inactivity.";

      const stayBtn = document.createElement("button");
      stayBtn.textContent = window.AdminI18n
        ? window.AdminI18n.translate("components.stay_logged_in", "Stay logged in")
        : "Stay logged in";
      stayBtn.style.cssText =
        "background:rgba(255,255,255,0.2);border:1px solid #fff;border-radius:4px;" +
        "color:#fff;cursor:pointer;font-size:13px;padding:4px 12px;";
      stayBtn.addEventListener("click", () => {
        _resetTimer();
        _hideWarning();
      });

      el.appendChild(msg);
      el.appendChild(stayBtn);
      document.body.appendChild(el);
    }
    el.style.display = "flex";
  }

  async function _doLogout() {
    _hideWarning();
    sessionStorage.setItem("kinjo_session_expired", "1");
    try {
      if (window.AuthService && typeof AuthService.logout === "function") {
        await AuthService.logout();
      } else {
        await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => {});
      }
    } catch (e) {
      // best-effort: proceed regardless
    }
    window.location.href = "/login?reason=timeout";
  }

  function _resetTimer() {
    _clearTimers();
    _warningTimer = setTimeout(_showWarning, TIMEOUT_MS - WARNING_BEFORE_MS);
    _logoutTimer = setTimeout(_doLogout, TIMEOUT_MS);
  }

  // Throttle activity handling: high-frequency events (mousemove, scroll) would
  // otherwise clear and recreate timers hundreds of times per second.
  let _lastActivity = 0;
  const _ACTIVITY_THROTTLE_MS = 1000;
  function _onActivity() {
    const now = Date.now();
    if (now - _lastActivity < _ACTIVITY_THROTTLE_MS) return;
    _lastActivity = now;
    _resetTimer();
  }

  const ACTIVITY_EVENTS = ["mousedown", "mousemove", "keydown", "touchstart", "scroll"];
  ACTIVITY_EVENTS.forEach((evt) => {
    document.addEventListener(evt, _onActivity, { passive: true });
  });

  _resetTimer();

  // Show "session expired" message if we were redirected here after timeout.
  if (sessionStorage.getItem("kinjo_session_expired") === "1") {
    sessionStorage.removeItem("kinjo_session_expired");
    const notice = document.createElement("div");
    notice.textContent = window.AdminI18n
      ? window.AdminI18n.translate("components.session_expired", "Your session expired due to inactivity. Please sign in again.")
      : "Your session expired due to inactivity. Please sign in again.";
    notice.style.cssText =
      "position:fixed;top:0;left:0;right:0;z-index:99999;background:#4F46E5;" +
      "color:#fff;text-align:center;padding:10px;font-size:14px;font-weight:600;";
    document.body.prepend(notice);
    setTimeout(() => notice.remove(), 5000);
  }
})()