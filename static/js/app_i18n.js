/* Global i18n runtime for non-admin pages. */

class AppI18n {
  constructor() {
    this.supported = ["ar", "en"];
    this.translations = {};
    this.currentLang = this.resolveInitialLanguage();
    this.languageApiStateKey = "kinjo_lang_api_state";
    this.serverLanguageApiState = this.resolveServerLanguageApiState();
    this.literalTranslations = {
      en: {
        "لوحة التحكم": "Dashboard",
        "مسار التنقل": "Breadcrumb",
        إغلاق: "Close",
        إلغاء: "Cancel",
        السابق: "Previous",
        التالي: "Next",
        حفظ: "Save",
        تحديث: "Refresh",
        بحث: "Search",
        عرض: "View",
        الكل: "All",
        الحالة: "Status",
        نشط: "Active",
        "غير نشط": "Inactive",
        "غير محدد": "Not specified",
        خطأ: "Error",
        اليوم: "Today",
        "هذا الأسبوع": "This week",
        "هذا الشهر": "This month",
        "هذا الربع": "This quarter",
        "تاريخ مخصص": "Custom date range",
        "جاري التحميل": "Loading",
        "الحضور والغياب": "Attendance and absence",
        "تقارير الحضور": "Attendance reports",
        "اختيار الروضة": "Select kindergarten",
        "اختيار الشعب": "Select classes",
        "اختيار الأطفال": "Select children",
        "تحديد الفترة": "Select period",
        "البحث بالروضة": "Search kindergarten",
        "اسم الروضة": "Kindergarten name",
        "جميع المحافظات": "All governorates",
        المحافظة: "Governorate",
        عمان: "Amman",
        إربد: "Irbid",
        الزرقاء: "Zarqa",
        العقبة: "Aqaba",
        البلقاء: "Balqa",
        جرش: "Jerash",
        عجلون: "Ajloun",
        مادبا: "Madaba",
        الكرك: "Karak",
        الطفيلة: "Tafilah",
        معان: "Ma'an",
        المفرق: "Mafraq",
        المدينة: "City",
        "رقم الهاتف": "Phone number",
        "اختر روضة": "Select a kindergarten",
        "جميع الشعب في الروضة المحددة": "All classes in selected kindergarten",
        "اختيار شعب محددة": "Select specific classes",
        "جميع الأطفال في الشعب المحددة": "All children in selected classes",
        "اختيار أطفال محددين": "Select specific children",
        "نوع الفترة": "Period type",
        "يوم واحد": "Single day",
        أسبوع: "Week",
        شهر: "Month",
        "فترة مخصصة": "Custom range",
        التاريخ: "Date",
        "من تاريخ": "From date",
        "إلى تاريخ": "To date",
        "إنشاء التقرير": "Generate report",
        "تقرير الحضور": "Attendance report",
        "توزيع الحضور": "Attendance distribution",
        "اتجاه الحضور اليومي": "Daily attendance trend",
        "جدول الحضور التفصيلي": "Detailed attendance table",
        "جاري إنشاء التقرير": "Generating report",
        "فترة التقرير": "Report period",
        "إجمالي الأطفال": "Total children",
        "أيام الدراسة": "School days",
        "معدل الحضور": "Attendance rate",
        "إجمالي الحضور": "Total attendance",
        حاضر: "Present",
        غائب: "Absent",
        "عدد الحاضرين": "Present count",
        الشعبة: "Class",
        الطفل: "Child",
        "تسجيل طفل جديد": "Register new child",
        الروضة: "Kindergarten",
        "بيانات الطفل": "Child information",
        "بيانات الأم": "Mother information",
        "مراجعة البيانات": "Review data",
        "تسجيل طفل في روضة": "Register child in kindergarten",
        "اختر المحافظة ثم المدينة أو ابحث باسم الروضة":
          "Choose governorate then city or search by kindergarten name",
        "عرض التفاصيل": "View details",
        "تغيير الروضة": "Change kindergarten",
        "اختر المحافظة أولاً": "Select governorate first",
        "بحث بالاسم": "Search by name",
        "اكتب اسم الروضة": "Type kindergarten name",
        "مسح عوامل التصفية": "Clear filters",
        "يرجى اختيار الروضة من القائمة": "Please select a kindergarten from the list",
        "اختر المحافظة أو اكتب اسم الروضة للبحث":
          "Select governorate or type kindergarten name to search",
        "يمكنك تصفية النتائج حسب المحافظة والمدينة والاسم":
          "You can filter results by governorate, city, and name",
        "الاسم الأول": "First name",
        "اسم العائلة": "Last name",
        "تاريخ الميلاد": "Date of birth",
        "اسم الأب": "Father name",
        "الاسم الثاني": "Middle name",
        الجنسية: "Nationality",
        "الرقم الوطني": "National ID",
        "رقم جواز السفر": "Passport number",
        الموافقات: "Consents",
        "الموافقات ومصدر الطلب": "Consents and source",
        "الموافقة على المراسلة": "Communication consent",
        "الموافقة على الوسائط": "Media consent",
        "مصدر الطلب": "Request source",
        حضوري: "Walk-in",
        إلكتروني: "Online",
        "تسجيل مدير": "Manager entry",
        "يرجى مراجعة البيانات قبل إرسال الطلب": "Please review data before submitting",
        "أؤكد صحة جميع البيانات المدخلة": "I confirm all entered data is correct",
        "إرسال الطلب": "Submit request",
        "جاري الإرسال": "Submitting",
        "تفاصيل الروضة": "Kindergarten details",
        "رجوع للقائمة": "Back to list",
        "تأكيد اختيار الروضة": "Confirm kindergarten selection",
        نعم: "Yes",
        ذكر: "Male",
        أنثى: "Female",
        أردني: "Jordanian",
        أخرى: "Other",
        "الروضة المخصصة": "Assigned kindergarten",
        "يرجى ملء جميع الحقول المطلوبة": "Please fill all required fields",
        "يرجى تأكيد صحة البيانات": "Please confirm data accuracy",
        "عمر الطفل غير مؤهل للتسجيل": "Child age is not eligible for enrollment",
        "لا يمكن إرسال الطلب: عمر الطفل غير مؤهل":
          "Cannot submit request: child age is not eligible",
        "يوجد طلب تسجيل لهذا الطفل في هذه الروضة بالفعل":
          "An enrollment request already exists for this child in this kindergarten",
        "هذا الطفل مسجل بالفعل في روضة أخرى ولا يمكن تسجيله في أكثر من روضة بنفس الوقت":
          "This child is already enrolled in another kindergarten and cannot be enrolled in more than one at the same time",
        "معلومات الروضة": "Kindergarten information",
        "إدارة الروضات": "Kindergarten management",
        "تعديل المعلومات": "Edit information",
        "البحث والتصفية": "Search and filters",
        "قائمة الروضات": "Kindergarten list",
        الاسم: "Name",
        الموقع: "Location",
        الهاتف: "Phone",
        "صفحات الروضات": "Kindergarten pages",
        "لا توجد روضات": "No kindergartens",
        "لم يتم العثور على أي روضات تطابق معايير البحث":
          "No kindergartens matched the search criteria",
        "عرض الكل": "Show all",
        "غير مصرح لك بالوصول": "Access denied",
        "لا يمكنك الوصول إلى صفحة معلومات الروضة":
          "You cannot access the kindergarten information page",
        "الاسم بالإنجليزية": "English name",
        العنوان: "Address",
        "ساعات العمل": "Working hours",
        الترخيص: "License",
        "ينتهي في": "Valid until",
        "ملخص الأداء": "Performance summary",
        "نسبة الإشغال": "Occupancy rate",
        "تقييم الحوكمة": "Governance score",
        "رضا أولياء الأمور": "Parent satisfaction",
        "الشعب الصفية": "Classrooms",
        "الكادر الإداري والتعليمي": "Administrative and educational staff",
        "الخدمات والمرافق": "Services and facilities",
        "سجل التدقيق": "Audit log",
        "سجل العمليات": "Operations log",
        "سجل العمليات فارغ": "Operations log is empty",
        "إضافة شعبة": "Add class",
        "إضافة شعبة صفية": "Add classroom",
        "إضافة موظف": "Add staff member",
        "إضافة خدمة/مرفق": "Add service/facility",
        "اسم الشعبة": "Class name",
        "اسم الشعبة بالعربية": "Class name (Arabic)",
        "اسم الشعبة بالإنجليزية": "Class name (English)",
        المرحلة: "Level",
        "روضة أولى (المجموعة 1)": "KG1 (Group 1)",
        "روضة ثانية (المجموعة 2)": "KG2 (Group 2)",
        حضانة: "Nursery",
        السعة: "Capacity",
        "السعة القصوى": "Maximum capacity",
        المشرف: "Supervisor",
        "المشرف الحالي": "Current supervisor",
        "اسم المستخدم": "Username",
        "البريد الإلكتروني": "Email",
        الدور: "Role",
        "مدير النظام": "System admin",
        "مدير نظام": "System admin",
        مدير: "Manager",
        "مدير الروضة": "Kindergarten manager",
        مشرف: "Supervisor",
        "مشرف رئيسي": "Lead supervisor",
        معلم: "Teacher",
        "ولي أمر": "Parent",
        "لا يوجد موظفين مسجلين حالياً": "No staff currently registered",
        "لا توجد خدمات أو مرافق مسجلة": "No registered services or facilities",
        الوصف: "Description",
        "اسم الخدمة/المرفق": "Service/facility name",
        "وصف مختصر": "Short description",
        مفعل: "Enabled",
        "تعديل الشعبة الصفية": "Edit classroom",
        "تعيين مشرف للشعبة": "Assign class supervisor",
        "الشعبة الصفية": "Classroom",
        "حفظ التعيينات": "Save assignments",
        "حفظ التغييرات": "Save changes",
        "تاريخ البدء": "Start date",
        "العمر الأدنى (بالأشهر)": "Minimum age (months)",
        "العمر الأقصى (بالأشهر)": "Maximum age (months)",
        "تعذر تحميل الفصول": "Unable to load classes",
        "تعذر تحميل البيانات": "Unable to load data",
        "تم إضافة الشعبة بنجاح": "Class added successfully",
        "تم تحديث الشعبة بنجاح": "Class updated successfully",
        "تم إضافة الخدمة/المرفق بنجاح": "Service/facility added successfully",
        "تم تحديث الخدمة/المرفق بنجاح": "Service/facility updated successfully",
        "تم حذف الخدمة/المرفق بنجاح": "Service/facility deleted successfully",
        "تم تحديث الموظف بنجاح": "Staff updated successfully",
        "تم حذف الموظف بنجاح": "Staff deleted successfully",
        "تم تحديث حالة الموظف بنجاح": "Staff status updated successfully",
        "تم إعادة تعيين كلمة المرور بنجاح": "Password reset successfully",
        "تم تعيين المشرف بنجاح": "Supervisor assigned successfully",
        "تم إعادة تفعيل الشعبة بنجاح": "Class reactivated successfully",
        "حدث خطأ في الاتصال": "Connection error occurred",
        "حدث خطأ في الحذف": "Deletion error occurred",
        "حدث خطأ في التحديث": "Update error occurred",
        "حدث خطأ في الأرشفة": "Archiving error occurred",
        "حدث خطأ أثناء التعيين": "Error occurred during assignment",
        "حدث خطأ في إعادة تعيين كلمة المرور": "Password reset error",
        "فشل الحفظ": "Save failed",
        "فشل التحديث": "Update failed",
        "فشل في الحذف": "Deletion failed",
        "فشل في الأرشفة": "Archiving failed",
        "فشل في التعيين": "Assignment failed",
        "فشل في تحديث الموظف": "Failed to update staff",
        "فشل في تحديث حالة الموظف": "Failed to update staff status",
        "فشل في إعادة تعيين كلمة المرور": "Failed to reset password",
        "نهائياً؟ لا يمكن التراجع عن هذا الإجراء": "Permanently? This action cannot be undone",
        "هل أنت متأكد من حذف هذه الروضة نهائياً؟ لا يمكن التراجع عن هذا الإجراء وستفقد جميع البيانات المرتبطة":
          "Are you sure you want to permanently delete this kindergarten? This cannot be undone and all related data will be lost",
        "هل أنت متأكد من أرشفة هذه الروضة؟ سيتم إخفاؤها من القوائم النشطة ولكن يمكن استعادتها لاحقاً":
          "Are you sure you want to archive this kindergarten? It will be hidden from active lists but can be restored later",
        "هل أنت متأكد من حذف الخدمة/المرفق":
          "Are you sure you want to delete this service/facility",
        "هل أنت متأكد من إلغاء تفعيل الشعبة": "Are you sure you want to deactivate this class",
        "هل أنت متأكد من إلغاء تفعيل الموظف":
          "Are you sure you want to deactivate this staff member",
        "هل أنت متأكد من إعادة تفعيل الموظف":
          "Are you sure you want to reactivate this staff member",
        "هل أنت متأكد من إعادة تعيين كلمة مرور الموظف":
          "Are you sure you want to reset this staff member password",
        "؟ سيتم إرسال كلمة مرور مؤقتة إلى بريده الإلكتروني":
          "? A temporary password will be sent to the email address",
        الرئيسية: "Home",
        "إبلاغ عن حادث": "Report incident",
        إجراء: "Action",
        إجراءات: "Actions",
        الإجراءات: "Actions",
        "إجراءات سريعة": "Quick actions",
        "إجراءات التحسين": "Improvement actions",
        "إجراءات مقترحة للتحسين": "Suggested improvement actions",
        "إجراء سريع غير معرّف": "Unknown quick action",
        "إدارة الحضور": "Manage attendance",
        "إدارة السلامة": "Manage safety",
        "إدارة الفصول": "Class management",
        "إدارة الحسابات": "Account management",
        "إرسال رسالة": "Send message",
        أرشفة: "Archive",
        حذف: "Delete",
        "حذف نهائي": "Permanent delete",
        أعمدة: "Bars",
        خطي: "Line",
        طباعة: "Print",
        تصدير: "Export",
        "تصدير التقرير": "Export report",
        "تصدير خطة العمل": "Export action plan",
        تطبيق: "Apply",
        التسجيل: "Enrollment",
        التقارير: "Reports",
        "التقارير المعلقة": "Pending reports",
        "تقارير معلقة": "Pending reports",
        "تقارير بانتظار المراجعة": "Reports pending review",
        "تقارير الحوادث": "Incident reports",
        "تم قبول طلب تسجيل": "Enrollment request approved",
        "تم العثور على": "Found",
        "تسجيل حضور": "Record attendance",
        "تقرير يومي جديد": "New daily report",
        "طلب تسجيل جديد": "New enrollment request",
        "طلب جديد": "New request",
        "طلبات تسجيل معلقة": "Pending enrollment requests",
        "جاري التحقق": "Checking",
        "تعذر تحميل المحافظات": "Unable to load governorates",
        "تعذر العثور على نافذة تفاصيل التحقق": "Validation details modal was not found",
        "تفاصيل التحقق من البيانات": "Data validation details",
        "جاري تحميل تفاصيل التحقق": "Loading validation details",
        "شرح المؤشرات": "Indicator definitions",
        "شرح المؤشرات: الميزة قيد التطوير": "Indicator explanation: feature under development",
        "شرح مؤشرات الأداء الرئيسية": "KPI definitions",
        "لوحة مؤشرات الأداء الرئيسية": "KPI dashboard",
        "مؤشرات الأداء الرئيسية": "Key performance indicators",
        المؤشر: "Indicator",
        القيمة: "Value",
        "القيمة الحالية": "Current value",
        التقييم: "Rating",
        التوجه: "Trend",
        التنبيهات: "Alerts",
        "التنبيهات الذكية": "Smart alerts",
        الاتجاه: "Trend",
        الحضور: "Attendance",
        الغياب: "Absence",
        "الحوادث المبلغ عنها": "Reported incidents",
        التواصل: "Communication",
        "النشاط الأخير": "Recent activity",
        "إجمالي الروضات": "Total kindergartens",
        "إجمالي الفصول": "Total classes",
        "إجمالي المستخدمين": "Total users",
        "حالة النظام": "System health",
        "امتثال النسبة": "Ratio compliance",
        "أولياء الأمور": "Parents",
        الآباء: "Parents",
        "اسم الوالد": "Parent name",
        "عدد الأطفال": "Children count",
        "الطلاب المسجلين": "Enrolled children",
        المسجلون: "Enrolled",
        الانتظار: "Waitlist",
        الفصل: "Class",
        "اسم الفصل": "Class name",
        المستوى: "Level",
        "تاريخ الإنشاء": "Created at",
        "لا توجد تقارير معلقة": "No pending reports",
        "لا يوجد لديك شعب مخصصة": "You do not have assigned classes",
        "لا توجد شعب صفية مسجلة": "No classrooms registered",
        "غير معين": "Unassigned",
        "غير متوفر": "Unavailable",
        "فشل التعيين": "Assignment failed",
        "فشل في إعادة التفعيل": "Reactivation failed",
        "فشل في حذف الخدمة": "Failed to delete service",
        "فشل في حذف الموظف": "Failed to delete staff member",
        "تم إرسال طلب التسجيل بنجاح": "Enrollment request sent successfully",
        "تمت إضافة الخدمة/المرفق بنجاح": "Service/facility added successfully",
        "تنبيه حرج": "Critical alert",
        "جاري تحميل الإحصائيات": "Loading statistics",
        "جاري تحميل التقارير": "Loading reports",
        "جاري تحميل الفصول": "Loading classes",
        "متابعة التقارير غير المعتمدة مع تحديد الأولوية": "Track unapproved reports with priority",
        "متابعة الغياب المتكرر": "Track recurrent absences",
        "تسريع مراجعة التسجيلات": "Speed up enrollment reviews",
        "راجع الطلبات الآن": "Review requests now",
        "روضتك المسؤول عنها": "Your assigned kindergarten",
        التعريفات: "Definitions",
        إلى: "To",
        "من:": "From:",
        "إلى:": "To:",
        الكادر: "Staff",
        "إعادة تفعيل": "Reactivate",
        "إعادة تعيين كلمة المرور": "Reset password",
        "اختر الأطفال": "Select children",
        "اختر الشعب": "Select classes",
        "إضافة روضة جديدة": "Add new kindergarten",
        الجنس: "Gender",
        "إنشاء تقرير يومي": "Create daily report",
        "تاريخ البداية يجب أن يكون قبل تاريخ النهاية": "Start date must be before end date",
        تعديل: "Edit",
        "تعديل الخدمة/المرفق": "Edit service/facility",
        "تعديل الموظف": "Edit staff",
        روضة: "Kindergarten",
        "فصل جديد": "New class",
        "قيد المراجعة": "Under review",
        مراجعة: "Review",
        "مراجعة الطلبات": "Review requests",
        مسح: "Clear",
        مسودة: "Draft",
        "معدل الحوادث": "Incident rate",
        معطل: "Disabled",
        "من أصل": "out of",
        "مؤشر إيجابي": "Positive indicator",
        "مؤشرات حرجة": "Critical indicators",
        "مؤشرات ممتازة": "Excellent indicators",
        موقوف: "Suspended",
        "نظرة عامة على الروضات": "Kindergartens overview",
        "نظرة عامة على الفصول": "Classes overview",
        "نظرة عامة على النظام": "System overview",
        "هناك 5 طلبات تنتظر المراجعة منذ أكثر من يومين":
          "There are 5 requests pending review for more than two days",
        "والد جديد": "New parent",
        "وصول سريع": "Quick access",
        "يحتاج تحسين": "Needs improvement",
        "يرجى اختيار روضة": "Please select a kindergarten",
        "يرجى اختيار شعبة واحدة على الأقل": "Please select at least one class",
        "يرجى تحديد تاريخ البداية والنهاية": "Please select start and end dates",
        "أحمد محمد - منذ 5 دقائق": "Ahmad Mohammad - 5 minutes ago",
        "سارة أحمد - منذ 15 دقيقة": "Sara Ahmad - 15 minutes ago",
        "طفل - منذ 30 دقيقة": "15 children - 30 minutes ago",
        "مثال: الفراشات": "Example: Butterflies",
        "مثال: ساحة ألعاب خارجية": "Example: Outdoor playground",
        "إحصائيات المشرفين": "Supervisor statistics",
        "إدارة التقارير اليومية": "Daily report management",
        "إدارة المشرفين وأولياء الأمور مع وصول سريع للمراسلة":
          "Manage supervisors and parents with quick messaging access",
        "اختيار نطاق التاريخ": "Select date range",
        "استغلال السعة": "Capacity utilization",
        "افحص تقرير الحضور": "Check attendance report",
        "الأطفال المسجلون": "Enrolled children",
        "التقارير اليومية": "Daily reports",
        "التقارير اليومية المعلقة": "Pending daily reports",
        الحاضرون: "Present",
        "الحالة الآن": "Current status",
        "الحالة التقديرية": "Estimated status",
        "الحضور اليوم": "Today's attendance",
        "الحضور اليومي": "Daily attendance",
        "الروضات النشطة": "Active kindergartens",
        الغائبون: "Absent",
        المشرفون: "Supervisors",
        "المشرفون النشطون": "Active supervisors",
        "تاريخ البداية يجب أن يكون قبل تاريخ النهاية.": "Start date must be before end date.",
        "تحديث البيانات": "Refresh data",
        "تحديث بيانات لوحة التحكم": "Refresh dashboard data",
        "تسجيل حضور اليوم": "Record today's attendance",
        "تصدير لوحة التحكم": "Export dashboard",
        "تم رصد تراجع في حضور الأطفال هذا الأسبوع بنسبة 4%.":
          "A 4% decline in child attendance was detected this week.",
        "جاري التحقق...": "Verifying...",
        "جاري التحميل...": "Loading...",
        "جاري تحميل الإحصائيات...": "Loading statistics...",
        "جاري تحميل التقارير...": "Loading reports...",
        "جاري تحميل الفصول...": "Loading classes...",
        "جاري تحميل تفاصيل التحقق...": "Loading validation details...",
        "حالات التسجيل": "Enrollment statuses",
        "طباعة لوحة التحكم": "Print dashboard",
        "عرض البطاقات": "Card view",
        "عرض الجدول": "Table view",
        "عرض الرسم البياني كأعمدة": "Show chart as bars",
        "عرض الرسم البياني كخط": "Show chart as line",
        "عرض السجل الكامل": "View full log",
        "عرض السجل الكامل للنشاط": "View full activity log",
        "عرض تفاصيل التحقق من البيانات": "View data validation details",
        "عرض تفاصيل مؤشرات الأداء الرئيسية": "View KPI details",
        "عرض جميع التقارير": "View all reports",
        "عرض جميع التقارير اليومية": "View all daily reports",
        "قراءة سريعة لنشاط المشرفين ومعدل التفعيل":
          "Quick read of supervisor activity and activation rate",
        "متابعة السعة والاستيعاب لكل فصل في الوقت الفعلي":
          "Monitor class capacity and occupancy in real time",
        "مراجعة التقارير": "Review reports",
        "مراجعة طلبات التسجيل": "Review enrollment requests",
        "مشرف جديد": "New supervisor",
        "من إجمالي الأطفال": "of total children",
        "ميزة التاريخ المخصص قيد التطوير": "Custom date feature is under development",
        "نسبة الحضور": "Attendance rate",
        "نسبة الحضور الأسبوعية": "Weekly attendance rate",
        "نظرة عامة على الروضات -": "Kindergartens overview -",
        "نظرة عامة على اليوم -": "Today's overview -",
        "هناك 5 طلبات تنتظر المراجعة منذ أكثر من يومين.":
          "There are 5 requests pending review for more than two days.",
        "وصول سريع:": "Quick access:",
        "يحتاج إجراء": "Action required",
        "يرجى تحديد تاريخ البداية والنهاية.": "Please select start and end dates.",
        "اختر الأطفال:": "Select children:",
        "اختر الشعب:": "Select classes:",
        "اختر روضة...": "Select a kindergarten...",
        "اسم الروضة...": "Kindergarten name...",
        "التالي: اختيار الأطفال": "Next: select children",
        "التالي: اختيار الشعب": "Next: select classes",
        "التالي: تحديد الفترة": "Next: select period",
        "تقرير الحضور -": "Attendance report -",
        "جاري إنشاء التقرير...": "Generating report...",
        "خطأ في إنشاء التقرير": "Error generating report",
        "خطأ في البحث عن الروضات": "Error searching kindergartens",
        "خطأ في تحميل الأطفال": "Error loading children",
        "خطأ في تحميل الشعب": "Error loading classes",
        "رقم الهاتف...": "Phone number...",
        "روضتك المسؤول عنها:": "Your assigned kindergarten:",
        "ستعمل جميع العمليات على هذه الروضة فقط": "All actions will run only for this kindergarten",
        "لا يوجد لديك شعب مخصصة. تواصل مع المدير.":
          "You have no assigned classes. Contact the manager.",
        "لم يتم العثور على روضات مطابقة": "No matching kindergartens found",
        "أدخل سبب القرار...": "Enter decision reason...",
        "اسم الطفل": "Child name",
        "الروضة:": "Kindergarten:",
        السبب: "Reason",
        "الطفل:": "Child:",
        القرار: "Decision",
        انتظار: "Waiting",
        "بحث...": "Search...",
        "تاريخ التقديم": "Submission date",
        "تم حفظ القرار بنجاح": "Decision saved successfully",
        "جاري تحضير الملف للتصدير...": "Preparing file for export...",
        "حدث خطأ": "An error occurred",
        "حدث خطأ في تحميل البيانات": "Error loading data",
        رفض: "Reject",
        "طلبات التسجيل": "Enrollment requests",
        قبول: "Accept",
        "لا توجد طلبات تسجيل": "No enrollment requests",
        "مراجعة طلب التسجيل": "Review enrollment request",
        مرفوض: "Rejected",
        معلق: "Pending",
        مقبول: "Accepted",
        "ولي الأمر": "Parent",
        "ولي الأمر:": "Parent:",
        "يجب تسجيل الدخول أولاً": "Sign-in required first",
        "البحث بالاسم...": "Search by name...",
        "البحث بالمدينة...": "Search by city...",
        "حالة الروضة": "Kindergarten status",
        "رقم الترخيص": "License number",
        "عرض التفاصيل الكاملة": "View full details",
        "؟ سيتم إخفاؤها من القوائم النشطة.": "? It will be hidden from active lists.",
        "؟ سيتم إرسال كلمة مرور مؤقتة إلى بريده الإلكتروني.":
          "? A temporary password will be sent to the email address.",
        "إلغاء تفعيل": "Deactivate",
        "اختر مشرف...": "Select supervisor...",
        "العناصر المعطلة تمثل المشرفين المعينين مسبقاً":
          "Disabled items represent already assigned supervisors",
        "تظهر بجانب كل مشرف الشعبة المعينة إن كان معيناً بالفعل، والمشرفون غير المتاحين يتم تعطيلهم.":
          "Each supervisor shows the assigned class when already assigned, and unavailable supervisors are disabled.",
        "حدث خطأ في إعادة التفعيل": "Error reactivating",
        "حدث خطأ في إلغاء التفعيل": "Error deactivating",
        "حدث خطأ في تحديث الموظف": "Error updating staff member",
        "حدث خطأ في تحديث حالة الموظف": "Error updating staff status",
        "حدث خطأ في حذف الخدمة": "Error deleting service",
        "حدث خطأ في حذف الموظف": "Error deleting staff member",
        "حفظ التعيين": "Save assignment",
        "خطأ في تحميل البيانات": "Error loading data",
        "خطأ:": "Error:",
        "فشل في إلغاء التفعيل": "Failed to deactivate",
        "لا يوجد مشرفين متاحين": "No supervisors available",
        "نهائياً؟ لا يمكن التراجع عن هذا الإجراء.": "Permanently? This action cannot be undone.",
        "هل أنت متأكد من أرشفة هذه الروضة؟ سيتم إخفاؤها من القوائم النشطة ولكن يمكن استعادتها لاحقاً.":
          "Are you sure you want to archive this kindergarten? It will be hidden from active lists but can be restored later.",
        "هل أنت متأكد من حذف الشعبة": "Are you sure you want to delete the class",
        "هل أنت متأكد من حذف الموظف": "Are you sure you want to delete the staff member",
        "هل أنت متأكد من حذف هذه الروضة نهائياً؟ لا يمكن التراجع عن هذا الإجراء وستفقد جميع البيانات المرتبطة.":
          "Are you sure you want to permanently delete this kindergarten? This cannot be undone and all related data will be lost.",
        "والنص التالي يوضح الشعبة المعينة.": "The following text indicates the assigned class.",
        "ينتهي في:": "Expires on:",
        "أعلى 5 روضات أداءً": "Top 5 performing kindergartens",
        "إجراءات مقترحة للتحسين:": "Suggested improvement actions:",
        "إرسال التقارير": "Report submission",
        "إعادة المحاولة": "Retry",
        "اتجاه الحوادث والتبليغات": "Incidents and reporting trend",
        "اتجاه تسجيلات الأطفال": "Child enrollment trend",
        "اتجاه نسبة الحضور": "Attendance rate trend",
        "اكتمال التدريب": "Training completion",
        الأداء: "Performance",
        "الاستيعاب والتحققات": "Capacity and validations",
        "البيانات المستلمة غير صالحة للعرض.": "Received data is not valid for display.",
        "البيانات مقصورة على الروضة المرتبطة بك.": "Data is limited to your assigned kindergarten.",
        "التصنيف والمقارنات": "Classification and benchmarking",
        التغطية: "Coverage",
        "الحوادث الخطرة": "Serious incidents",
        الروضات: "Kindergartens",
        "الروضات الأكثر حاجة للدعم": "Kindergartens most in need of support",
        "الروضة الخاصة بك": "Your kindergarten",
        "الروضة المرتبطة بالمدير لا يمكن تغييرها.":
          "The manager-linked kindergarten cannot be changed.",
        العدد: "Count",
        "الغياب المزمن": "Chronic absence",
        "المتبقي للوصول للهدف": "Remaining to reach target",
        المنطقة: "Area",
        "النسبة المئوية للأطفال الحاضرين من إجمالي المسجلين.":
          "Percentage of present children out of total enrolled.",
        "انتظار البيانات...": "Waiting for data...",
        "بيانات ناقصة": "Incomplete data",
        "تاريخ البداية يجب أن يكون قبل أو يساوي تاريخ النهاية.":
          "Start date must be before or equal to end date.",
        "تحسين التواصل مع أولياء الأمور": "Improve communication with parents",
        "تحسين معدل الالتزام بالتقارير": "Improve report compliance rate",
        "تحليل شامل لأداء الروضة، معايير الجودة، ومعدلات السلامة والالتزام.":
          "Comprehensive analysis of kindergarten performance, quality standards, and safety/compliance rates.",
        "تسجيلات جديدة": "New enrollments",
        "تعذر التواصل مع الخادم.": "Unable to reach server.",
        "تعذر تحميل عوامل التصفية": "Failed to load filters",
        "تعذر تصدير البيانات": "Failed to export data",
        "تعذر تطبيق المرشحات": "Failed to apply filters",
        "تعذر تهيئة الرسوم البيانية: عناصر الرسم غير متوفرة.":
          "Failed to initialize charts: chart elements unavailable.",
        "تعذر جلب إعدادات عناصر اللوحة": "Failed to fetch widget settings",
        "تغير مؤشر الحوكمة": "Governance indicator change",
        "تم تجاهل رسالة فورية غير صالحة.": "Ignored invalid realtime message.",
        "تم تحديث البيانات": "Data updated",
        "تم تطبيق المرشحات": "Filters applied",
        تنبيه: "Alert",
        "تنبيهات الأداء:": "Performance alerts:",
        "تنبيهات النظام": "System alerts",
        "توزيع الطلاب حسب سنة الميلاد": "Student distribution by birth year",
        "جارٍ تحليل البيانات لتقديم التوصيات...": "Analyzing data to provide recommendations...",
        "جارٍ تطبيق المرشحات...": "Applying filters...",
        "جارٍ جلب البيانات...": "Fetching data...",
        "جميع المدن": "All cities",
        "جميع المناطق": "All areas",
        جيد: "Good",
        روضتي: "My kindergarten",
        "زيادة معدل الدورات التدريبية": "Increase training completion rate",
        ضعيف: "Weak",
        "عدد الحوادث البسيطة لكل 100 طفل في اليوم.":
          "Number of minor incidents per 100 children per day.",
        "عدد الحوادث الجسيمة التي تتطلب تدخل إجراء فورياً.":
          "Number of severe incidents requiring immediate action.",
        "عرض مؤشرات الروضة المرتبطة بالمدير فقط":
          "Show metrics for manager-linked kindergarten only",
        "فشل في تصدير البيانات": "Data export failed",
        "كفاءة الطاقة الاستيعابية": "Capacity efficiency",
        "لا توجد بيانات": "No data",
        "لا توجد بيانات ضمن الفترة المحددة": "No data for the selected period",
        "لا يوجد توزيع متاح حالياً": "No distribution currently available",
        "لوحة مؤشرات الأداء": "KPI dashboard",
        "لوحة مؤشرات الأداء والحوكمة": "KPI and governance dashboard",
        "مؤشر الحوكمة والتجربة": "Governance and experience index",
        "مؤشرات الأداء": "KPIs",
        "مؤشرات السلامة والمخاطر": "Safety and risk indicators",
        "مؤشرات العمليات والجودة": "Operations and quality indicators",
        "متابعة الحوادث": "Incident follow-up",
        "مخطط توزيع الطلاب حسب الروضات": "Student distribution by kindergarten chart",
        "مدى الالتزام بنسبة (معلم لكل عدد معين من الطلاب) حسب المعايير.":
          "Compliance with ratio standards (teacher per defined number of students).",
        "مدى الانتظام في إرسال التقارير اليومية والأسبوعية لرئاسة الروضة.":
          "Consistency in submitting daily and weekly reports to management.",
        "مدى سرعة إغلاق ومتابعة البلاغات خلال الوقت المتفق عليه.":
          "Speed of closing and following up reports within agreed time.",
        "مراجعة إجراءات السلامة المتبعة": "Review applied safety procedures",
        "معيار الجودة": "Quality standard",
        "معيار شامل يقيس جودة العمليات، الالتزام بالتقارير، السلامة، وتجربة الأطفال والمدراء. المدى من 0 إلى 100.":
          "Comprehensive metric measuring operations quality, report compliance, safety, and child/manager experience. Range 0-100.",
        "ملء الشاشة": "Fullscreen",
        ممتاز: "Excellent",
        "نسبة إتمام الدورات التدريبية الإلزامية للكادر التعليمي.":
          "Completion rate of mandatory training for teaching staff.",
        "نسبة الأطفال الذين غابوا أكثر من 10% من إجمالي أيام الدراسة.":
          "Percentage of children absent more than 10% of total school days.",
        "نسبة الأطفال المسجلين حالياً مقارنة بالسعة القصوى المرخصة للروضة.":
          "Percentage of currently enrolled children relative to licensed maximum capacity.",
        "نسبة الالتزام": "Compliance rate",
        "نسبة التغطية": "Coverage rate",
        "نظرة عامة على مستوى التميز في إدارة الروضة.":
          "Overview of excellence level in kindergarten management.",
        "يرجى اختيار تاريخ بداية ونهاية.": "Please select start and end dates.",
        "يعبر هذا المؤشر عن الكفاءة الشاملة للروضة.":
          "This indicator reflects overall kindergarten efficiency.",
        "يوضح هذا المؤشر مدى استغلال المقاعد المتوفرة في الروضة.":
          "This indicator shows how effectively available seats are utilized.",
        "يوم - 4 سنوات و 8 أشهر)": "day - 4 years and 8 months)",
      },
    };
    this.literalTranslationEntries = {
      en: Object.entries(this.literalTranslations.en).sort((a, b) => b[0].length - a[0].length),
    };
    this.literalObserver = null;
    this.isApplyingLiteral = false;
    this.runtimePatchesApplied = false;
    this.chartTranslationPluginRegistered = false;
    this.dynamicLiteralPairsLoaded = false;
    this.dynamicLiteralPairsPromise = null;
    this.dynamicLiteralPairsPreloadScheduled = false;
    this.literalCacheVersion = "2026-02-18-v2";
    this.literalCacheKey = `kinjo_literal_pairs_${this.literalCacheVersion}`;
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

  resolveInitialLanguage() {
    const stored = localStorage.getItem("kinjo_lang");
    if (stored && this.supported.includes(stored)) {
      return stored;
    }
    const cookieMatch = document.cookie.match(/(?:^|;\s*)kinjo_lang=(ar|en)(?:;|$)/i);
    const cookieLang = cookieMatch ? cookieMatch[1].toLowerCase() : "";
    if (cookieLang && this.supported.includes(cookieLang)) {
      return cookieLang;
    }
    const htmlLang = document.documentElement.lang || "ar";
    return this.supported.includes(htmlLang) ? htmlLang : "ar";
  }

  resolveAuthToken() {
    return localStorage.getItem("kinjo_token") || sessionStorage.getItem("kinjo_token") || "";
  }

  async loadServerLanguagePreference() {
    try {
      const token = this.resolveAuthToken();
      if (!token || this.serverLanguageApiState === "missing") {
        return null;
      }
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await fetch("/api/users/me/language", {
        method: "GET",
        headers,
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
      return this.supported.includes(userLang) ? userLang : null;
    } catch (_error) {
      return null;
    }
  }

  async persistServerLanguagePreference(lang) {
    try {
      const token = this.resolveAuthToken();
      if (!token || this.serverLanguageApiState === "missing") {
        return;
      }
      const headers = { "Content-Type": "application/json" };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const response = await fetch("/api/users/me/language", {
        method: "PUT",
        headers,
        credentials: "same-origin",
        keepalive: true,
        body: JSON.stringify({ user_lang: lang }),
      });
      if (response.status === 404) {
        this.setServerLanguageApiState("missing");
        return;
      }
      if (response.ok) {
        this.setServerLanguageApiState("available");
      }
    } catch (_error) {
      // Ignore persistence failure and keep client-side preference.
    }
  }

  persistClientLanguage(lang) {
    const safeLang = this.supported.includes(lang) ? lang : "ar";
    localStorage.setItem("kinjo_lang", safeLang);
    localStorage.setItem("admin_language", safeLang);
    document.cookie = `kinjo_lang=${safeLang}; path=/; max-age=31536000; SameSite=Lax`;
  }

  async loadLanguage(lang) {
    if (this.translations[lang]) {
      return this.translations[lang];
    }
    try {
      const response = await fetch(`/static/i18n/app_${lang}.json`, { cache: "force-cache" });
      if (!response.ok) {
        throw new Error(`Failed to load app_${lang}.json`);
      }
      const data = await response.json();
      this.translations[lang] = data || {};
      return this.translations[lang];
    } catch (_error) {
      this.translations[lang] = {};
      return {};
    }
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

    // Add tolerant variants for common punctuation suffixes.
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

  ingestCatalogLiteralPairs(arCatalog, enCatalog) {
    const flatAr = this.flattenTranslationMap(arCatalog);
    const flatEn = this.flattenTranslationMap(enCatalog);
    Object.keys(flatAr).forEach((key) => {
      this.addLiteralTranslationPair(flatAr[key], flatEn[key] || "");
    });
  }

  rebuildLiteralTranslationEntries() {
    this.literalTranslationEntries = {
      en: Object.entries(this.literalTranslations.en).sort((a, b) => b[0].length - a[0].length),
    };
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
      this.rebuildLiteralTranslationEntries();
      this.dynamicLiteralPairsLoaded = true;
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
      const data = await response.json();
      return data || {};
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
          // Ignore literal harvest failures to avoid blocking i18n startup.
        }
      })
    );

    document.querySelectorAll("script:not([src])").forEach((script) => {
      this.ingestLiteralPairsFromSource(script.textContent || "");
    });
  }

