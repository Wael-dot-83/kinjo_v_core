/* Parent module i18n helpers for dynamic UI text. */

const parentI18n = {
  en: {
    confirmDelete: "Are you sure?",
    saveSuccess: "Saved successfully",
    errorOccurred: "An error occurred",
    loading: "Loading...",
    noData: "No data found",
    present: "Present",
    absent: "Absent",
    late: "Late",
    pending: "Pending",
    approved: "Approved",
    rejected: "Rejected",
  },
  ar: {
    confirmDelete: "هل أنت متأكد؟",
    saveSuccess: "تم الحفظ بنجاح",
    errorOccurred: "حدث خطأ",
    loading: "جاري التحميل...",
    noData: "لا توجد بيانات",
    present: "حاضر",
    absent: "غائب",
    late: "متأخر",
    pending: "قيد الانتظار",
    approved: "موافق",
    rejected: "مرفوض",
  },
};

function parentLang() {
  return document.documentElement.lang === "en" ? "en" : "ar";
}

function parentT(key) {
  const lang = parentLang();
  return parentI18n[lang]?.[key] || parentI18n.en[key] || key;
}

function parentLocalDate(value) {
  if (!value) return "";
  const date = new Date(value);
  const locale = parentLang() === "ar" ? "ar-JO-u-nu-arab" : "en-US";
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function parentLocalNumber(value) {
  return new Intl.NumberFormat(parentLang() === "ar" ? "ar-JO-u-nu-arab" : "en-US").format(value);
}

window.parentI18n = parentI18n;
window.parentT = parentT;
window.parentLocalDate = parentLocalDate;
window.parentLocalNumber = parentLocalNumber;
