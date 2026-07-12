/**
 * KinJo Admin Internationalization Framework
 * Bilingual Support for Arabic RTL and English LTR Interfaces
 *
 * Version: 2.0
 * Date: February 2026
 */

/**
 * Admin Internationalization Manager
 * Handles language switching, translations, and RTL/LTR layout management
 */
class AdminI18n {
  constructor(options = {}) {
    this.options = {
      defaultLanguage: "ar",
      supportedLanguages: ["ar", "en"],
      persistLanguage: true,
      ...options,
    };

    this.currentLanguage = this.getSavedLanguage() || this.options.defaultLanguage;
    this.translations = {};
    this.isLoading = false;
    this.literalTranslations = { en: {} };
    this.literalTranslationEntries = { en: [] };
    this.literalObserver = null;
    this.isApplyingLiteral = false;
    this.languageApiStateKey = "kinjo_lang_api_state";
    this.serverLanguageApiState = this.resolveServerLanguageApiState();
    this.literalCacheVersion = "2026-02-18-v2";
    this.literalCacheKey = `kinjo_admin_literal_pairs_${this.literalCacheVersion}`;
    this.literalTranslationsReady = false;
    this.literalBuildPromise = null;
    this.literalPreloadScheduled = false;

    this.init();
  }

  init() {
    this.setupLanguageSwitcher();
    this.setupEventListeners();
    this.loadTranslations()
      .then(() => this.loadServerLanguagePreference())
      .then((serverLanguage) => {
        if (serverLanguage) {
          this.currentLanguage = serverLanguage;
          this.saveLanguage(serverLanguage);
        }
      })
      .then(() => this.applyLanguage(this.currentLanguage))
      .catch((error) => {
        console.error("Failed to initialize admin i18n:", error);
        this.applyLanguage(this.currentLanguage);
      });
  }

  // ============================================================================
  // LANGUAGE MANAGEMENT
  // ============================================================================

  /**
   * Load translation files for all supported languages
   */
  async loadTranslations() {
    this.isLoading = true;

    try {
      // Load all supported languages in parallel
      const loadPromises = this.options.supportedLanguages.map(async (lang) => {
        try {
          const response = await fetch(`/static/i18n/admin_${lang}.json`, { cache: "no-cache" });
          if (response.ok) {
            this.translations[lang] = await response.json();
            // Signals "real JSON catalog loaded" — consumers (e.g. the
            // dashboard re-render canary) must check this, not key presence,
            // because the inline defaults also contain most keys.
            this.loadedFromFiles = true;
          } else {
            console.warn(`Translation file for ${lang} not found — keeping defaults`);
            // Do NOT overwrite defaults with {} — leave whatever was set already
          }
        } catch (error) {
          console.error(`Failed to load translations for ${lang}:`, error);
          // Do NOT overwrite defaults with {} — leave whatever was set already
        }
      });

      await Promise.all(loadPromises);
    } catch (error) {
      console.error("Failed to load translations:", error);
    } finally {
      this.isLoading = false;
    }
  }

  resolveServerLanguageApiState() {
    try {
      const value = sessionStorage.getItem(this.languageApiStateKey);
      if (value === "available" || value === "missing") {
        return value;
      }
    } catch (_error) {
      // Ignore storage access failures.
    }
    return "unknown";
  }

  setServerLanguageApiState(state) {
    if (state !== "available" && state !== "missing") {
      return;
    }
    this.serverLanguageApiState = state;
    try {
      sessionStorage.setItem(this.languageApiStateKey, state);
    } catch (_error) {
      // Ignore storage access failures.
    }
  }

  async loadServerLanguagePreference() {
    try {
      if (this.serverLanguageApiState === "missing") {
        return null;
      }
      const response = await fetch("/api/users/me/language", {
        method: "GET",
        credentials: "same-origin",
      });
      if (response.status === 404) {
        this.setServerLanguageApiState("missing");
        return null;
      }
      if (!response.ok) {
        return null;
      }
      this.setServerLanguageApiState("available");
      const data = await response.json();
      const userLang = typeof data?.user_lang === "string" ? data.user_lang.toLowerCase() : "";
      return this.options.supportedLanguages.includes(userLang) ? userLang : null;
    } catch (_error) {
      return null;
    }
  }