  async loadDynamicLiteralPairs() {
    if (this.dynamicLiteralPairsLoaded) {
      return;
    }
    if (this.dynamicLiteralPairsPromise) {
      return this.dynamicLiteralPairsPromise;
    }

    this.dynamicLiteralPairsPromise = (async () => {
      if (this.restoreLiteralPairsCache()) {
        return;
      }
      this.ingestCatalogLiteralPairs(this.translations.ar || {}, this.translations.en || {});

      const [adminAr, adminEn] = await Promise.all([
        this.loadJsonCatalog("/static/i18n/admin_ar.json"),
        this.loadJsonCatalog("/static/i18n/admin_en.json"),
      ]);
      this.ingestCatalogLiteralPairs(adminAr, adminEn);

      const [literalOverrides, literalQualityOverrides] = await Promise.all([
        this.loadJsonCatalog("/static/i18n/literal_en_overrides.json"),
        this.loadJsonCatalog("/static/i18n/literal_en_quality_overrides.json"),
      ]);

      Object.entries(literalOverrides || {}).forEach(([arText, enText]) => {
        this.addLiteralTranslationPair(arText, enText);
      });
      Object.entries(literalQualityOverrides || {}).forEach(([arText, enText]) => {
        this.addLiteralTranslationPair(arText, enText);
      });

      await this.loadScriptLiteralPairs();
      this.rebuildLiteralTranslationEntries();
      this.dynamicLiteralPairsLoaded = true;
      this.persistLiteralPairsCache();
    })();

    try {
      await this.dynamicLiteralPairsPromise;
    } finally {
      this.dynamicLiteralPairsPromise = null;
    }
  }

