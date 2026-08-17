/**
 * static/js/chatbot.js — KinJo Elite Multi-Role AI Assistant / FAQ Chatbot Controller
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
    unreadBadge,
    roleSelector,
    userAvatarIcon;

  var currentLang = "ar";
  var currentRole = "parent";
  var sessionId = "kinjo_chat_" + Math.random().toString(36).substring(2, 9);
  var isWaitingResponse = false;

  var ROLE_META = {
    parent: {
      icon: "👨‍👩‍👧",
      title_ar: "ولي أمر",
      title_en: "Parent",
      badge_class: "role-parent"
    },
    supervisor: {
      icon: "📋",
      title_ar: "مشرف تربوي",
      title_en: "Supervisor",
      badge_class: "role-supervisor"
    },
    manager: {
      icon: "🏢",
      title_ar: "مدير حضانة",
      title_en: "Manager",
      badge_class: "role-manager"
    },
    general: {
      icon: "👤",
      title_ar: "زائر",
      title_en: "Visitor",
      badge_class: "role-general"
    }
  };

  var I18N = {
    ar: {
      roles: {
        parent: {
          welcome: "مرحباً بك يا ولي الأمر! 👨‍👩‍👧\n\nأنا مساعد كينجو الذكي. كيف يمكنني مساعدتك اليوم في: تسجيل طفلك، متابعة التقارير اليومية والوجبات، مواعيد التطعيمات، أو الرسوم؟",
          chips: [
            "كيف أسجل طفلي في الحضانة؟",
            "ما هي الأوراق المطلوبة للتسجيل؟",
            "كيف أتابع التقارير اليومية لطفلي؟",
            "جدول التطعيمات الوطني المعتمد",
            "استعراض الحضانات والرسوم"
          ]
        },
        supervisor: {
          welcome: "أهلاً بك حضرة المشرف التربوي والمدقق! 📋\n\nأنا جاهز لمساعدتك في: تدقيق سجلات الحضور والانصراف، مراجعة نسب المربيات للأطفال، استكمال نماذج التفتيش، وإصدار التقارير الإحصائية الرسمية.",
          chips: [
            "ما هي النسب القانونية المعتمدة للأطفال؟",
            "كيف أدقق سجل الحضور اليومي للحضانة؟",
            "كيف أوثق زيارة تفتيشية رسمية؟",
            "تصدير التقارير الإحصائية لـ MoSD"
          ]
        },
        manager: {
          welcome: "أهلاً بك إدارة الحضانة والكادر التعليمي! 🏢\n\nأنا في خدمتك لمساعدتك في: إدارة طلبات التسجيل وقبول الطلاب، تنظيم الشعب وتوزيع الكادر، متابعة السعة الاستيعابية، وتجديد الترخيص والامتثال.",
          chips: [
            "كيف أعتمد طلب تسجيل طفل جديد؟",
            "كيف أصدر تقرير الحضور الشهري للوزارة؟",
            "ما هي شروط تجديد ترخيص الحضانة؟",
            "إدارة الشعب وتوزيع الكادر"
          ]
        },
        general: {
          welcome: "مرحباً بك في منصة كينجو الوطنية لرياض الأطفال في الأردن! 🇯🇴\n\nأنا المساعد الذكي المعتمد، اختر دورك أعلاه أو اسألني مباشرة عن الحضانات المرخصة، إجراءات التسجيل، أو الدعم الفني.",
          chips: [
            "ابحث عن حضانة معتمدة في عمان",
            "كيف أسجل طفلي في الحضانة؟",
            "ما هي معايير الأمان والخصوصية؟",
            "تواصل مع الدعم الفني"
          ]
        }
      },
      placeholder: "اكتب سؤالك هنا...",
      errorMsg: "عذراً، حدث خطأ أثناء معالجة الطلب. يرجى المحاولة مرة أخرى.",
      copied: "تم النسخ!"
    },
    en: {
      roles: {
        parent: {
          welcome: "Welcome Parent! 👨‍👩‍👧\n\nI am your KinJo AI Assistant. How can I help you today with: Child enrollment, daily care reports, meals & naps, vaccination schedules, or tuition fees?",
          chips: [
            "How do I enroll my child?",
            "Required documents for registration?",
            "How to view child daily reports?",
            "Official vaccination schedule",
            "Browse nurseries & fees"
          ]
        },
        supervisor: {
          welcome: "Welcome Supervisor / QA Auditor! 📋\n\nI am ready to assist you with: Attendance record auditing, staff-to-child ratio compliance, digital inspection checklists, and official ministry reporting exports.",
          chips: [
            "What are statutory child-to-staff ratios?",
            "How to audit live nursery attendance?",
            "How to record an inspection visit?",
            "Export compliance reports for MoSD"
          ]
        },
        manager: {
          welcome: "Welcome Kindergarten Management! 🏢\n\nI am here to assist with: Admissions pipeline, student approvals, section allocations, capacity limits, and institutional licensing compliance.",
          chips: [
            "How to accept an enrollment application?",
            "How to export monthly attendance report?",
            "Requirements for license renewal?",
            "Classroom section management"
          ]
        },
        general: {
          welcome: "Welcome to KinJo — Jordan's National Kindergarten Portal! 🇯🇴\n\nI am your official AI Assistant. Select your role above or ask me about: Licensed nurseries, enrollment steps, or technical support.",
          chips: [
            "Find accredited nurseries in Amman",
            "How do I enroll my child?",
            "What are privacy & security standards?",
            "Contact technical support"
          ]
        }
      },
      placeholder: "Ask a question...",
      errorMsg: "Sorry, an error occurred while processing your request. Please try again.",
      copied: "Copied!"
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

  function setRole(roleName, skipWelcome) {
    currentRole = ROLE_META[roleName] ? roleName : "parent";
    
    // Update Role Pills UI
    if (roleSelector) {
      var pills = roleSelector.querySelectorAll(".chatbot-role-pill");
      pills.forEach(function (pill) {
        if (pill.getAttribute("data-role") === currentRole) {
          pill.classList.add("is-active");
        } else {
          pill.classList.remove("is-active");
        }
      });
    }

    // Update Input User Avatar
    if (userAvatarIcon) {
      userAvatarIcon.textContent = ROLE_META[currentRole].icon;
    }

    if (!skipWelcome) {
      renderInitialWelcome();
    }
  }

  function renderChips(chips) {
    if (!quickChipsContainer) return;
    quickChipsContainer.innerHTML = "";
    var roleData = I18N[currentLang].roles[currentRole] || I18N[currentLang].roles.general;
    var list = chips || roleData.chips;
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

  function formatText(text) {
    if (!text) return "";
    var escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Replace bold **text**
    escaped = escaped.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    
    // Replace newlines
    escaped = escaped.replace(/\n/g, "<br>");
    return escaped;
  }

  function appendMessage(sender, text, actions, customRole) {
    if (!messagesContainer) return;

    var roleToUse = customRole || currentRole;
    var isBot = sender === "bot";

    var msgRow = document.createElement("div");
    msgRow.className = "chatbot-msg-row " + (isBot ? "is-bot" : "is-user");

    // Avatar
    var avatarDiv = document.createElement("div");
    avatarDiv.className = "chatbot-msg-avatar " + (isBot ? "chatbot-bot-msg-avatar" : "chatbot-user-msg-avatar");
    
    if (isBot) {
      avatarDiv.textContent = "🤖";
      avatarDiv.title = "KinJo Smart Assistant";
    } else {
      avatarDiv.textContent = ROLE_META[roleToUse].icon;
      avatarDiv.title = currentLang === "ar" ? ROLE_META[roleToUse].title_ar : ROLE_META[roleToUse].title_en;
    }

    var contentWrap = document.createElement("div");
    contentWrap.className = "chatbot-msg-content-wrap";

    var bubble = document.createElement("div");
    bubble.className = "chatbot-bubble " + (isBot ? "bot-bubble" : "user-bubble");
    bubble.innerHTML = formatText(text);

    // Actions
    if (actions && actions.length > 0) {
      var actionsWrap = document.createElement("div");
      actionsWrap.className = "chatbot-actions-wrap";
      actions.forEach(function (act) {
        var link = document.createElement("a");
        link.className = "chatbot-action-link";
        link.href = act.url;
        
        var iconHtml = "";
        if (act.icon) {
          if (act.icon.indexOf("bi-") !== -1) {
            iconHtml = '<i class="bi ' + act.icon + '"></i> ';
          } else {
            iconHtml = '<span class="material-symbols-outlined text-sm">' + act.icon + '</span> ';
          }
        }
        link.innerHTML = iconHtml + act.label;
        actionsWrap.appendChild(link);
      });
      bubble.appendChild(actionsWrap);
    }

    // Meta row (timestamp & copy)
    var metaRow = document.createElement("div");
    metaRow.className = "chatbot-msg-meta";

    var timeSpan = document.createElement("span");
    timeSpan.className = "chatbot-time";
    timeSpan.textContent = formatTime();
    metaRow.appendChild(timeSpan);

    if (isBot) {
      var copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "chatbot-copy-btn";
      copyBtn.innerHTML = '<i class="bi bi-copy"></i>';
      copyBtn.title = "Copy text";
      copyBtn.addEventListener("click", function () {
        navigator.clipboard.writeText(text).then(function () {
          copyBtn.innerHTML = '<i class="bi bi-check2"></i>';
          setTimeout(function () {
            copyBtn.innerHTML = '<i class="bi bi-copy"></i>';
          }, 2000);
        });
      });
      metaRow.appendChild(copyBtn);
    }

    contentWrap.appendChild(bubble);
    contentWrap.appendChild(metaRow);

    msgRow.appendChild(avatarDiv);
    msgRow.appendChild(contentWrap);

    messagesContainer.appendChild(msgRow);
    scrollToBottom();
  }

  function renderInitialWelcome() {
    if (!messagesContainer) return;
    messagesContainer.innerHTML = "";
    var roleData = I18N[currentLang].roles[currentRole] || I18N[currentLang].roles.general;
    
    var defaultActions = [
      { label: currentLang === "ar" ? "دليل الحضانات" : "Browse Nurseries", url: "/kindergartens", icon: "bi-building" },
      { label: currentLang === "ar" ? "تقديم طلب تسجيل" : "Apply for Enrollment", url: "/enrollment/apply", icon: "bi-person-plus-fill" }
    ];

    if (currentRole === "supervisor") {
      defaultActions = [
        { label: currentLang === "ar" ? "بوابة المشرفين" : "Supervisor QA", url: "/services#supervisors", icon: "bi-clipboard2-check-fill" },
        { label: currentLang === "ar" ? "تصدير التقارير" : "Export Reports", url: "/dashboard", icon: "bi-file-earmark-bar-graph" }
      ];
    } else if (currentRole === "manager") {
      defaultActions = [
        { label: currentLang === "ar" ? "لوحة الإدارة" : "Operations Dashboard", url: "/dashboard", icon: "bi-kanban-fill" },
        { label: currentLang === "ar" ? "إدارة الطلبات" : "Admissions Pipeline", url: "/kindergartens", icon: "bi-people-fill" }
      ];
    }

    appendMessage("bot", roleData.welcome, defaultActions);
    renderChips(roleData.chips);
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
    appendMessage("user", text, null, currentRole);

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
        role: currentRole,
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
          ? "شكراً لتواصلك مع منصة كينجو. يمكنك استعراض الخدمات وبدء التسجيل، أو التواصل مع فريق الدعم."
          : "Thank you for reaching out to KinJo. You can explore services, apply for enrollment, or contact our support team.";
        appendMessage("bot", fallbackReply, [
          { label: currentLang === "ar" ? "دليل الخدمات" : "Services", url: "/services", icon: "bi-info-circle-fill" },
          { label: currentLang === "ar" ? "تواصل معنا" : "Contact Support", url: "/contact", icon: "bi-envelope-fill" }
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
    roleSelector = document.getElementById("chatbot-role-selector");
    userAvatarIcon = document.getElementById("chatbot-user-avatar-icon");

    currentLang = detectLanguage();

    // Setup Role Selector Event Listeners
    if (roleSelector) {
      var pills = roleSelector.querySelectorAll(".chatbot-role-pill");
      pills.forEach(function (pill) {
        pill.addEventListener("click", function () {
          var role = pill.getAttribute("data-role");
          setRole(role);
        });
      });
    }

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
