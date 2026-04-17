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
    this.initModals();
    this.initTooltips();
    this.initTabs();
    this.initNotifications();
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

    // Create modal overlay
    const overlay = document.createElement("div");
    overlay.className = "admin-modal-overlay";
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

    // Create modal dialog
    const modal = document.createElement("div");
    modal.className = `admin-modal admin-modal-${size}`;
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

    // Animate in
    requestAnimationFrame(() => {
      overlay.style.opacity = "1";
      modal.style.transform = "scale(1)";
    });

    // Store modal data
    modal._adminModal = {
      overlay,
      onClose,
    };

    return modal;
  }

  closeModal(modal) {
    const { overlay, onClose } = modal._adminModal;

    // Animate out
    overlay.style.opacity = "0";
    modal.style.transform = "scale(0.9)";

    setTimeout(() => {
      if (overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
      if (onClose) {
        onClose();
      }
    }, 250);
  }

  // ============================================================================
  // NOTIFICATION SYSTEM
  // ============================================================================

  /**
   * Show toast notifications
   */
  showNotification(options = {}) {
    const { type = "info", title = "", message = "", duration = 5000, closable = true } = options;

    // Create notification container if it doesn't exist
    let container = document.querySelector(".admin-notifications");
    if (!container) {
      container = document.createElement("div");
      container.className = "admin-notifications";
      container.style.cssText = `
        position: fixed;
        top: 24px;
        right: 24px;
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
    notification.style.cssText = `
      background: white;
      border-radius: 8px;
      box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
      padding: 16px;
      display: flex;
      align-items: flex-start;
      gap: 12px;
      transform: translateX(100%);
      transition: transform 0.3s ease;
      border-left: 4px solid;
    `;

    // Set border color based on type
    const colors = {
      success: "#10b981",
      warning: "#f59e0b",
      error: "#ef4444",
      info: "#3b82f6",
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
    notification.style.transform = "translateX(100%)";
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

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      this.toggleDropdown(dropdown);
    });

    // Close on outside click
    document.addEventListener("click", (e) => {
      if (!dropdown.contains(e.target)) {
        this.closeDropdown(dropdown);
      }
    });

    // Close on escape
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        this.closeDropdown(dropdown);
      }
    });
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

    tabButtons.forEach((button, index) => {
      button.addEventListener("click", () => {
        this.activateTab(tabs, index);
      });
    });
  }

  activateTab(tabs, index) {
    const tabButtons = tabs.querySelectorAll(".admin-tab-button");
    const tabPanels = tabs.querySelectorAll(".admin-tab-panel");

    // Deactivate all tabs
    tabButtons.forEach((button) => button.classList.remove("active"));
    tabPanels.forEach((panel) => panel.classList.remove("active"));

    // Activate selected tab
    tabButtons[index].classList.add("active");
    tabPanels[index].classList.add("active");
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
