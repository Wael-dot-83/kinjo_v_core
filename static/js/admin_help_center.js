(function () {
  "use strict";

  const searchInput = document.getElementById("helpSearch");
  const clearButton = document.getElementById("helpClear");
  const resultsCount = document.getElementById("helpResultsCount");
  const liveRegion = document.getElementById("helpLiveRegion");
  const noResults = document.getElementById("helpNoResults");

  if (!searchInput || !resultsCount || !liveRegion) {
    return;
  }

  const isEnglish = (document.documentElement.lang || "ar").toLowerCase().startsWith("en");

  const topicSections = Array.from(document.querySelectorAll("[data-help-topic]"));
  const tocLinks = Array.from(document.querySelectorAll("[data-help-nav-link]"));
  const coverageRows = Array.from(document.querySelectorAll("[data-help-coverage-row]"));
  const faqItems = Array.from(document.querySelectorAll("[data-help-faq-item]"));
  const glossaryRows = Array.from(document.querySelectorAll("#glossary [data-help-row]"));

  const indexById = new Map();
  topicSections.forEach((section) => {
    if (section.id) {
      indexById.set(section.id, section);
    }
  });

  function normalizeArabic(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u064B-\u065F\u0670\u0640]/g, "")
      .replace(/[\u0622\u0623\u0625\u0671]/g, "ا")
      .replace(/ؤ/g, "و")
      .replace(/ئ/g, "ي")
      .replace(/ى/g, "ي")
      .replace(/ة/g, "ه")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  function normalizeForSearch(value) {
    return normalizeArabic(value).replace(/\s+/g, " ").trim();
  }

  function buildNormalizedIndexMap(value) {
    const original = String(value || "");
    let normalized = "";
    const indexMap = [];

    for (let i = 0; i < original.length; i += 1) {
      const normalizedChar = normalizeForSearch(original[i]);
      if (!normalizedChar) {
        continue;
      }
      for (const ch of normalizedChar) {
        normalized += ch;
        indexMap.push(i);
      }
    }

    return { normalized, indexMap };
  }

  function getSearchUrl(term) {
    const url = new URL(window.location.href);
    if (term) {
      url.searchParams.set("q", term);
    } else {
      url.searchParams.delete("q");
    }
    return url;
  }

  function updateUrl(term) {
    const next = getSearchUrl(term);
    window.history.replaceState({}, "", next);
  }

  function restoreText(node) {
    if (!node.dataset.originalText) {
      node.dataset.originalText = node.textContent || "";
    }
    node.textContent = node.dataset.originalText;
  }

  function highlightNode(node, rawTerm) {
    if (!rawTerm) {
      restoreText(node);
      return;
    }

    if (!node.dataset.originalText) {
      node.dataset.originalText = node.textContent || "";
    }

    const original = node.dataset.originalText;
    const normalizedTerm = normalizeForSearch(rawTerm);
    const { normalized, indexMap } = buildNormalizedIndexMap(original);
    const index = normalized.indexOf(normalizedTerm);
    if (index === -1) {
      node.textContent = original;
      return;
    }

    const start = indexMap[index];
    const end = indexMap[index + normalizedTerm.length - 1] + 1;
    const before = original.slice(0, start);
    const match = original.slice(start, end);
    const after = original.slice(end);

    node.textContent = "";
    if (before) {
      node.appendChild(document.createTextNode(before));
    }
    const mark = document.createElement("mark");
    mark.className = "help-match";
    mark.textContent = match;
    node.appendChild(mark);
    if (after) {
      node.appendChild(document.createTextNode(after));
    }
  }

  function setActiveTopic(id) {
    tocLinks.forEach((link) => {
      const isActive = link.getAttribute("href") === "#" + id;
      link.classList.toggle("is-active", isActive);
      if (isActive) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });
  }

  function clearHighlights() {
    document.querySelectorAll("[data-original-text]").forEach((node) => {
      restoreText(node);
    });
  }

  function collectVisibleTopics() {
    return topicSections.filter((section) => !section.hidden && section.dataset.hidden !== "true");
  }

  function updateTopicNavigation() {
    const visibleTopics = collectVisibleTopics();
    const visibleTopicIndex = new Map(visibleTopics.map((section, index) => [section.id, index]));
    const previousLabel = isEnglish ? "Previous" : "السابق";
    const nextLabel = isEnglish ? "Next" : "التالي";

    topicSections.forEach((section) => {
      const currentIndex = visibleTopicIndex.get(section.id);
      const prevLink = section.querySelector("[data-help-prev-link]");
      const nextLink = section.querySelector("[data-help-next-link]");

      if (prevLink) {
        const prevTopic = currentIndex > 0 ? visibleTopics[currentIndex - 1] : null;
        if (prevTopic) {
          prevLink.hidden = false;
          prevLink.setAttribute("href", "#" + prevTopic.id);
          prevLink.textContent = `${previousLabel}: ${prevTopic.querySelector("h2")?.textContent || prevTopic.id}`;
        } else {
          prevLink.hidden = true;
        }
      }

      if (nextLink) {
        const nextTopic = currentIndex !== undefined && currentIndex < visibleTopics.length - 1
          ? visibleTopics[currentIndex + 1]
          : null;
        if (nextTopic) {
          nextLink.hidden = false;
          nextLink.setAttribute("href", "#" + nextTopic.id);
          nextLink.textContent = `${nextLabel}: ${nextTopic.querySelector("h2")?.textContent || nextTopic.id}`;
        } else {
          nextLink.hidden = true;
        }
      }
    });
  }

  function applySearch(rawValue) {
    const rawTerm = rawValue.trim();
    const term = normalizeForSearch(rawTerm);
    const url = new URL(window.location.href);

    if (rawTerm) {
      url.searchParams.set("q", rawTerm);
      clearButton.hidden = false;
    } else {
      url.searchParams.delete("q");
      clearButton.hidden = true;
    }
    window.history.replaceState({}, "", url);

    clearHighlights();

    let matchedTopics = 0;
    let matchedFaqs = 0;
    let matchedGlossaryRows = 0;
    let matchedCoverageRows = 0;

    topicSections.forEach((section) => {
      const searchText = normalizeForSearch(section.dataset.searchText || section.textContent || "");
      const matches = !term || searchText.includes(term);
      section.hidden = !matches;
      section.dataset.hidden = matches ? "false" : "true";
      if (matches) {
        matchedTopics += 1;
      }
    });

    coverageRows.forEach((row) => {
      const searchText = normalizeForSearch(row.dataset.searchText || row.textContent || "");
      const matches = !term || searchText.includes(term);
      row.hidden = !matches;
      if (matches) {
        matchedCoverageRows += 1;
      }
    });

    faqItems.forEach((item) => {
      const searchText = normalizeForSearch(item.dataset.searchText || item.textContent || "");
      const matches = !term || searchText.includes(term);
      item.hidden = !matches;
      const collapseEl = item.querySelector(".accordion-collapse");
      const button = item.querySelector(".accordion-button");
      if (collapseEl) {
        collapseEl.classList.toggle("show", Boolean(term) && matches);
      }
      if (button) {
        button.classList.toggle("collapsed", !(Boolean(term) && matches));
        button.setAttribute("aria-expanded", Boolean(term) && matches ? "true" : "false");
      }
      if (matches) {
        matchedFaqs += 1;
      }
    });

    glossaryRows.forEach((row) => {
      const searchText = normalizeForSearch(row.dataset.searchText || row.textContent || "");
      const matches = !term || searchText.includes(term);
      row.hidden = !matches;
      if (matches) {
        matchedGlossaryRows += 1;
      }
    });

    if (rawTerm) {
      const lowercaseTerm = rawTerm.toLowerCase();
      document.querySelectorAll("[data-help-topic] h2, [data-help-nav-link], [data-help-row] td:first-child, .help-faq-item .accordion-button").forEach((node) => {
        const source = node.dataset.originalText || node.textContent || "";
        if ((source || "").toLowerCase().includes(lowercaseTerm)) {
          highlightNode(node, rawTerm);
        }
      });
    }

    const totalMatches = matchedTopics + matchedFaqs + matchedGlossaryRows + matchedCoverageRows;
    if (rawTerm) {
      resultsCount.textContent = isEnglish
        ? `${totalMatches} ${totalMatches === 1 ? "match" : "matches"} found`
        : `تم العثور على ${totalMatches} ${totalMatches === 1 ? "مطابقة" : "مطابقات"}`;
      liveRegion.textContent = isEnglish
        ? `${totalMatches} ${totalMatches === 1 ? "result" : "results"} matched your search.`
        : `تطابق ${totalMatches} ${totalMatches === 1 ? "نتيجة" : "نتائج"} مع البحث.`;
    } else {
      resultsCount.textContent = isEnglish ? "All topics shown" : "تظهر كل الموضوعات";
      liveRegion.textContent = isEnglish
        ? "Search cleared. All help topics are visible."
        : "تم مسح البحث. تظهر جميع موضوعات المساعدة.";
    }

    if (noResults) {
      noResults.hidden = totalMatches !== 0 || !rawTerm;
    }

    tocLinks.forEach((link) => {
      const target = indexById.get(link.getAttribute("href")?.slice(1));
      const matches = !term || (target && !target.hidden);
      link.hidden = !matches;
    });

    updateTopicNavigation();

    const firstVisible = collectVisibleTopics()[0];
    if (firstVisible) {
      setActiveTopic(firstVisible.id);
    }
  }

  searchInput.addEventListener("input", () => {
    applySearch(searchInput.value);
  });

  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && searchInput.value) {
      event.preventDefault();
      searchInput.value = "";
      applySearch("");
      searchInput.focus();
    }
  });

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      searchInput.value = "";
      applySearch("");
      searchInput.focus();
    });
  }

  const observer = "IntersectionObserver" in window
    ? new IntersectionObserver((entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting && !entry.target.hidden)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible && visible.target.id) {
          setActiveTopic(visible.target.id);
        }
      }, { threshold: [0.35, 0.5, 0.75] })
    : null;

  if (observer) {
    topicSections.forEach((section) => observer.observe(section));
  }

  tocLinks.forEach((link) => {
    link.addEventListener("click", () => {
      const targetId = link.getAttribute("href")?.slice(1);
      if (targetId) {
        setActiveTopic(targetId);
      }
    });
  });

  const initial = normalizeForSearch(new URL(window.location.href).searchParams.get("q") || "");
  if (initial) {
    searchInput.value = new URL(window.location.href).searchParams.get("q") || "";
    clearButton.hidden = false;
  }
  applySearch(searchInput.value);
})();
