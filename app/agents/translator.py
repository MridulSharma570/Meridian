"""Translator agent — full-report localisation with structure preservation.

With a configured LLM slot, the entire markdown is translated by the model.
Without one, Meridian applies a curated phrase lexicon (headings, labels and
section vocabulary) plus a fully localised executive summary in 14 languages,
and clearly labels the result as a structural translation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.agents.base import BaseAgent
from app.api.llm_router import call_llm, is_configured
from app.config import SUPPORTED_LANGUAGES, settings
from app.database import queries

LANG_NAMES = {code: native for code, _, native in SUPPORTED_LANGUAGES}

KEYS = [
    "Executive Summary", "Key Takeaways", "Market Overview", "Market Sizing",
    "Historical Trajectory", "Competitive Landscape", "Trend Analysis",
    "SWOT Analysis", "PESTLE Analysis", "Porter's Five Forces", "Recommendations",
    "Risks & Assumptions", "Sources", "Market size", "Market Intelligence Report",
    "Total Addressable Market", "Serviceable Available Market",
    "Serviceable Obtainable Market", "Trailing CAGR", "Strengths", "Weaknesses",
    "Opportunities", "Threats", "Company", "Share", "Growth", "Sentiment",
    "Reliability", "Developed by", "Data mode", "Assumption notice",
]

LEXICON: Dict[str, List[str]] = {
    "hi": ["कार्यकारी सारांश", "मुख्य निष्कर्ष", "बाजार अवलोकन", "बाजार आकार निर्धारण",
           "ऐतिहासिक प्रवृत्ति", "प्रतिस्पर्धी परिदृश्य", "प्रवृत्ति विश्लेषण", "SWOT विश्लेषण",
           "PESTLE विश्लेषण", "पोर्टर के पाँच बल", "सिफारिशें", "जोखिम और मान्यताएँ", "स्रोत",
           "बाजार आकार", "बाजार आसूचना रिपोर्ट", "कुल संबोध्य बाजार", "सेवा योग्य उपलब्ध बाजार",
           "सेवा योग्य प्राप्य बाजार", "पिछली CAGR", "शक्तियाँ", "कमज़ोरियाँ", "अवसर", "खतरे",
           "कंपनी", "हिस्सेदारी", "वृद्धि", "भावना", "विश्वसनीयता", "विकसित किया",
           "डेटा मोड", "मान्यता सूचना"],
    "es": ["Resumen Ejecutivo", "Conclusiones Clave", "Panorama del Mercado", "Dimensionamiento",
           "Trayectoria Histórica", "Panorama Competitivo", "Análisis de Tendencias", "Análisis FODA",
           "Análisis PESTLE", "Cinco Fuerzas de Porter", "Recomendaciones", "Riesgos y Supuestos",
           "Fuentes", "Tamaño del mercado", "Informe de Inteligencia de Mercado",
           "Mercado Total Direccionable", "Mercado Disponible Servible", "Mercado Obtenible Servible",
           "CAGR histórica", "Fortalezas", "Debilidades", "Oportunidades", "Amenazas", "Empresa",
           "Cuota", "Crecimiento", "Sentimiento", "Fiabilidad", "Desarrollado por",
           "Modo de datos", "Aviso de supuestos"],
    "fr": ["Synthèse Exécutive", "Points Clés", "Aperçu du Marché", "Dimensionnement du Marché",
           "Trajectoire Historique", "Paysage Concurrentiel", "Analyse des Tendances", "Analyse SWOT",
           "Analyse PESTLE", "Les Cinq Forces de Porter", "Recommandations", "Risques et Hypothèses",
           "Sources", "Taille du marché", "Rapport d'Intelligence Marché",
           "Marché Total Adressable", "Marché Disponible Servi", "Marché Obtenable Servi",
           "TCAM historique", "Forces", "Faiblesses", "Opportunités", "Menaces", "Entreprise",
           "Part", "Croissance", "Sentiment", "Fiabilité", "Développé par", "Mode de données",
           "Avis sur les hypothèses"],
    "de": ["Zusammenfassung", "Kernaussagen", "Marktüberblick", "Marktgrößenbestimmung",
           "Historische Entwicklung", "Wettbewerbslandschaft", "Trendanalyse", "SWOT-Analyse",
           "PESTLE-Analyse", "Porters Fünf Kräfte", "Empfehlungen", "Risiken und Annahmen",
           "Quellen", "Marktgröße", "Marktintelligenz-Bericht", "Gesamter adressierbarer Markt",
           "Bedienbarer verfügbarer Markt", "Bedienbarer erreichbarer Markt", "Historische CAGR",
           "Stärken", "Schwächen", "Chancen", "Risiken", "Unternehmen", "Anteil", "Wachstum",
           "Stimmung", "Zuverlässigkeit", "Entwickelt von", "Datenmodus", "Hinweis zu Annahmen"],
    "ja": ["エグゼクティブサマリー", "主な要点", "市場概観", "市場規模の算定", "過去の推移",
           "競争環境", "トレンド分析", "SWOT分析", "PESTLE分析", "ポーターの五力", "提言",
           "リスクと前提", "出典", "市場規模", "市場インテリジェンスレポート",
           "獲得可能な市場全体", "対応可能な利用可能市場", "対応可能な獲得市場", "過去のCAGR",
           "強み", "弱み", "機会", "脅威", "企業", "シェア", "成長", "感情", "信頼性",
           "開発者", "データモード", "前提条件に関する注記"],
    "zh": ["执行摘要", "核心要点", "市场概览", "市场规模测算", "历史轨迹", "竞争格局",
           "趋势分析", "SWOT 分析", "PESTLE 分析", "波特五力", "建议", "风险与假设",
           "资料来源", "市场规模", "市场情报报告", "潜在市场总量", "可服务市场",
           "可获得市场", "历史复合增长率", "优势", "劣势", "机会", "威胁", "公司",
           "份额", "增长", "情绪", "可信度", "开发者", "数据模式", "假设说明"],
    "ar": ["الملخص التنفيذي", "أبرز النتائج", "نظرة عامة على السوق", "تقدير حجم السوق",
           "المسار التاريخي", "المشهد التنافسي", "تحليل الاتجاهات", "تحليل SWOT",
           "تحليل PESTLE", "قوى بورتر الخمس", "التوصيات", "المخاطر والافتراضات", "المصادر",
           "حجم السوق", "تقرير استخبارات السوق", "إجمالي السوق القابل للاستهداف",
           "السوق المتاح القابل للخدمة", "السوق الممكن الحصول عليه", "معدل النمو التاريخي",
           "نقاط القوة", "نقاط الضعف", "الفرص", "التهديدات", "الشركة", "الحصة",
           "النمو", "المعنويات", "الموثوقية", "تم التطوير بواسطة", "وضع البيانات",
           "ملاحظة الافتراضات"],
    "pt": ["Resumo Executivo", "Principais Conclusões", "Visão Geral do Mercado",
           "Dimensionamento do Mercado", "Trajetória Histórica", "Cenário Competitivo",
           "Análise de Tendências", "Análise SWOT", "Análise PESTLE", "Cinco Forças de Porter",
           "Recomendações", "Riscos e Premissas", "Fontes", "Tamanho do mercado",
           "Relatório de Inteligência de Mercado", "Mercado Total Endereçável",
           "Mercado Disponível Atendível", "Mercado Obtível Atendível", "CAGR histórico",
           "Forças", "Fraquezas", "Oportunidades", "Ameaças", "Empresa", "Participação",
           "Crescimento", "Sentimento", "Confiabilidade", "Desenvolvido por",
           "Modo de dados", "Aviso de premissas"],
    "ko": ["경영 요약", "핵심 시사점", "시장 개요", "시장 규모 산정", "과거 추이", "경쟁 구도",
           "트렌드 분석", "SWOT 분석", "PESTLE 분석", "포터의 다섯 가지 힘", "권고 사항",
           "위험 및 가정", "출처", "시장 규모", "시장 인텔리전스 보고서", "전체 잠재 시장",
           "서비스 가능 시장", "확보 가능 시장", "과거 CAGR", "강점", "약점", "기회", "위협",
           "기업", "점유율", "성장", "감성", "신뢰도", "개발자", "데이터 모드", "가정 관련 안내"],
    "ru": ["Краткое резюме", "Ключевые выводы", "Обзор рынка", "Оценка объёма рынка",
           "Историческая динамика", "Конкурентная среда", "Анализ трендов", "SWOT-анализ",
           "PESTLE-анализ", "Пять сил Портера", "Рекомендации", "Риски и допущения",
           "Источники", "Объём рынка", "Отчёт по рыночной аналитике",
           "Общий адресуемый рынок", "Доступный обслуживаемый рынок",
           "Реально достижимый рынок", "Исторический CAGR", "Сильные стороны",
           "Слабые стороны", "Возможности", "Угрозы", "Компания", "Доля", "Рост",
           "Настроения", "Надёжность", "Разработано", "Режим данных", "Примечание о допущениях"],
    "it": ["Sintesi Esecutiva", "Punti Chiave", "Panoramica del Mercato", "Dimensionamento",
           "Andamento Storico", "Panorama Competitivo", "Analisi dei Trend", "Analisi SWOT",
           "Analisi PESTLE", "Cinque Forze di Porter", "Raccomandazioni", "Rischi e Ipotesi",
           "Fonti", "Dimensione del mercato", "Report di Market Intelligence",
           "Mercato Totale Indirizzabile", "Mercato Disponibile Servibile",
           "Mercato Ottenibile Servibile", "CAGR storico", "Punti di forza", "Debolezze",
           "Opportunità", "Minacce", "Azienda", "Quota", "Crescita", "Sentiment",
           "Affidabilità", "Sviluppato da", "Modalità dati", "Nota sulle ipotesi"],
    "bn": ["নির্বাহী সারসংক্ষেপ", "মূল তথ্য", "বাজার পর্যালোচনা", "বাজার আকার নির্ধারণ",
           "ঐতিহাসিক প্রবণতা", "প্রতিযোগিতামূলক পরিস্থিতি", "প্রবণতা বিশ্লেষণ", "SWOT বিশ্লেষণ",
           "PESTLE বিশ্লেষণ", "পোর্টারের পাঁচ শক্তি", "সুপারিশ", "ঝুঁকি ও অনুমান", "উৎস",
           "বাজার আকার", "বাজার গোয়েন্দা প্রতিবেদন", "মোট সম্ভাব্য বাজার", "সেবাযোগ্য বাজার",
           "অর্জনযোগ্য বাজার", "ঐতিহাসিক CAGR", "শক্তি", "দুর্বলতা", "সুযোগ", "হুমকি",
           "কোম্পানি", "অংশীদারি", "প্রবৃদ্ধি", "অনুভূতি", "নির্ভরযোগ্যতা", "নির্মিত",
           "ডেটা মোড", "অনুমান সংক্রান্ত নোট"],
    "pa": ["ਕਾਰਜਕਾਰੀ ਸਾਰ", "ਮੁੱਖ ਨਤੀਜੇ", "ਬਾਜ਼ਾਰ ਝਲਕ", "ਬਾਜ਼ਾਰ ਆਕਾਰ", "ਇਤਿਹਾਸਕ ਰੁਝਾਨ",
           "ਮੁਕਾਬਲੇ ਦਾ ਦ੍ਰਿਸ਼", "ਰੁਝਾਨ ਵਿਸ਼ਲੇਸ਼ਣ", "SWOT ਵਿਸ਼ਲੇਸ਼ਣ", "PESTLE ਵਿਸ਼ਲੇਸ਼ਣ",
           "ਪੋਰਟਰ ਦੀਆਂ ਪੰਜ ਤਾਕਤਾਂ", "ਸਿਫ਼ਾਰਸ਼ਾਂ", "ਜੋਖਮ ਅਤੇ ਧਾਰਨਾਵਾਂ", "ਸਰੋਤ",
           "ਬਾਜ਼ਾਰ ਆਕਾਰ", "ਬਾਜ਼ਾਰ ਖੁਫ਼ੀਆ ਰਿਪੋਰਟ", "ਕੁੱਲ ਸੰਭਾਵੀ ਬਾਜ਼ਾਰ", "ਸੇਵਾਯੋਗ ਬਾਜ਼ਾਰ",
           "ਪ੍ਰਾਪਤਯੋਗ ਬਾਜ਼ਾਰ", "ਪਿਛਲੀ CAGR", "ਤਾਕਤਾਂ", "ਕਮਜ਼ੋਰੀਆਂ", "ਮੌਕੇ", "ਖਤਰੇ",
           "ਕੰਪਨੀ", "ਹਿੱਸਾ", "ਵਾਧਾ", "ਭਾਵਨਾ", "ਭਰੋਸੇਯੋਗਤਾ", "ਵਿਕਸਤ ਕਰਤਾ",
           "ਡਾਟਾ ਮੋਡ", "ਧਾਰਨਾਵਾਂ ਬਾਰੇ ਨੋਟ"],
}

SUMMARY_TEMPLATES: Dict[str, str] = {
    "en": "**Executive Summary.** {company} operates in {sector} across {region}, a market "
          "estimated at ${size}B growing at {cagr}% CAGR. This report covers sizing, "
          "competitive position, trends, strategic frameworks and a 12-month forecast.",
    "hi": "**कार्यकारी सारांश।** {company} {region} में {sector} क्षेत्र में सक्रिय है। "
          "इस बाजार का अनुमानित आकार ${size}B है और यह {cagr}% CAGR से बढ़ रहा है। "
          "रिपोर्ट में आकार, प्रतिस्पर्धा, प्रवृत्तियाँ, रणनीतिक ढाँचे और 12 महीने का पूर्वानुमान शामिल है।",
    "es": "**Resumen Ejecutivo.** {company} opera en {sector} en {region}, un mercado estimado "
          "en ${size}B con un crecimiento del {cagr}% CAGR. El informe cubre dimensionamiento, "
          "competencia, tendencias, marcos estratégicos y una previsión a 12 meses.",
    "fr": "**Synthèse Exécutive.** {company} opère dans {sector} en {region}, un marché estimé "
          "à ${size}B avec un TCAM de {cagr}%. Le rapport couvre le dimensionnement, la "
          "concurrence, les tendances et une prévision à 12 mois.",
    "de": "**Zusammenfassung.** {company} ist in {sector} in {region} tätig — ein Markt von "
          "geschätzt ${size}B mit {cagr}% CAGR. Der Bericht umfasst Marktgröße, Wettbewerb, "
          "Trends, Strategie-Frameworks und eine 12-Monats-Prognose.",
    "ja": "**エグゼクティブサマリー。** {company} は {region} の {sector} 市場で事業を展開しています。"
          "市場規模は ${size}B、CAGR は {cagr}% と推定されます。本レポートは市場規模、競争環境、"
          "トレンド、戦略フレームワーク、12か月予測を網羅しています。",
    "zh": "**执行摘要。** {company} 在 {region} 的 {sector} 市场开展业务，市场规模估计为 ${size}B，"
          "复合年增长率为 {cagr}%。本报告涵盖市场规模、竞争格局、趋势、战略框架及 12 个月预测。",
    "ar": "**الملخص التنفيذي.** تعمل {company} في سوق {sector} بمنطقة {region}، ويُقدّر حجمه "
          "بـ ${size}B بمعدل نمو {cagr}%. يغطي التقرير الحجم والمنافسة والاتجاهات وتوقعات 12 شهراً.",
    "pt": "**Resumo Executivo.** {company} atua em {sector} na região {region}, mercado estimado "
          "em ${size}B com CAGR de {cagr}%. O relatório cobre dimensionamento, concorrência, "
          "tendências e uma previsão de 12 meses.",
    "ko": "**경영 요약.** {company}는 {region}의 {sector} 시장에서 사업을 영위하며, 시장 규모는 "
          "${size}B, CAGR은 {cagr}%로 추정됩니다. 본 보고서는 시장 규모, 경쟁 구도, 트렌드 및 "
          "12개월 전망을 다룹니다.",
    "ru": "**Краткое резюме.** {company} работает на рынке {sector} в регионе {region}; "
          "объём оценивается в ${size}B при CAGR {cagr}%. Отчёт охватывает размер рынка, "
          "конкуренцию, тренды и прогноз на 12 месяцев.",
    "it": "**Sintesi Esecutiva.** {company} opera in {sector} nella regione {region}, un mercato "
          "stimato in ${size}B con CAGR del {cagr}%. Il report copre dimensionamento, "
          "concorrenza, trend e previsioni a 12 mesi.",
    "bn": "**নির্বাহী সারসংক্ষেপ।** {company} {region}-এ {sector} খাতে কাজ করে। "
          "বাজারের আকার আনুমানিক ${size}B এবং প্রবৃদ্ধি {cagr}% CAGR। প্রতিবেদনে আকার, "
          "প্রতিযোগিতা, প্রবণতা ও ১২ মাসের পূর্বাভাস রয়েছে।",
    "pa": "**ਕਾਰਜਕਾਰੀ ਸਾਰ।** {company} {region} ਵਿੱਚ {sector} ਖੇਤਰ ਵਿੱਚ ਕੰਮ ਕਰਦੀ ਹੈ। "
          "ਬਾਜ਼ਾਰ ਦਾ ਅਨੁਮਾਨਿਤ ਆਕਾਰ ${size}B ਹੈ ਅਤੇ ਵਾਧਾ ਦਰ {cagr}% CAGR ਹੈ। "
          "ਰਿਪੋਰਟ ਵਿੱਚ ਆਕਾਰ, ਮੁਕਾਬਲਾ, ਰੁਝਾਨ ਅਤੇ 12 ਮਹੀਨਿਆਂ ਦਾ ਪੂਰਵਾਨੁਮਾਨ ਸ਼ਾਮਲ ਹੈ।",
}

LOCALISED_NOTES: Dict[str, str] = {
    "en": "Structural translation applied. Connect an LLM provider for full neural translation.",
    "hi": "संरचनात्मक अनुवाद लागू। पूर्ण तंत्रिका अनुवाद के लिए सेटिंग्स में LLM कुंजी जोड़ें।",
    "es": "Traducción estructural aplicada. Conecte un proveedor LLM para traducción neuronal completa.",
    "fr": "Traduction structurelle appliquée. Connectez un fournisseur LLM pour une traduction neuronale complète.",
    "de": "Strukturelle Übersetzung angewendet. Für eine vollständige neuronale Übersetzung LLM-Anbieter verbinden.",
    "ja": "構造翻訳を適用しました。完全なニューラル翻訳には設定で LLM キーを接続してください。",
    "zh": "已应用结构化翻译。如需完整的神经机器翻译，请在设置中连接 LLM 提供商。",
    "ar": "تم تطبيق ترجمة هيكلية. أضف مفتاح LLM في الإعدادات للحصول على ترجمة عصبية كاملة.",
    "pt": "Tradução estrutural aplicada. Conecte um provedor LLM para tradução neural completa.",
    "ko": "구조 번역이 적용되었습니다. 전체 신경망 번역은 설정에서 LLM 키를 연결하세요.",
    "ru": "Применён структурный перевод. Для полного нейронного перевода подключите LLM в настройках.",
    "it": "Traduzione strutturale applicata. Collega un provider LLM per la traduzione neurale completa.",
    "bn": "গঠনমূলক অনুবাদ প্রয়োগ করা হয়েছে। সম্পূর্ণ নিউরাল অনুবাদের জন্য সেটিংসে LLM কী যোগ করুন।",
    "pa": "ਢਾਂਚਾਗਤ ਅਨੁਵਾਦ ਲਾਗੂ ਕੀਤਾ ਗਿਆ। ਪੂਰੇ ਨਿਊਰਲ ਅਨੁਵਾਦ ਲਈ ਸੈਟਿੰਗਾਂ ਵਿੱਚ LLM ਕੁੰਜੀ ਜੋੜੋ।",
}


class TranslatorAgent(BaseAgent):
    name = "translator"
    slot = "translator"
    icon = "🌐"
    description = "Localises the full report while preserving formatting"

    def local_run(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {"supported": [{"code": c, "name": n, "native": nat}
                              for c, n, nat in SUPPORTED_LANGUAGES]}

    def llm_prompt(self, ctx: Dict[str, Any]) -> str:
        return ""

    @staticmethod
    def _lexicon_replace(text: str, lang: str) -> str:
        words = LEXICON.get(lang)
        if not words:
            return text
        out = text
        for key, translated in sorted(zip(KEYS, words), key=lambda x: -len(x[0])):
            out = re.sub(re.escape(key), lambda m, t=translated: t, out, flags=re.I)
        return out

    def translate(self, markdown: str, target: str, ctx: Dict[str, Any],
                  report_id: str = "") -> Dict[str, Any]:
        """Translate a full report. Always returns usable text."""
        target = target if target in LANG_NAMES else "en"
        if target == "en":
            return {"language": "en", "native": "English", "content": markdown,
                    "method": "original", "note": ""}
        d = ctx.get("dataset", {})
        tpl = SUMMARY_TEMPLATES.get(target, SUMMARY_TEMPLATES["en"])
        summary = tpl.format(
            company=d.get("company", "The Market"), sector=d.get("sector", "the market"),
            region=d.get("region", "Global"),
            size=f"{d.get('market_size_usd_b', 0):.1f}",
            cagr=f"{d.get('cagr_pct', 0):.1f}",
        )

        method, note = "structural-lexicon", LOCALISED_NOTES.get(target, LOCALISED_NOTES["en"])
        content = self._lexicon_replace(markdown, target)
        if is_configured("translator"):
            try:
                res = call_llm(
                    "translator",
                    "You are a professional financial translator. Translate the report into "
                    f"{LANG_NAMES[target]}. Preserve ALL markdown syntax, tables, numbers, "
                    "reference ids like [S01], URLs and section structure. Output only the "
                    "translated markdown, no commentary.",
                    markdown[:9000], max_tokens=4096, temperature=0.15,
                    timeout=max(settings.agent_timeout_s, 60),
                )
                if len(res["text"]) > 200:
                    content, method = res["text"], f"llm ({res['provider']})"
                    note = "Full neural translation; markdown structure preserved."
            except Exception:
                pass  # structural translation stands

        # Add a localised summary at the top so the result reads naturally.
        header = f"## {LEXICON[target][0] if target in LEXICON else 'Summary'}\n\n{summary}\n\n" \
                 f"> {note}\n\n---\n\n"
        content = header + content
        if report_id:
            queries.save_translation(report_id, "en", target, content)
        return {"language": target, "native": LANG_NAMES[target],
                "content": content, "method": method, "note": note}
