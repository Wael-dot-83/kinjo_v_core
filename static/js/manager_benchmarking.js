(function () {
  const IS_AR = (document.documentElement.lang || 'ar') !== 'en';
  const tr = (ar, en) => IS_AR ? ar : en;

  async function apiRequest(url) {
    // Auth is the httpOnly session cookie (kinjo_session), sent automatically
    // on same-origin fetch. Benchmarking is read-only, so no CSRF token needed (F2).
    const headers = { "Content-Type": "application/json" };

    let response = null;
    if (typeof window.fetchWithAuth === "function") {
      response = await window.fetchWithAuth(url, { headers });
      if (!response) {
        throw new Error(tr("يتطلب تسجيل الدخول", "Sign-in is required"));
      }
    } else {
      response = await fetch(url, { headers });
    }

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || tr("تعذر تحميل البيانات", "Unable to load data"));
    }
    return response.json();
  }

  /** Pick the band label matching the UI language.
   *
   * The classification row stores band_label in Arabic only; the API now also
   * returns band_label_en alongside it. Falling back to the Arabic label keeps
   * this working against an older response shape rather than rendering blank.
   */
  function bandLabel(source) {
    if (!source) return tr("غير مصنف", "Unclassified");
    const label = IS_AR ? source.band_label : (source.band_label_en || source.band_label);
    return label || tr("غير مصنف", "Unclassified");
  }

  // toFixed(2) rendered "82.00" and "100.00%" for whole numbers and spelled the
  // digits in Latin, while the rest of the Arabic UI (context strip, KPI page)
  // uses Arabic-Indic. toLocaleString fixes both: maximumFractionDigits drops a
  // trailing ".0" instead of padding to it, so a score reads 82, a percentile
  // reads 45.5, and neither carries more precision than the number deserves.
  function formatNumber(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "--";
    }
    return Number(value).toLocaleString(IS_AR ? "ar-JO" : "en", {
      maximumFractionDigits: digits,
    });
  }

  function formatDateValue(dateObj) {
    const year = dateObj.getFullYear();
    const month = String(dateObj.getMonth() + 1).padStart(2, "0");
    const day = String(dateObj.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function defaultPeriod() {
    const endInput = document.getElementById("managerPeriodEnd");
    const startInput = document.getElementById("managerPeriodStart");
    if (!endInput || !startInput) {
      return;
    }
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(endDate.getDate() - 29);
    endInput.value = formatDateValue(endDate);
    startInput.value = formatDateValue(startDate);
  }

  function showError(message) {
    const box = document.getElementById("managerBenchmarkError");
    if (!box) {
      return;
    }
    if (message) {
      box.textContent = message;
      box.classList.remove("d-none");
    } else {
      box.textContent = "";
      box.classList.add("d-none");
    }
  }

  function requestParams() {
    const params = new URLSearchParams();
    const periodStart = document.getElementById("managerPeriodStart")?.value;
    const periodEnd = document.getElementById("managerPeriodEnd")?.value;
    const sizeMode = document.getElementById("managerSizeMode")?.value;
    if (periodStart) params.set("period_start", periodStart);
    if (periodEnd) params.set("period_end", periodEnd);
    if (sizeMode) params.set("size_mode", sizeMode);
    return params;
  }

  function renderSummary(data) {
    const finalScoreEl = document.getElementById("managerFinalScore");
    const percentileEl = document.getElementById("managerPercentile");
    const bandEl = document.getElementById("managerBand");
    const peerSizeEl = document.getElementById("managerPeerSize");
    const tableBody = document.getElementById("managerPeersTableBody");
    if (!finalScoreEl || !percentileEl || !bandEl || !peerSizeEl || !tableBody) {
      return;
    }

    finalScoreEl.textContent =
      data.final_score === null ? tr("غير متاح", "Not available") : formatNumber(data.final_score);
    percentileEl.textContent =
      data.percentile === null ? "--" : `${formatNumber(data.percentile)}%`;
    // band_label is persisted in Arabic only; band_label_en is its English
    // counterpart. Reading band_label unconditionally left "أخضر" sitting in an
    // otherwise fully English page.
    bandEl.textContent = bandLabel(data);

    // Colour the card's status rail to match the band. The response carries no
    // machine-readable band code — only the two display labels — so this maps
    // from band_label_en, which classification_service._BAND_LABEL_EN pins to a
    // closed set ("Green"/"Amber"/"Red"/"Unclassified"). If that endpoint ever
    // grows a real band_code field, switch to it: matching on a display string
    // is the weakest link here.
    const bandCard = document.getElementById("managerBandCard");
    if (bandCard) {
      const RAIL_BY_BAND = {
        Green: "mgr-state-healthy",
        Amber: "mgr-state-attention",
        Red: "mgr-state-breach",
      };
      bandCard.classList.remove(
        "mgr-state-healthy",
        "mgr-state-attention",
        "mgr-state-breach"
      );
      const rail = RAIL_BY_BAND[data.band_label_en];
      if (rail) bandCard.classList.add(rail);
    }

    peerSizeEl.textContent = String(data.peer_group_size ?? 0);

    const peers = data.anonymized_peers || [];
    if (peers.length === 0) {
      tableBody.innerHTML =
        `<tr><td colspan="5" class="text-center text-muted">${tr("لا توجد بيانات ندية كافية", "Insufficient peer data")}</td></tr>`;
      return;
    }
    tableBody.innerHTML = peers
      .map(
        (peer) => `
      <tr>
        <td>${escapeHtml(peer.peer_code)}</td>
        <td>${peer.rank ?? "--"}</td>
        <td>${peer.percentile === null ? "--" : `${formatNumber(peer.percentile)}%`}</td>
        <td>${escapeHtml(bandLabel(peer))}</td>
        <td>${peer.final_score === null ? "--" : formatNumber(peer.final_score)}</td>
      </tr>
    `
      )
      .join("");
  }

  async function loadSummary() {
    showError("");
    try {
      const params = requestParams();
      const data = await apiRequest(`/api/manager/benchmarking/summary?${params.toString()}`);
      renderSummary(data);
      if (data.insufficient_data && data.insufficient_reason) {
        showError(`${tr("البيانات غير كافية للمقارنة: ", "Insufficient data for comparison: ")}${data.insufficient_reason}`);
      }
    } catch (error) {
      showError(tr("تعذر تحميل المقارنة المعيارية حالياً.", "Unable to load benchmarking data at this time."));
    }
  }

  function init() {
    if (!document.getElementById("managerBenchmarkRoot")) {
      return;
    }
    defaultPeriod();
    document.getElementById("managerBenchmarkLoadBtn")?.addEventListener("click", loadSummary);
    // Replaces inline onsubmit="event.preventDefault()" (F1/CSP).
    document.querySelectorAll("form.js-noreload").forEach(function (f) {
      f.addEventListener("submit", function (e) { e.preventDefault(); });
    });
    loadSummary();
  }

  init();
})();
