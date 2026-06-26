def generate_government_report(dim_name: str, z_scores: dict, adv_data: dict, demographics: dict) -> dict:
    """
    Intelligent Heuristics Engine to generate official Arabic government reports
    based on raw mathematical data (Correlations, Z-Scores, Trends).
    """
    
    # 1. SUMMARY
    total_children = demographics.get("total_children", 0)
    total_kgs = demographics.get("total_kgs", 0)
    gov_z = z_scores.get("governance", 0.0)
    att_z = z_scores.get("attendance", 0.0)
    
    if gov_z > 1.0:
        gov_status = "تتفوق بشكل استثنائي على المعدل الوطني"
    elif gov_z > 0:
        gov_status = "أداء أعلى من المعدل الوطني"
    elif gov_z > -1.0:
        gov_status = "أداء مقبول يقارب المعدل الوطني"
    else:
        gov_status = "أداء حرج وأقل بكثير من المعدل الوطني"

    summary = f"بناءً على التحليل العميق للبيانات، يضم مستوى ({dim_name}) إجمالي {total_children} طفل موزعين على {total_kgs} حضانة نشطة. من الناحية الإدارية والتشغيلية، يظهر هذا المستوى {gov_status} (بمؤشر انحراف معياري {gov_z:.2f})."

    # 2. CORRELATIONS
    correlation_text = []
    staff_corr = adv_data.get("staffing_quality_correlation", 0.0)
    if staff_corr > 0.6:
        correlation_text.append(f"تم اكتشاف ترابط إحصائي خطير ({staff_corr:.2f}) بين نقص الكوادر وارتفاع معدل الحوادث. هذا يثبت أن الحضانات في هذا القطاع تعاني من ضغط تشغيلي يؤدي مباشرة لضعف السلامة.")
    elif staff_corr < -0.5:
        correlation_text.append(f"توجد علاقة عكسية قوية ({staff_corr:.2f}) تدل على أن توفير الكوادر بشكل جيد يساهم بشكل مباشر في رفع جودة الحوكمة.")
    else:
        correlation_text.append("معدلات التوظيف مقابل الحوادث تبدو طبيعية ولا تشكل ارتباطاً يشير إلى الخطر.")

    att_trend = adv_data.get("attendance_trend_slope", 0.0)
    if att_trend < -0.1:
        correlation_text.append(f"هناك انحدار سلبي مستمر في معدلات الحضور والغياب (بميل {att_trend:.2f})، مما ينذر باحتمالية تسرب الأطفال أو وجود مشاكل في رضا الأهالي.")
    elif att_trend > 0.1:
        correlation_text.append("تحليل السلاسل الزمنية يظهر نمواً إيجابياً ومستقراً في معدلات الحضور.")

    # 3. JUDGEMENT
    risk_index = adv_data.get("predictive_risk_index", 50.0)
    if risk_index > 75:
        judgement = "وضع حرج ومخاطر عالية (Red Flag). القطاع يتطلب تدخلاً فورياً."
    elif risk_index > 50:
        judgement = "وضع حذر (Yellow Flag). يحتاج إلى متابعة للرقابة الإدارية."
    else:
        judgement = "وضع مستقر وصحي (Green Flag). الأداء المؤسسي في مستويات آمنة."

    # 4. SUGGESTIONS
    suggestions = []
    if gov_z < 0:
        suggestions.append("توجيه فرق التفتيش فوراً لإجراء مسح شامل للحضانات ذات التقييم المنخفض وإلزامهم بخطط تصويب أوضاع.")
    if risk_index > 60:
        suggestions.append("تجميد مؤقت لمنح تراخيص جديدة في هذا النطاق الجغرافي لحين تحسين جودة الحضانات الحالية.")
    if staff_corr > 0.5:
        suggestions.append("تفعيل برامج دعم توظيف المعلمات والمشرفات لتقليل الضغط التشغيلي وخفض معدل الحوادث.")
    if att_trend < 0:
        suggestions.append("إطلاق استبيان حكومي موجه للأهالي لمعرفة أسباب الغياب والتسرب بشكل دقيق.")

    if not suggestions:
        suggestions.append("الاستمرار في المراقبة الروتينية للحفاظ على هذه المؤشرات الإيجابية.")

    return {
        "summary": summary,
        "correlations": " ".join(correlation_text),
        "judgement": judgement,
        "suggestions": suggestions
    }