  scheduleDynamicLiteralPairsBuild() {
    if (this.dynamicLiteralPairsLoaded || this.dynamicLiteralPairsPreloadScheduled) {
      return;
    }

    this.dynamicLiteralPairsPreloadScheduled = true;
    const run = () => {
      this.dynamicLiteralPairsPreloadScheduled = false;
      this.loadDynamicLiteralPairs()
        .then(() => {
          if (this.currentLang === "en") {
            this.translateDocument();
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

  async init() {
    await Promise.all([this.loadLanguage("ar"), this.loadLanguage("en")]);
    const serverLang = await this.loadServerLanguagePreference();
    if (serverLang) {
      this.currentLang = serverLang;
      this.persistClientLanguage(serverLang);
    }
    this.patchRuntimeTranslators();
    await this.applyLanguage(this.currentLang, false);
    if (this.currentLang === "en") {
      this.scheduleDynamicLiteralPairsBuild();
    }
  }

  t(key, fallbackValue = "") {
    if (!key) {
      return "";
    }
    const current = this.translations[this.currentLang] || {};
    const translated = current[key];
    if (typeof translated === "string" && translated.trim()) {
      return translated;
    }
    if (typeof fallbackValue === "string" && fallbackValue.trim()) {
      return fallbackValue;
    }
    return key;
  }

  translateDocument() {
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      const key = element.getAttribute("data-i18n");
      if (!key) {
        return;
      }
      const existingText = element.textContent || "";
      const translated = this.t(key, existingText);
      if (translated !== existingText) {
        element.textContent = translated;
      }
    });

    document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      const key = element.getAttribute("data-i18n-placeholder");
      if (!key) {
        return;
      }
      const currentValue = element.getAttribute("placeholder") || "";
      const translated = this.t(key, currentValue);
      if (translated !== currentValue) {
        element.setAttribute("placeholder", translated);
      }
    });

    document.querySelectorAll("[data-i18n-title]").forEach((element) => {
      const key = element.getAttribute("data-i18n-title");
      if (!key) {
        return;
      }
      const currentValue = element.getAttribute("title") || "";
      const translated = this.t(key, currentValue);
      if (translated !== currentValue) {
        element.setAttribute("title", translated);
      }
    });

    document.querySelectorAll("[data-i18n-aria]").forEach((element) => {
      const key = element.getAttribute("data-i18n-aria");
      if (!key) {
        return;
      }
      const currentValue = element.getAttribute("aria-label") || "";
      const translated = this.t(key, currentValue);
      if (translated !== currentValue) {
        element.setAttribute("aria-label", translated);
      }
    });

    if (document.title) {
      document.title = this.replaceLiteralSegments(document.title);
    }

    this.translateLiteralText();
    this.ensureAccessibilityLabels();
  }

  shouldApplyLiteralTranslation() {
    return this.currentLang === "en";
  }

  replaceLiteralSegments(value) {
    if (!value || this.currentLang !== "en") {
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
    if (!this.shouldApplyLiteralTranslation()) {
      return;
    }
    if (this.isApplyingLiteral) {
      return;
    }
    this.isApplyingLiteral = true;

    try {
      const disallowedTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT"]);
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => {
          const parentTag = node.parentElement?.tagName;
          if (!node.nodeValue || !parentTag || disallowedTags.has(parentTag)) {
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
        const updated = this.replaceLiteralSegments(node.nodeValue);
        if (updated !== node.nodeValue) {
          node.nodeValue = updated;
        }
      });

      ["placeholder", "title", "aria-label"].forEach((attributeName) => {
        document.querySelectorAll(`[${attributeName}]`).forEach((element) => {
          if (
            element.hasAttribute(
              `data-i18n-${attributeName === "aria-label" ? "aria" : attributeName}`
            )
          ) {
            return;
          }
          const currentValue = element.getAttribute(attributeName);
          const updatedValue = this.replaceLiteralSegments(currentValue);
          if (updatedValue && updatedValue !== currentValue) {
            element.setAttribute(attributeName, updatedValue);
          }
        });
      });
    } finally {
      this.isApplyingLiteral = false;
    }
  }

  startLiteralObserver() {
    if (this.literalObserver) {
      this.literalObserver.disconnect();
      this.literalObserver = null;
    }
    if (!this.shouldApplyLiteralTranslation() || !document.body) {
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

  translateObjectLiterals(value, visited = new WeakSet()) {
    if (typeof value === "string") {
      return this.replaceLiteralSegments(value);
    }
    if (!value || typeof value !== "object") {
      return value;
    }
    if (visited.has(value)) {
      return value;
    }
    visited.add(value);

    if (Array.isArray(value)) {
      for (let index = 0; index < value.length; index += 1) {
        value[index] = this.translateObjectLiterals(value[index], visited);
      }
      return value;
    }

    Object.keys(value).forEach((key) => {
      value[key] = this.translateObjectLiterals(value[key], visited);
    });
    return value;
  }

  registerChartLiteralPlugin() {
    const chartLib = window.Chart;
    if (
      !chartLib ||
      typeof chartLib.register !== "function" ||
      this.chartTranslationPluginRegistered
    ) {
      return;
    }
    const appI18n = this;
    chartLib.register({
      id: "kinjoLiteralI18n",
      beforeInit(chart) {
        if (appI18n.currentLang !== "en") {
          return;
        }
        appI18n.translateObjectLiterals(chart.data);
        appI18n.translateObjectLiterals(chart.options);
      },
      beforeUpdate(chart) {
        if (appI18n.currentLang !== "en") {
          return;
        }
        appI18n.translateObjectLiterals(chart.data);
        appI18n.translateObjectLiterals(chart.options);
      },
    });
    this.chartTranslationPluginRegistered = true;
  }

  translateExistingCharts() {
    const chartLib = window.Chart;
    if (!chartLib || typeof chartLib.getChart !== "function" || this.currentLang !== "en") {
      return;
    }
    document.querySelectorAll("canvas").forEach((canvas) => {
      const chart = chartLib.getChart(canvas);
      if (!chart) {
        return;
      }
      this.translateObjectLiterals(chart.data);
      this.translateObjectLiterals(chart.options);
      chart.update("none");
    });
  }

  patchRuntimeTranslators() {
    this.registerChartLiteralPlugin();

    const swal = window.Swal;
    if (
      swal &&
      typeof swal.fire === "function" &&
      typeof swal.showValidationMessage === "function" &&
      !swal.__kinjoLiteralI18nPatched
    ) {
      const originalFire = swal.fire.bind(swal);
      const originalShowValidationMessage = swal.showValidationMessage.bind(swal);
      const appI18n = this;

      swal.fire = (...args) => {
        if (appI18n.currentLang !== "en") {
          return originalFire(...args);
        }
        const translatedArgs = args.map((arg) => appI18n.translateObjectLiterals(arg));
        return originalFire(...translatedArgs);
      };

      swal.showValidationMessage = (message) =>
        originalShowValidationMessage(appI18n.replaceLiteralSegments(message));

      swal.__kinjoLiteralI18nPatched = true;
    }

    this.runtimePatchesApplied = true;
  }

  ensureAccessibilityLabels() {
    const controls = document.querySelectorAll("input, select, textarea");
    controls.forEach((element) => {
      const inputType = (element.getAttribute("type") || "").toLowerCase();
      if (["hidden", "submit", "button", "image", "reset"].includes(inputType)) {
        return;
      }
      if (element.hasAttribute("aria-label") || element.hasAttribute("aria-labelledby")) {
        return;
      }

      let labelText = "";
      const controlId = element.getAttribute("id");
      if (controlId) {
        const escapedId = controlId.replace(/"/g, '\\"');
        const explicitLabel = document.querySelector(`label[for="${escapedId}"]`);
        if (explicitLabel && explicitLabel.textContent) {
          labelText = explicitLabel.textContent;
        }
      }

      if (!labelText) {
        const wrappedLabel = element.closest("label");
        if (wrappedLabel && wrappedLabel.textContent) {
          labelText = wrappedLabel.textContent;
        }
      }

      if (!labelText) {
        labelText = element.getAttribute("placeholder") || "";
      }
      if (!labelText) {
        labelText = element.getAttribute("name") || "";
      }
      if (!labelText) {
        labelText = controlId || "field";
      }

      const normalized = labelText.replace(/\s+/g, " ").trim();
      if (normalized) {
        element.setAttribute("aria-label", normalized);
      }
    });
  }

  updateBootstrapDirection(lang) {
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
    bootstrapLink.setAttribute("href", lang === "ar" ? rtlHref : ltrHref);
    const rtlIntegrity = bootstrapLink.dataset.rtlIntegrity || "";
    const ltrIntegrity = bootstrapLink.dataset.ltrIntegrity || "";
    const targetIntegrity = lang === "ar" ? rtlIntegrity : ltrIntegrity;
    if (targetIntegrity) {
      bootstrapLink.setAttribute("integrity", targetIntegrity);
    }
  }

  setHtmlLanguage(lang) {
    const safeLang = this.supported.includes(lang) ? lang : "ar";
    this.currentLang = safeLang;
    document.documentElement.lang = safeLang;
    document.documentElement.dir = safeLang === "ar" ? "rtl" : "ltr";
    this.updateBootstrapDirection(safeLang);
    this.persistClientLanguage(safeLang);
  }

  async applyLanguage(lang, persist = true) {
    await this.loadLanguage(lang);
    this.setHtmlLanguage(lang);
    this.patchRuntimeTranslators();
    if (persist) {
      await this.persistServerLanguagePreference(this.currentLang);
    }
    this.translateDocument();
    this.startLiteralObserver();
    this.translateExistingCharts();
    if (this.currentLang === "en") {
      this.scheduleDynamicLiteralPairsBuild();
    }
  }

  async toggleLanguage() {
    const nextLang = this.currentLang === "ar" ? "en" : "ar";
    this.setHtmlLanguage(nextLang);
    this.persistServerLanguagePreference(nextLang);
    window.location.reload();
  }
}

window.AppI18n = new AppI18n();

document.addEventListener("DOMContentLoaded", () => {
  window.AppI18n.init();
});