  async persistServerLanguagePreference(language) {
    try {
      if (this.serverLanguageApiState === "missing") {
        return;
      }
      const csrfToken =
        (window.AuthStorage && AuthStorage.getCookie("kinjo_csrf_token")) ||
        document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
        "";
      const headers = { "Content-Type": "application/json" };
      if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
      }
      const response = await fetch("/api/users/me/language", {
        method: "PUT",
        headers,
        credentials: "same-origin",
        keepalive: true,
        body: JSON.stringify({ user_lang: language }),
      });
      if (response.status === 404) {
        this.setServerLanguageApiState("missing");
        return;
      }
      if (response.ok) {
        this.setServerLanguageApiState("available");
      }
    } catch (_error) {
      // Keep local preference if server persistence fails.
    }
  }

  /**
   * Switch to a different language
   */
  async switchLanguage(language) {
    if (!this.options.supportedLanguages.includes(language)) {
      console.error(`Unsupported language: ${language}`);
      return false;
    }

    if (language === this.currentLanguage) return true;

    try {
      this.currentLanguage = language;
      this.saveLanguage(language);
      // Await server persistence so the preference is saved before the page
      // reloads — without await the reload can outrace the PUT request.
      await this.persistServerLanguagePreference(language);
      window.location.reload();
      return true;
    } catch (error) {
      console.error("Failed to switch language:", error);
      return false;
    }
  }

  /**
   * Apply language settings to the interface
   */
  async applyLanguage(language) {
    const direction = this.getDirection(language);

    // Update HTML attributes
    document.documentElement.lang = language;
    document.documentElement.dir = direction;
    document.documentElement.classList.toggle("rtl", direction === "rtl");
    document.documentElement.classList.toggle("ltr", direction === "ltr");

    // Update meta tags
    this.updateMetaTags(language);

    // Apply translations to all translatable elements
    this.translatePage(language);
    this.translateLiteralText();
    this.startLiteralObserver();

    // Update CSS custom properties for RTL/LTR
    this.updateCSSDirection(direction);
    this.updateBootstrapDirection(direction);

    // Update language switcher
    this.updateLanguageSwitcher(language);

    if (language === "en") {
      this.scheduleLiteralTranslationBuild();
    }
  }

  /**
   * Get text direction for a language
   */
  getDirection(language) {
    const rtlLanguages = ["ar", "he", "fa", "ur"];
    return rtlLanguages.includes(language) ? "rtl" : "ltr";
  }

  /**
   * Update meta tags for SEO and accessibility
   */
  updateMetaTags(_language) {
    const title = this.translate("page.title", "KinJo Admin");
    const description = this.translate(
      "page.description",
      "Professional Kindergarten Management System"
    );

    // Update title
    document.title = title;

    // Update meta description
    let metaDesc = document.querySelector('meta[name="description"]');
    if (!metaDesc) {
      metaDesc = document.createElement("meta");
      metaDesc.name = "description";
      document.head.appendChild(metaDesc);
    }
    metaDesc.content = description;

    // Update Open Graph tags
    this.updateOGTags(title, description);
  }

  /**
   * Update Open Graph tags for social sharing
   */
  updateOGTags(title, description) {
    const ogTags = [
      { property: "og:title", content: title },
      { property: "og:description", content: description },
      {
        property: "og:locale",
        content: this.currentLanguage === "ar" ? "ar_JO" : "en_US",
      },
    ];

    ogTags.forEach(({ property, content }) => {
      let tag = document.querySelector(`meta[property="${property}"]`);
      if (!tag) {
        tag = document.createElement("meta");
        tag.setAttribute("property", property);
        document.head.appendChild(tag);
      }
      tag.content = content;
    });
  }

  /**
   * Update CSS custom properties for direction-specific styling
   */
  updateCSSDirection(direction) {
    const root = document.documentElement;
    root.style.setProperty("--admin-direction", direction);

    // Update direction-specific properties
    if (direction === "rtl") {
      root.style.setProperty("--admin-text-align-start", "right");
      root.style.setProperty("--admin-text-align-end", "left");
      root.style.setProperty("--admin-float-start", "right");
      root.style.setProperty("--admin-float-end", "left");
      root.style.setProperty("--admin-margin-start", "margin-right");
      root.style.setProperty("--admin-margin-end", "margin-left");
      root.style.setProperty("--admin-padding-start", "padding-right");
      root.style.setProperty("--admin-padding-end", "padding-left");
    } else {
      root.style.setProperty("--admin-text-align-start", "left");
      root.style.setProperty("--admin-text-align-end", "right");
      root.style.setProperty("--admin-float-start", "left");
      root.style.setProperty("--admin-float-end", "right");
      root.style.setProperty("--admin-margin-start", "margin-left");
      root.style.setProperty("--admin-margin-end", "margin-right");
      root.style.setProperty("--admin-padding-start", "padding-left");
      root.style.setProperty("--admin-padding-end", "padding-right");
    }
  }

  // ============================================================================
  // TRANSLATION METHODS
  // ============================================================================

  /**
   * Translate a key with optional fallback
   */
  translate(key, fallback = "", params = {}) {
    if (!this.translations[this.currentLanguage]) {
      return fallback || key;
    }

    let translation = this.getNestedValue(this.translations[this.currentLanguage], key);

    if (!translation) {
      // Try fallback language if available
      if (
        this.options.defaultLanguage !== this.currentLanguage &&
        this.translations[this.options.defaultLanguage]
      ) {
        translation = this.getNestedValue(this.translations[this.options.defaultLanguage], key);
      }

      if (!translation) {
        console.warn(`Translation missing for key: ${key}`);
        // GWS A.1.4-022: show the language-fallback banner once if a key is missing
        const banner = document.getElementById("langFallbackBanner");
        if (banner && banner.classList.contains("d-none")) {
          banner.classList.remove("d-none");
        }
        return fallback || key;
      }
    }

    // Replace parameters
    return this.interpolateParams(translation, params);
  }

  /**
   * Get nested value from object using dot notation
   */
  getNestedValue(obj, path) {
    return path.split(".").reduce((current, key) => {
      return current && current[key] !== undefined ? current[key] : undefined;
    }, obj);
  }

  /**
   * Interpolate parameters in translation strings
   */
  interpolateParams(text, params) {
    return text.replace(/\{\{(\w+)\}\}/g, (match, key) => {
      return params[key] !== undefined ? params[key] : match;
    });
  }

  /**
   * Translate all elements with data-i18n attributes.
   * Uses each element's existing text as fallback so missing keys never
   * overwrite visible content with a raw translation key string.
   */
  translatePage() {
    const elements = document.querySelectorAll("[data-i18n]");
    elements.forEach((element) => {
      const key = element.getAttribute("data-i18n");
      const params = this.parseDataParams(element, "data-i18n-");

      if (key) {
        // Use the element's existing visible text as the fallback so that
        // a missing key preserves the server-rendered content instead of
        // writing the raw key string (e.g. "dashboard.total_kindergartens").
        let existingText;
        if (element.tagName === "INPUT" && element.type === "placeholder") {
          existingText = element.placeholder || "";
        } else if (element.tagName === "IMG") {
          existingText = element.alt || "";
        } else {
          existingText = element.textContent.trim();
        }

        const translation = this.translate(key, existingText, params);
        // Never apply the raw key — only apply when we have a real translation
        if (translation && translation !== key) {
          if (element.tagName === "INPUT" && element.type === "placeholder") {
            element.placeholder = translation;
          } else if (element.tagName === "IMG") {
            element.alt = translation;
          } else {
            element.textContent = translation;
          }
        }
      }
    });

    // Translate aria-labels
    const ariaElements = document.querySelectorAll("[data-i18n-aria]");
    ariaElements.forEach((element) => {
      const key = element.getAttribute("data-i18n-aria");
      const params = this.parseDataParams(element, "data-i18n-aria-");

      if (key) {
        const existingAria = element.getAttribute("aria-label") || "";
        const translation = this.translate(key, existingAria, params);
        if (translation && translation !== key) {
          element.setAttribute("aria-label", translation);
        }
      }
    });
  }

  /**
   * Parse data parameters from element attributes
   */
  parseDataParams(element, prefix) {
    const params = {};
    const attributes = element.attributes;

    for (let i = 0; i < attributes.length; i++) {
      const attr = attributes[i];
      if (attr.name.startsWith(prefix)) {
        const paramName = attr.name.substring(prefix.length);
        params[paramName] = attr.value;
      }
    }

    return params;
  }

  normalizeLiteralText(value) {
    if (typeof value !== "string") {
      return "";
    }
    return value.replace(/\s+/g, " ").trim();
  }

  containsArabic(text) {
    return /[\u0600-\u06FF]/.test(text || "");
  }

  flattenTranslationMap(source, parentKey = "", output = {}) {
    if (typeof source === "string") {
      if (parentKey) {
        output[parentKey] = source;
      }
      return output;
    }
    if (!source || typeof source !== "object") {
      return output;
    }
    Object.entries(source).forEach(([key, value]) => {
      const nextKey = parentKey ? `${parentKey}.${key}` : key;
      if (typeof value === "string") {
        output[nextKey] = value;
        return;
      }
      this.flattenTranslationMap(value, nextKey, output);
    });
    return output;
  }

  addLiteralTranslationPair(arText, enText) {
    const normalizedAr = this.normalizeLiteralText(arText);
    const normalizedEn = this.normalizeLiteralText(enText);
    if (!normalizedAr || !normalizedEn || !this.containsArabic(normalizedAr)) {
      return;
    }
    this.literalTranslations.en[normalizedAr] = normalizedEn;
    if (!normalizedAr.endsWith(":")) {
      this.literalTranslations.en[`${normalizedAr}:`] = normalizedEn.endsWith(":")
        ? normalizedEn
        : `${normalizedEn}:`;
    } else {
      const arNoColon = normalizedAr.slice(0, -1).trim();
      const enNoColon = normalizedEn.endsWith(":")
        ? normalizedEn.slice(0, -1).trim()
        : normalizedEn;
      if (arNoColon) {
        this.literalTranslations.en[arNoColon] = enNoColon;
      }
    }
  }

  updateBootstrapDirection(direction) {
    const bootstrapLink = document.getElementById("bootstrapCss");
    if (!bootstrapLink) {
      return;
    }

    const currentHref = bootstrapLink.getAttribute("href") || "";
    const rtlHref =
      bootstrapLink.dataset.rtlHref ||
      (currentHref.includes("bootstrap.rtl.min.css")
        ? currentHref
        : currentHref.replace("bootstrap.min.css", "bootstrap.rtl.min.css"));
    const ltrHref =
      bootstrapLink.dataset.ltrHref ||
      (rtlHref.includes("bootstrap.rtl.min.css")
        ? rtlHref.replace("bootstrap.rtl.min.css", "bootstrap.min.css")
        : rtlHref);

    bootstrapLink.dataset.rtlHref = rtlHref;
    bootstrapLink.dataset.ltrHref = ltrHref;
    bootstrapLink.setAttribute("href", direction === "rtl" ? rtlHref : ltrHref);
    const rtlIntegrity = bootstrapLink.dataset.rtlIntegrity || "";
    const ltrIntegrity = bootstrapLink.dataset.ltrIntegrity || "";
    const targetIntegrity = direction === "rtl" ? rtlIntegrity : ltrIntegrity;
    if (targetIntegrity) {
      bootstrapLink.setAttribute("integrity", targetIntegrity);
    }
  }

  ingestCatalogLiteralPairs(arCatalog, enCatalog) {
    const flatAr = this.flattenTranslationMap(arCatalog);
    const flatEn = this.flattenTranslationMap(enCatalog);
    Object.keys(flatAr).forEach((key) => {
      this.addLiteralTranslationPair(flatAr[key], flatEn[key] || "");
    });
  }

  restoreLiteralPairsCache() {
    try {
      const raw = sessionStorage.getItem(this.literalCacheKey);
      if (!raw) {
        return false;
      }
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object" || !parsed.en || typeof parsed.en !== "object") {
        return false;
      }
      this.literalTranslations.en = parsed.en;
      this.literalTranslationEntries = {
        en: Object.entries(this.literalTranslations.en).sort((a, b) => b[0].length - a[0].length),
      };
      this.literalTranslationsReady = true;
      return true;
    } catch (_error) {
      return false;
    }
  }

  persistLiteralPairsCache() {
    try {
      sessionStorage.setItem(
        this.literalCacheKey,
        JSON.stringify({ en: this.literalTranslations.en })
      );
    } catch (_error) {
      // Ignore cache persistence failures (quota/security).
    }
  }

  async loadJsonCatalog(path) {
    try {
      const response = await fetch(path, { cache: "force-cache" });
      if (!response.ok) {
        return {};
      }
      return (await response.json()) || {};
    } catch (_error) {
      return {};
    }
  }

  decodeJsStringToken(token) {
    if (!token || token.length < 2) {
      return "";
    }
    let value = token.slice(1, -1);
    value = value
      .replace(/\\'/g, "'")
      .replace(/\\"/g, '"')
      .replace(/\\`/g, "`")
      .replace(/\\n/g, " ")
      .replace(/\\r/g, " ")
      .replace(/\\t/g, " ");
    return this.normalizeLiteralText(value);
  }

  ingestLiteralPairsFromSource(source) {
    if (!source) {
      return;
    }
    const helperPattern =
      /(?:appText|dashboardText|dashboardInlineText|attendanceText|enrollmentText|kindergartenText|kpiText|parentText|supervisorText|enrollmentViewText|managerText|adminText)\s*\(\s*(?:'[^']*'|"[^"]*"|`[^`]*`)\s*,\s*('(?:\\.|[^'])*'|"(?:\\.|[^"])*"|`(?:\\.|[^`])*`)\s*,\s*('(?:\\.|[^'])*'|"(?:\\.|[^"])*"|`(?:\\.|[^`])*`)/gms;
    let match = helperPattern.exec(source);
    while (match) {
      const arText = this.decodeJsStringToken(match[1]);
      const enText = this.decodeJsStringToken(match[2]);
      this.addLiteralTranslationPair(arText, enText);
      match = helperPattern.exec(source);
    }
  }

  async loadScriptLiteralPairs() {
    const srcSet = new Set();
    document.querySelectorAll("script[src]").forEach((script) => {
      const src = script.getAttribute("src");
      if (!src || !src.startsWith("/static/js/")) {
        return;
      }
      srcSet.add(src.split("?")[0]);
    });

    await Promise.all(
      [...srcSet].map(async (src) => {
        try {
          const response = await fetch(src, { cache: "force-cache" });
          if (!response.ok) {
            return;
          }
          const content = await response.text();
          this.ingestLiteralPairsFromSource(content);
        } catch (_error) {
          // Ignore source-harvest failures to avoid blocking UI startup.
        }
      })
    );

    document.querySelectorAll("script:not([src])").forEach((script) => {
      this.ingestLiteralPairsFromSource(script.textContent || "");
    });
  }

  async buildLiteralTranslations() {
    if (this.literalTranslationsReady) {
      return;
    }
    if (this.literalBuildPromise) {
      return this.literalBuildPromise;
    }

    this.literalBuildPromise = (async () => {
      if (this.restoreLiteralPairsCache()) {
        return;
      }
      this.literalTranslations = { en: {} };
      this.ingestCatalogLiteralPairs(this.translations.ar || {}, this.translations.en || {});

      const [appAr, appEn, literalOverrides, literalQualityOverrides] = await Promise.all([
        this.loadJsonCatalog("/static/i18n/app_ar.json"),
        this.loadJsonCatalog("/static/i18n/app_en.json"),
        this.loadJsonCatalog("/static/i18n/literal_en_overrides.json"),
        this.loadJsonCatalog("/static/i18n/literal_en_quality_overrides.json"),
      ]);
      this.ingestCatalogLiteralPairs(appAr, appEn);
      Object.entries(literalOverrides || {}).forEach(([arText, enText]) => {
        this.addLiteralTranslationPair(arText, enText);
      });
      Object.entries(literalQualityOverrides || {}).forEach(([arText, enText]) => {
        this.addLiteralTranslationPair(arText, enText);
      });

      await this.loadScriptLiteralPairs();

      this.literalTranslationEntries = {
        en: Object.entries(this.literalTranslations.en).sort((a, b) => b[0].length - a[0].length),
      };
      this.literalTranslationsReady = true;
      this.persistLiteralPairsCache();
    })();

    try {
      await this.literalBuildPromise;
    } finally {
      this.literalBuildPromise = null;
    }
  }

  scheduleLiteralTranslationBuild() {
    if (this.literalTranslationsReady || this.literalPreloadScheduled) {
      return;
    }

    this.literalPreloadScheduled = true;
    const run = () => {
      this.literalPreloadScheduled = false;
      this.buildLiteralTranslations()
        .then(() => {
          if (this.currentLanguage === "en") {
            this.translateLiteralText();
          }
        })
        .catch(() => {
          // Ignore background literal preload failures.
        });
    };

    if (typeof window.requestIdleCallback === "function") {
      window.requestIdleCallback(run, { timeout: 800 });
      return;
    }
    window.setTimeout(run, 0);
  }

  replaceLiteralSegments(value) {
    if (!value || this.currentLanguage !== "en") {
      return value;
    }
    const entries = this.literalTranslationEntries.en || [];
    let output = String(value);
    entries.forEach(([arText, enText]) => {
      output = output.split(arText).join(enText);
    });
    return output;
  }

  translateLiteralText() {
    if (this.currentLanguage !== "en" || this.isApplyingLiteral || !document.body) {
      return;
    }
    this.isApplyingLiteral = true;
    try {
      const blockedTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT"]);
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => {
          const parentTag = node.parentElement?.tagName;
          if (!node.nodeValue || !parentTag || blockedTags.has(parentTag)) {
            return NodeFilter.FILTER_REJECT;
          }
          if (node.parentElement?.closest("[data-i18n]")) {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        },
      });
      const textNodes = [];
      let current = walker.nextNode();
      while (current) {
        textNodes.push(current);
        current = walker.nextNode();
      }
      textNodes.forEach((node) => {
        const translated = this.replaceLiteralSegments(node.nodeValue);
        if (translated !== node.nodeValue) {
          node.nodeValue = translated;
        }
      });

      ["placeholder", "title", "aria-label"].forEach((attr) => {
        document.querySelectorAll(`[${attr}]`).forEach((element) => {
          if (element.hasAttribute(`data-i18n-${attr === "aria-label" ? "aria" : attr}`)) {
            return;
          }
          const currentValue = element.getAttribute(attr);
          const translated = this.replaceLiteralSegments(currentValue);
          if (translated && translated !== currentValue) {
            element.setAttribute(attr, translated);
          }
        });
      });

      if (document.title) {
        document.title = this.replaceLiteralSegments(document.title);
      }
    } finally {
      this.isApplyingLiteral = false;
    }
  }

  startLiteralObserver() {
    if (this.literalObserver) {
      this.literalObserver.disconnect();
      this.literalObserver = null;
    }
    if (this.currentLanguage !== "en" || !document.body) {
      return;
    }
    this.literalObserver = new MutationObserver(() => {
      this.translateLiteralText();
    });
    this.literalObserver.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label"],
    });
  }

  // ============================================================================
  // LANGUAGE SWITCHER
  // ============================================================================

  /**
   * Setup language switcher component
   */
  setupLanguageSwitcher() {
    const switcher = document.querySelector(".language-switcher");
    if (!switcher) return;

    // Options must go inside .dropdown-menu so they stay hidden until opened
    const menu = switcher.querySelector(".dropdown-menu");
    if (!menu) return;

    menu.innerHTML = ""; // clear before populating to prevent duplicates on re-init

    const languages = [
      { code: "en", name: "English",  nameAr: "الإنجليزية", flag: "🇬🇧" },
      { code: "ar", name: "العربية",  nameAr: "العربية",    flag: "🇯🇴" },
    ];

    languages.forEach((lang) => {
      // The current language is already shown in the button trigger (server-rendered).
      // Adding it to the dropdown too would duplicate it visually.
      if (lang.code === this.currentLanguage) return;

      const option = document.createElement("button");
      option.className = "admin-language-option";
      option.setAttribute("data-language", lang.code);
      option.setAttribute("type", "button");

      const displayName = this.currentLanguage === "ar" ? lang.nameAr : lang.name;
      const flagSpan = document.createElement("span");
      flagSpan.className = "admin-language-flag";
      flagSpan.setAttribute("aria-hidden", "true");
      flagSpan.textContent = lang.flag;

      const nameSpan = document.createElement("span");
      nameSpan.className = "admin-language-name";
      nameSpan.textContent = displayName;

      option.appendChild(flagSpan);
      option.appendChild(nameSpan);

      option.addEventListener("click", () => {
        this.switchLanguage(lang.code);
      });

      menu.appendChild(option);
    });
  }

  /**
   * Update language switcher active state
   */
  updateLanguageSwitcher(language) {
    const options = document.querySelectorAll(".admin-language-option");
    options.forEach((option) => {
      const optionLang = option.getAttribute("data-language");
      option.classList.toggle("active", optionLang === language);
    });
  }

  // ============================================================================
  // PERSISTENCE
  // ============================================================================

  /**
   * Save language preference
   */
  saveLanguage(language) {
    if (this.options.persistLanguage) {
      try {
        localStorage.setItem("admin_language", language);
        localStorage.setItem("kinjo_lang", language);
        document.cookie = `kinjo_lang=${language}; path=/; max-age=31536000; SameSite=Lax`;
      } catch (error) {
        console.warn("Failed to save language preference:", error);
      }
    }
  }

  /**
   * Get saved language preference
   */
  getSavedLanguage() {
    if (this.options.persistLanguage) {
      try {
        const saved = localStorage.getItem("admin_language") || localStorage.getItem("kinjo_lang");
        if (this.options.supportedLanguages.includes(saved)) {
          return saved;
        }
        const cookieMatch = document.cookie.match(/(?:^|;\s*)kinjo_lang=(ar|en)(?:;|$)/i);
        const cookieLang = cookieMatch ? cookieMatch[1].toLowerCase() : "";
        if (this.options.supportedLanguages.includes(cookieLang)) {
          return cookieLang;
        }
        return null;
      } catch (error) {
        return null;
      }
    }
    return null;
  }

  // ============================================================================
  // UTILITIES
  // ============================================================================

  /**
   * Setup event listeners
   */
  setupEventListeners() {
    // Listen for language change events from other components
    window.addEventListener("languageChangeRequest", (event) => {
      const { language } = event.detail;
      this.switchLanguage(language);
    });
  }

  /**
   * Format numbers according to language conventions
   */
  formatNumber(number, options = {}) {
    const locale = this.currentLanguage === "ar" ? "ar-JO" : "en-US";
    return new Intl.NumberFormat(locale, options).format(number);
  }

  /**
   * Format dates according to language conventions
   */
  formatDate(date, options = {}) {
    const locale = this.currentLanguage === "ar" ? "ar-JO" : "en-US";
    return new Intl.DateTimeFormat(locale, options).format(new Date(date));
  }

  /**
   * Format currency according to language conventions
   */
  formatCurrency(amount, currency = "JOD") {
    const locale = this.currentLanguage === "ar" ? "ar-JO" : "en-US";
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency,
    }).format(amount);
  }

  /**
   * Get current language info
   */
  getCurrentLanguage() {
    return {
      code: this.currentLanguage,
      direction: this.getDirection(this.currentLanguage),
      name: this.translate(`language.${this.currentLanguage}`, this.currentLanguage.toUpperCase()),
    };
  }

  /**
   * Check if current language is RTL
   */
  isRTL() {
    return this.getDirection(this.currentLanguage) === "rtl";
  }

  /**
   * Get available languages
   */
  getAvailableLanguages() {
    return this.options.supportedLanguages.map((code) => ({
      code,
      name: this.translate(`language.${code}`, code.toUpperCase()),
      direction: this.getDirection(code),
    }));
  }
}

// ============================================================================
// DEFAULT TRANSLATIONS
// ============================================================================

// English translations (fallback) — must cover every key used in admin_dashboard.html
// and admin_dashboard.js so pages render correctly even when JSON files fail to load.
const defaultEnglishTranslations = {
  language: {
    en: "English",
    ar: "Arabic",
  },
  page: {
    title: "KinJo Admin",
    description: "Professional Kindergarten Management System",
  },
  nav: {
    brand: "KinJo",
    dashboard: "Dashboard",
    users: "Users",
    communication: "Communication",
    analytics: "Analytics",
    governance: "Governance",
    data: "Data Management",
    security: "Security",
  },
  a11y: {
    skip_nav: "Skip to navigation"
  },
  components: {
    error_title: "Error",
    background_error: "A background error occurred"
  },
  common: {
    save: "Save",
    cancel: "Cancel",
    delete: "Delete",
    edit: "Edit",
    add: "Add",
    search: "Search",
    filter: "Filter",
    export: "Export",
    import: "Import",
    loading: "Loading...",
    no_data: "No data available",
    confirm: "Confirm",
    yes: "Yes",
    no: "No",
    refresh: "Refresh",
    error: "Error",
    just_now: "just now",
    minutes_ago: "minutes ago",
    hours_ago: "hours ago",
    days_ago: "days ago",
    locale: "en-US",
  },
  dashboard: {
    title: "Dashboard",
    subtitle: "Monitor system performance and manage operations",
    welcome: "Welcome to KinJo Admin",
    total_users: "Total Users",
    active_users: "Active Users",
    total_kindergartens: "Total Kindergartens",
    active_kindergartens: "Active Kindergartens",
    total_submissions: "Total Submissions",
    pending_submissions: "Pending Submissions",
    data_quality_score: "Data Quality",
    dq_good: "Good",
    dq_average: "Average",
    dq_low: "Low",
    no_recent_activity: "No recent activity",
    no_activity_hint: "Add users or monitor operations to see activity here",
    no_alerts: "No active alerts",
    no_alerts_hint: "You'll be notified when important system events occur",
    manage_users: "Manage Users",
    send_message: "Send Message",
    view_analytics: "View Analytics",
    data_management: "Data Management",
    quick_actions: "Quick Actions",
    user_activity: "User Activity",
    data_submissions: "Data Submissions",
    recent_activity: "Recent Activity",
    alerts: "Alerts",
    enrollment_status: "Enrollment Status",
    enrollment_active: "Active",
    enrollment_pending: "Pending",
    enrollment_rejected: "Rejected",
    enrollment_withdrawn: "Withdrawn",
    enrollment_waitlisted: "Waitlisted",
    time_minutes_ago: "{{count}} minutes ago",
    time_hours_ago: "{{count}} hours ago",
    time_days_ago: "{{count}} days ago",
    reports_today: "Reports Today",
    compliance_rate: "Compliance Rate",
    overview: "Overview",
    activity_filter_bar: "Filter recent activity",
    activity_user: "User ID",
    activity_module: "Module",
    activity_entity: "Affected Entity",
    activity_role: "Role",
    activity_severity: "Severity",
    activity_status: "Status",
    activity_start_date: "Start date",
    activity_end_date: "End date",
    activity_search_placeholder: "Search recent activity…",
    activity_prev_page: "Previous page",
    activity_next_page: "Next page",
    activity_page_status: "Page {{page}} of {{total}}",
    status_good: "Good",
    status_warning: "Needs attention",
    status_critical: "Critical",
    status_unavailable: "Unavailable",
    status_success: "Success",
    status_failed: "Failed",
    trend_compare_period: "{{change}} vs. previous period",
    trend_no_baseline: "No reliable prior-period comparison",
    value_unavailable: "Unavailable",
    view_users: "View Users",
    view_kindergartens: "View Kindergartens",
    view_reports: "View Reports",
    dq_view_issues: "View data issues",
    dq_improve: "Improve data quality",
    view_data_management: "Data Management",
  },
  errors: {
    generic_error:   "An error occurred. Please try again.",
    request_timeout: "Request timed out. Please try again.",
  },
};

// Arabic translations — must cover every key used in admin_dashboard.html
// and admin_dashboard.js so pages render correctly even when JSON files fail to load.
const defaultArabicTranslations = {
  language: {
    en: "English",
    ar: "العربية",
  },
  page: {
    title: "إدارة كينجو",
    description: "نظام إدارة حضانات الأطفال المهني",
  },
  nav: {
    brand: "كينجو",
    dashboard: "لوحة التحكم",
    users: "المستخدمون",
    communication: "التواصل",
    analytics: "التحليلات",
    governance: "الحوكمة",
    data: "إدارة البيانات",
    security: "الأمان",
  },
  a11y: {
    skip_nav: "تخطي إلى التصفح"
  },
  components: {
    error_title: "خطأ",
    background_error: "حدث خطأ في الخلفية"
  },
  common: {
    save: "حفظ",
    cancel: "إلغاء",
    delete: "حذف",
    edit: "تعديل",
    add: "إضافة",
    search: "بحث",
    filter: "تصفية",
    export: "تصدير",
    import: "استيراد",
    loading: "جارٍ تحميل البيانات، يرجى الانتظار.",
    no_data: "لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.",
    confirm: "تأكيد",
    yes: "نعم",
    no: "لا",
    refresh: "تحديث",
    error: "خطأ",
    just_now: "الآن",
    minutes_ago: "دقائق مضت",
    hours_ago: "ساعات مضت",
    days_ago: "أيام مضت",
    locale: "ar-SA",
  },
  dashboard: {
    title: "لوحة التحكم",
    subtitle: "مراقبة أداء النظام وإدارة العمليات",
    welcome: "مرحباً بك في إدارة كينجو",
    total_users: "إجمالي المستخدمين",
    active_users: "المستخدمون النشطون",
    total_kindergartens: "إجمالي الحضانات",
    active_kindergartens: "الحضانات النشطة",
    total_submissions: "إجمالي الطلبات",
    pending_submissions: "الطلبات المعلقة",
    data_quality_score: "مؤشر جودة البيانات",
    dq_good: "جيد",
    dq_average: "متوسط",
    dq_low: "منخفض",
    no_recent_activity: "لا يوجد نشاط حديث",
    no_activity_hint: "ابدأ بإضافة مستخدمين أو متابعة العمليات لعرض النشاط هنا",
    no_alerts: "لا توجد تنبيهات نشطة",
    no_alerts_hint: "سيتم إخطارك عند وقوع أحداث مهمة في النظام",
    manage_users: "إدارة المستخدمين",
    send_message: "إرسال رسالة",
    view_analytics: "عرض التحليلات",
    data_management: "إدارة البيانات",
    quick_actions: "الإجراءات السريعة",
    user_activity: "نشاط المستخدمين",
    data_submissions: "عمليات الإدخال",
    recent_activity: "النشاط الأخير",
    alerts: "التنبيهات",
    enrollment_status: "حالة التسجيل",
    enrollment_active: "نشط",
    enrollment_pending: "قيد الانتظار",
    enrollment_rejected: "مرفوض",
    enrollment_withdrawn: "منسحب",
    enrollment_waitlisted: "قائمة الانتظار",
    time_minutes_ago: "منذ {{count}} دقيقة",
    time_hours_ago: "منذ {{count}} ساعة",
    time_days_ago: "منذ {{count}} يوم",
    reports_today: "التقارير اليوم",
    compliance_rate: "معدل الامتثال",
    overview: "نظرة عامة",
    activity_filter_bar: "تصفية النشاط الأخير",
    activity_user: "رقم المستخدم",
    activity_module: "القسم",
    activity_entity: "الكيان المتأثر",
    activity_role: "الدور",
    activity_severity: "الخطورة",
    activity_status: "الحالة",
    activity_start_date: "تاريخ البداية",
    activity_end_date: "تاريخ النهاية",
    activity_search_placeholder: "ابحث في النشاط الأخير...",
    activity_prev_page: "الصفحة السابقة",
    activity_next_page: "الصفحة التالية",
    activity_page_status: "صفحة {{page}} من {{total}}",
    status_good: "جيد",
    status_warning: "يتطلب انتباه",
    status_critical: "حرج",
    status_unavailable: "غير متاحة",
    status_success: "ناجح",
    status_failed: "فشل",
    trend_compare_period: "{{change}} مقارنة بالفترة السابقة",
    trend_no_baseline: "لا تتوفر مقارنة موثوقة بالفترة السابقة",
    value_unavailable: "غير متاحة",
    view_users: "عرض المستخدمين",
    view_kindergartens: "عرض الحضانات",
    view_reports: "عرض التقارير",
    dq_view_issues: "عرض مشاكل البيانات",
    dq_improve: "تحسين جودة البيانات",
    view_data_management: "إدارة البيانات",
  },
  errors: {
    generic_error:   "حدث خطأ. يرجى المحاولة مرة أخرى.",
    request_timeout: "انتهت مهلة الطلب. يرجى المحاولة مرة أخرى.",
  },
};

// ============================================================================
// INITIALIZATION
// ============================================================================

// Initialize i18n when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  if (window.AdminI18n) {
    return;
  }

  // Set default translations
  const i18n = new AdminI18n();

  // Make i18n globally available
  window.AdminI18n = i18n;

  // Add default translations if not loaded from files
  if (!i18n.translations.en || Object.keys(i18n.translations.en).length === 0) {
    i18n.translations.en = defaultEnglishTranslations;
  }
  if (!i18n.translations.ar || Object.keys(i18n.translations.ar).length === 0) {
    i18n.translations.ar = defaultArabicTranslations;
  }
});

// Export for module usage
if (typeof module !== "undefined" && module.exports) {
  module.exports = AdminI18n;
}
