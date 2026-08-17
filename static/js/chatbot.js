/**
 * static/js/chatbot.js — KinJo Bilingual Floating AI/FAQ Chatbot Widget Controller
 */

(function () {
  "use strict";

  var widget,
    launcherBtn,
    chatWindow,
    messagesContainer,
    typingIndicator,
    quickChipsContainer,
    inputForm,
    inputField,
    sendBtn,
    clearBtn,
    closeBtn,
    unreadBadge;

  var currentLang = "ar";
  var sessionId = "kinjo_chat_" + Math.random().toString(36).substring(2, 9);
  var isWaitingResponse = false;

  var I18N = {
    ar: {
      welcomeTitle: "مرحباً بك في كينجو! 👋",
      welcomeMsg: "أنا مساعدك الذكي، كيف يمكنني مساعدتك اليوم بخصوص الحضانات، التسجيل، أو التقارير؟",
      chips: [
        "كيف أسجل طفلي؟",
        "ابحث عن حضانة قريبة",
        "التقارير اليومية والمتابعة",
        "التطعيمات والصحة",
        "تواصل مع الدعم"
      ],
      placeholder: "اكتب سؤالك هنا...",
      errorMsg: "عذراً، حدث خطأ أثناء معالجة الطلب. يرجى المحاولة مرة أخرى.",
      emptyWarning: "يرجى كتابة رسالة أولاً."
    },
    en: {
      welcomeTitle: "Welcome to KinJo! 👋",
      welcomeMsg: "I'm your AI Assistant. How can I help you today with nursery discovery, enrollment, or daily reports?",
      chips: [
        "How to enroll a child?",
        "Find nearby nurseries",
        "Daily reports & tracking",
        "Vaccines & Health",
        "Contact Support"
      ],
      placeholder: "Type a question...",
      errorMsg: "Sorry, an error occurred while processing your request. Please try again.",
      emptyWarning: "Please type a message first."
    }
  };

  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  function detectLanguage() {
    var docLang = document.documentElement.getAttribute("lang") || "ar";
    if (docLang.toLowerCase().startsWith("en")) {
      return "en";
    }
    var widgetElem = document.getElementById("kinjo-chatbot-widget");
    if (widgetElem && widgetElem.getAttribute("data-ui-lang") === "en") {
      return "en";
    }
    return "ar";
  }

  function formatTime(date) {
    var d = date || new Date();
    var hours = d.getHours();
    var minutes = d.getMinutes();
    var ampm = hours >= 12 ? (currentLang === "ar" ? "م" : "PM") : (currentLang === "ar" ? "ص" : "AM");
    hours = hours % 12;
    hours = hours ? hours : 12;
    var minutesStr = minutes < 10 ? "0" + minutes : minutes;
    return hours + ":" + minutesStr + " " + ampm;
  }

  function scrollToBottom() {
    if (messagesContainer) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  }

  function showTypingIndicator(show) {
    if (!typingIndicator) return;
    typingIndicator.style.display = show ? "flex" : "none";
    if (show) scrollToBottom();
  }

  function renderChips(chips) {
    if (!quickChipsContainer) return;
    quickChipsContainer.innerHTML = "";
    var list = chips || I18N[currentLang].chips;
    list.forEach(function (text) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chatbot-chip-btn";
      chip.textContent = text;
      chip.addEventListener("click", function () {
        handleUserMessage(text);
      });
      quickChipsContainer.appendChild(chip);
    });
  }

  function appendMessage(sender, text, actions) {
    if (!messagesContainer) return;

    var msgDiv = document.createElement("div");
    msgDiv.className = "chatbot-message " + (sender === "user" ? "is-user" : "is-bot");

    var bubble = document.createElement("div");
    bubble.className = "chatbot-bubble";
    bubble.textContent = text;

    if (actions && actions.length > 0) {
      var actionsWrap = document.createElement("div");
      actionsWrap.className = "chatbot-actions-wrap";
      actions.forEach(function (act) {
        var link = document.createElement("a");
        link.className = "chatbot-action-link";
        link.href = act.url;
        link.innerHTML = (act.icon ? '<i class="bi ' + act.icon + '"></i> ' : '') + act.label;
        actionsWrap.appendChild(link);
      });
      bubble.appendChild(actionsWrap);
    }

    var timeSpan = document.createElement("span");
    timeSpan.className = "chatbot-time";
    timeSpan.textContent = formatTime();

    msgDiv.appendChild(bubble);
    msgDiv.appendChild(timeSpan);
    messagesContainer.appendChild(msgDiv);

    scrollToBottom();
  }

  function renderInitialWelcome() {
    if (!messagesContainer) return;
    messagesContainer.innerHTML = "";
    var langStrings = I18N[currentLang];
    var welcomeText = langStrings.welcomeTitle + "\n" + langStrings.welcomeMsg;
    appendMessage("bot", welcomeText, [
      { label: currentLang === "ar" ? "دليل الحضانات" : "Browse Nurseries", url: "/kindergartens", icon: "bi-building" },
      { label: currentLang === "ar" ? "تقديم طلب تسجيل" : "Apply for Enrollment", url: "/enrollment/apply", icon: "bi-person-plus" }
    ]);
    renderChips(langStrings.chips);
  }

  function toggleWidget(forceOpen) {
    if (!widget) return;
    var isOpen = typeof forceOpen === "boolean" ? forceOpen : !widget.classList.contains("is-open");
    if (isOpen) {
      widget.classList.add("is-open");
      launcherBtn.setAttribute("aria-expanded", "true");
      chatWindow.setAttribute("aria-hidden", "false");
      if (unreadBadge) unreadBadge.style.display = "none";
      setTimeout(function () {
        if (inputField) inputField.focus();
        scrollToBottom();
      }, 150);
    } else {
      widget.classList.remove("is-open");
      launcherBtn.setAttribute("aria-expanded", "false");
      chatWindow.setAttribute("aria-hidden", "true");
      launcherBtn.focus();
    }
  }

  function handleUserMessage(messageText) {
    var text = (messageText || "").trim();
    if (!text || isWaitingResponse) return;

    if (inputField) inputField.value = "";
    appendMessage("user", text);

    isWaitingResponse = true;
    if (sendBtn) sendBtn.disabled = true;
    showTypingIndicator(true);

    var csrfToken = getCsrfToken();
    var headers = {
      "Content-Type": "application/json",
      "Accept": "application/json"
    };
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }

    fetch("/api/assistant/chat", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({
        message: text,
        lang: currentLang,
        session_id: sessionId
      })
    })
      .then(function (res) {
        if (!res.ok) {
          throw new Error("HTTP error " + res.status);
        }
        return res.json();
      })
      .then(function (data) {
        showTypingIndicator(false);
        isWaitingResponse = false;
        if (sendBtn) sendBtn.disabled = false;

        appendMessage("bot", data.reply, data.actions);
        if (data.suggested_queries && data.suggested_queries.length > 0) {
          renderChips(data.suggested_queries);
        }
      })
      .catch(function (err) {
        console.warn("KinJo Chatbot API fallback:", err);
        showTypingIndicator(false);
        isWaitingResponse = false;
        if (sendBtn) sendBtn.disabled = false;

        var fallbackReply = currentLang === "ar"
          ? "شكراً لتواصلك مع منصة كينجو. يمكنك استعراض الحضانات وتقديم طلبات التسجيل مباشرة، أو التواصل مع فريق الدعم."
          : "Thank you for contacting KinJo. You can browse accredited nurseries, submit enrollment requests, or reach out to our support team.";
        appendMessage("bot", fallbackReply, [
          { label: currentLang === "ar" ? "دليل الحضانات" : "Nurseries", url: "/kindergartens", icon: "bi-building" },
          { label: currentLang === "ar" ? "تواصل معنا" : "Contact", url: "/contact", icon: "bi-envelope" }
        ]);
      });
  }

  function initChatbot() {
    widget = document.getElementById("kinjo-chatbot-widget");
    if (!widget) return;

    launcherBtn = document.getElementById("kinjo-chatbot-launcher");
    chatWindow = document.getElementById("kinjo-chatbot-window");
    messagesContainer = document.getElementById("chatbot-messages-container");
    typingIndicator = document.getElementById("chatbot-typing-indicator");
    quickChipsContainer = document.getElementById("chatbot-quick-chips");
    inputForm = document.getElementById("chatbot-input-form");
    inputField = document.getElementById("chatbot-input-field");
    sendBtn = document.getElementById("chatbot-send-btn");
    clearBtn = document.getElementById("chatbot-clear-btn");
    closeBtn = document.getElementById("chatbot-close-btn");
    unreadBadge = document.getElementById("chatbot-unread-badge");

    currentLang = detectLanguage();

    // Event listeners
    if (launcherBtn) {
      launcherBtn.addEventListener("click", function () {
        toggleWidget();
      });
    }

    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        toggleWidget(false);
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        renderInitialWelcome();
      });
    }

    if (inputForm) {
      inputForm.addEventListener("submit", function (e) {
        e.preventDefault();
        if (inputField) {
          handleUserMessage(inputField.value);
        }
      });
    }

    // Keyboard accessibility: ESC key to close widget
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && widget.classList.contains("is-open")) {
        toggleWidget(false);
      }
    });

    renderInitialWelcome();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initChatbot);
  } else {
    initChatbot();
  }
})();
