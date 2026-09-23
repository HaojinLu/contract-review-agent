from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from contract_review_agent.json_utils import extract_json_payload, to_pretty_json
from contract_review_agent.llm import ProviderSettings, create_chat_model
from contract_review_agent.prompt_loader import read_text_with_fallback
from contract_review_agent.schemas import ClauseExtractionResult, ContractReviewReport


DEFAULT_REVIEW_PROMPT = """---

### 模块一：核心比对规则 Prompt（引导多维度核对）
*目标：明确告诉LLM需要比对哪些具体条款，避免遗漏。*

> **【比对维度说明】**
> 请你严格按照以下三个核心维度，逐一对比【采购结果文件】与【合同草案】的内容：
>
> **1. 商务条款匹配度（Business Terms）：**
> - **价格**：核对总金额、单价、计价方式是否完全一致，注意大小写金额的准确性。
> - **数量**：核对采购的软硬件授权数、人月数、服务频次等具体数量指标。
> - **服务范围/采购清单**：核对中标供应商、具体提供产品/服务的明细、规格型号是否出现缩水或变更。
>
> **2. 时间框架吻合度（Time Frames）：**
> - **交付周期**：核对项目上线时间、软硬件到货时间、里程碑节点是否一致。
> - **合同期限**：核对服务的生效日期与终止日期、质保期长短是否一致。
>
> **3. 法律及合规条款完整性（Legal & Compliance）：**
> - **违约责任**：核对采购文件中要求的违约金比例、逾期罚则、赔偿上限等在合同中是否被削弱或篡改。
> - **支付条件**：核对付款比例（如预付款、初验款、尾款）、付款前提（如提供发票、验收报告）是否被修改。
> - **保密条款**：核对数据安全要求、保密期限、违约责任是否完整承接采购要求。

---

### 模块二：语义理解与容错 Prompt（提升语义对齐能力）
*目标：防止LLM因为"字面不同"而误判，引导其进行深度的语义推理。*

> **【语义理解与判断准则】**
> 由于采购结果通常由业务/采购部门起草，而合同通常由法务/供应商起草，两者存在用词习惯差异。你必须具备**高级语义理解能力**，不能仅依赖字面匹配：
> 1. **同义替换识别**：例如采购结果要求"30个自然日内交付"，合同写"自签订之日起一个月内完成交付"，应判定为【语义一致】。
> 2. **包容性判断**：如果合同条款的约束比采购结果更严格、更有利于银行（如采购要求质保1年，合同承诺质保3年），应判定为【一致且有利】，不可标为矛盾。
> 3. **隐蔽性削弱识别**：如果采购结果要求"乙方承担全部违约责任"，合同却增加了"除非因不可抗力或第三方原因"，这构成了对违约责任的削弱，必须判定为【差异项】。
> 4. **前后文关联**：在判断服务范围时，注意结合附件内容进行整体语义比对，不可断章取义。
> 5. **价格差异因果分析**：合同总价低于采购总价时，不得直接列为独立差异项。必须先检查是否存在服务范围缩减、数量减少、规格降低等根本原因。若价格差异能被服务范围变化解释，应将价格差异作为"服务范围变化"差异项的佐证，而非单独的价格差异项。仅在合同总价高于采购总价，或价格差异无法用其他已发现的差异解释时，才可列为独立的价格差异项。
> *在得出结论前，请先进行内部逻辑推理，解释两句话在法律和商业实质上是否等价。*

---

### 模块三：结构化输出 Prompt（规范输出结果）
*目标：要求LLM输出便于前端系统解析和高亮展示的JSON格式。*

> **【结构化输出要求】**
> 你的输出必须严格按照以下三个分类进行结构化展示。对于每一项结论，必须提供原文引述和分析理由：
>
> **一、缺失项 (Missing Items)**
> *(定义：在采购结果中明确要求，但合同草案中完全缺失或遗漏的条款)*
>
> **二、差异/矛盾项 (Discrepancies)**
> *(定义：双方都有提及，但核心数据、时间、责任划分在语义或数值上存在矛盾与削弱)*
>
> **三、一致项 (Consistent Items)**
> *(定义：核心关键条款在两份文档中语义完全吻合)*

```text
# Role
你是一名资深的"银行法务合规专家"与"高级采购审核AI Agent"。你拥有深厚的法律合同功底和商业敏感度，擅长在冗长、晦涩的文本中精准捕捉数据、时间、责任的细微差异。

# Task
你的任务是对两份文件进行深度比对：
文件A：【银行采购结果/中标通知书/采购需求书】
文件B：【拟签订的合同草案】
你需要通过全维度交叉校验，找出两份文件中的"一致项"、"缺失项"和"差异/矛盾项"，以此防止合同漏洞，避免银行产生履约纠纷与经济损失。

# Rules (比对维度)
请重点提取并比对以下三大类条款：
1. 商务匹配度：总价/单价/计价方式、采购数量（软硬件/人月）、核心服务范围与采购清单。
2. 时间框架：交付周期/里程碑节点、合同生效与失效期限、质保期。
3. 法律完整性：违约责任（罚金比例/赔偿上限）、支付条件（首尾款比例/付款前提）、保密条款与数据安全要求。

# Strategy (语义理解准则)
请务必运用深度语义理解，不要死板地进行字面匹配：
1. 【同义等价】：如"30个自然日"与"一个月"，"尾款"与"验收后支付的款项"，需识别为语义一致。
2. 【严格度判定】：若合同条款比文件A更有利于银行（如质保期更长、价格更低），属于"一致且有利"；若合同偷偷增加了银行的义务或减轻了供应商的责任（如增加免责条款），则必须判定为"矛盾项"。
3. 【推理过程】：在判定为矛盾前，请仔细思考双方语境是否真的冲突。

# Output Format
请严格按照以下JSON格式输出比对质检报告，确保JSON合法且可被解析。对于差异项，必须给出"高、中、低"的风险评级。

{
  "Review_Summary": "简述整体匹配情况及最大风险点(100字以内)",
  "Discrepancies_矛盾项": [
    {
      "条款维度": "例如：违约责任",
      "文件A_采购要求": "提取的原文片段",
      "文件B_合同草案": "提取的原文片段",
      "语义差异分析": "详细解释为何构成矛盾或削弱了银行权益",
      "风险评级": "高"
    }
  ],
  "Missing_Items_缺失项": [
    {
      "条款维度": "例如：保密条款",
      "文件A_要求": "提取的原文片段",
      "遗漏说明": "说明合同中缺失了哪部分关键约束",
      "风险评级": "中"
    }
  ],
  "Consistent_Items_一致项": [
    {
      "条款维度": "例如：采购总金额",
      "文件A_内容": "...",
      "文件B_内容": "..."
    }
  ]
}
```
"""


EXTRACTION_PROMPT_TEMPLATE = """你是合同条款抽取专家。你的任务是做"证据级事实抽取"，不是做判断。

请从下面的 markdown 合同文本中，按以下要求抽取信息：

# 一、抽取三大类条款
1. business_terms: 价格（总价/单价/计价方式）、数量（授权数/人月数/次数/把/张等）、服务范围/采购清单（每一项服务/产品及其详细要求）、规格型号
2. time_frames: 交付周期（具体天数/日期）、里程碑节点、合同期限（起止日期）、质保期、响应时间
3. legal_terms: 违约责任（罚金比例/赔偿上限/违约金比例）、支付条件（预付款比例/尾款条件/付款前提）、保密条款、税率/发票要求

# 二、系统性抽取规则
- **逐项枚举**：将文档中列出的每一个独立服务项/产品项单独作为一条 fact 抽取。例如：①渗透测试 ②漏洞扫描 ③安全培训 ④应急响应 → 四条独立的 fact
- **数值必须抽取**：每一项中的金额、数量、比例、天数必须抽入 key_points。例如：单价 ¥4,500.00、数量 4次、预付款 40%、45个工作日、13%增值税
- **具体要求必须抽取**：如果文档列出了具体服务标准（如"茶歇人均不低于30元""精修照片不少于200张""响应时间2小时内"），必须逐条抽取，不可合并为笼统描述
- **合同引用**：source_quote 必须是原文中的连续片段。注意结合 markdown 末尾的"补充文本"和"附加说明"部分----这些也是原文的有效来源
- **不要臆断**：不完整的句子片段如果无法确认完整含义，宁可漏抽

输出要求：
- 只输出 JSON
- JSON 结构必须是：
{{
  "document_role": "{document_role}",
  "clauses": [
    {{
      "dimension": "business_terms|time_frames|legal_terms",
      "sub_dimension": "price|quantity|service_scope|specification|delivery_cycle|contract_term|breach_liability|payment_terms|confidentiality|tax_rate|response_time|...",
      "normalized_statement": "归一化后的短句，包含完整的数值信息",
      "source_quote": "原文摘录，优先控制在300字以内",
      "key_points": ["单价: ¥4,500.00", "数量: 4次", "预付款比例: 40%", "交付: 45个工作日", ...]
    }}
  ]
}}

待抽取 markdown：
{markdown_text}
"""


COMPARISON_PROMPT_TEMPLATE = """你是银行合同双审专家。请结合下面的审核规则、采购文件条款抽取结果、合同草案条款抽取结果，对两份文件做深度比对。

审核规则：
{review_prompt}

# 比对方法论（必须严格遵循以下步骤）

## 第一步：逐项配对
1. 从采购文件中提取所有**可独立核验的服务项/产品项/条款项**，每项包含：名称、数量、单价/金额、时间/周期、具体要求
2. 从合同草案中做同样的提取
3. 将采购文件中的每一项与合同草案中的对应项逐一配对。对于无法配对的项，标注为"未找到对应条款"

## 第二步：逐项比对（对每个配对执行以下检查）
- **数值比对**：数量是否一致？单价是否一致？总价是否一致？百分比是否一致？天数/月数是否一致？
- **服务范围比对**：采购中的每一项具体要求（如"茶歇人均不低于30元"、"精修照片不少于200张"）是否在合同中都有对应的明确条款？
- **义务比对**：采购中约定的供应商义务是否在合同中完整承接？是否有被删除或弱化的义务？
- **时间比对**：交付周期、响应时间、合同期限的天数/日期是否一致？

## 第三步：分类判定
- **差异项**：数值不一致 → 差异项。具体要求被削弱或改变 → 差异项。合同用了更低的标准 → 差异项
- **缺失项**：采购有明确的具体要求，但合同中完全找不到对应条款（甚至连概括性表述都没有）→ 缺失项。采购中的具体要求在合同中变成了笼统描述（如"按合同约定执行""满足甲方要求"等无实质内容的表述）→ 缺失项
- **一致项**：数值、内容、义务均一致，或合同更严格/更有利于银行 → 一致项

## 常见漏报场景（必须注意）
1. 如果采购文件列出了一系列具体服务要求（如①...②...③...），但合同只用了笼统的一句话概括，必须逐条检查每项要求是否在合同中有对应条款。缺失的具体要求必须逐一报告为缺失项
2. 如果采购文件约定了具体数值（如"45个工作日"、"13%增值税"），但合同改成了不同数值或省略了数值，必须报告为差异项
3. 如果采购文件约定了"免费技术培训"、"应急响应2小时内到场"等增值/配套服务，但合同未提及，必须报告为缺失项
4. 同一服务项下如果有多个具体参数（数量、单价、规格、频次等），对每个参数分别比对

严格判定门槛：
- 证据不足时不要报风险项，宁可不报，也不要猜测
- 普通措辞差异、合同语言更规范、合同对银行更有利，不得列为差异项
- 合同句子里包含同义表述（哪怕用词不同）则应视为一致项
- **价格因果规则**：合同总价与采购总价不同时，不得直接列为独立差异项。必须先检查各分项是否存在数量/单价变化来解释总价差异。总价差异作为分项差异的佐证引用
- **服务项交叉比对**：比对前必须先构建两份文件的服务项/产品项清单，逐项配对。采购中有但合同中完全缺失的，必须列为缺失项

采购文件抽取结果：
{procurement_facts}

合同草案抽取结果：
{contract_facts}

请只输出 JSON，且严格满足下面结构：
{{
  "review_summary": "100字以内总结，列出主要差异类型和数量",
  "missing_items": [
    {{
      "dimension": "business_terms|time_frames|legal_terms",
      "sub_dimension": "具体子类（如service_scope, price, quantity, delivery_cycle, payment_terms等）",
      "procurement_quote": "采购文件原文",
      "contract_quote": "",
      "analysis": "说明采购要求了什么，合同中为什么视为缺失（必须说明排除了同义承接的可能性）",
      "risk_level": "high|medium|low"
    }}
  ],
  "discrepancies": [
    {{
      "dimension": "business_terms|time_frames|legal_terms",
      "sub_dimension": "具体子类",
      "procurement_quote": "采购文件原文",
      "contract_quote": "合同草案原文",
      "analysis": "具体指出数值/参数/义务的冲突点",
      "risk_level": "high|medium|low"
    }}
  ],
  "consistent_items": [
    {{
      "dimension": "business_terms|time_frames|legal_terms",
      "sub_dimension": "具体子类",
      "procurement_quote": "采购文件原文",
      "contract_quote": "合同草案原文",
      "analysis": "为何视为一致或合同更有利",
      "risk_level": null
    }}
  ]
}}
"""


VERIFICATION_PROMPT_TEMPLATE = """你是合同审核结果复核专家。你的任务是对"候选审核结果"做保守复核，删除没有充分证据的误报，并补充明显漏报的高置信问题。

复核原则：
1. 只保留能被原文直接支持的缺失项和差异项。
2. 缺失项必须满足：采购文件有明确具体要求，且合同草案全文没有同义、概括或附件形式的承接。
3. 差异项必须满足：双方均有相关条款，且金额、数量、时间、责任、付款条件、服务范围等实质内容冲突或被削弱。
4. 仅有表达方式不同、法务措辞不同、条款更详细、合同更有利于银行，不是问题。
5. 如果候选问题的采购原文或合同原文不足以支撑结论，应删除或改为一致项。
6. 如果你不确定是否存在问题，删除该风险项。
7. consistent_items 只保留关键一致项，不需要穷尽，最多输出 8 项。

可用证据一：采购文件原文 markdown
{procurement_markdown}

可用证据二：合同草案原文 markdown
{contract_markdown}

可用证据三：采购文件抽取事实
{procurement_facts}

可用证据四：合同草案抽取事实
{contract_facts}

候选审核结果：
{candidate_report}

请只输出修正后的 JSON，严格满足下面结构：
{{
  "review_summary": "100字以内总结，说明最终保留的主要风险；如无明确风险，应直接说明未发现实质冲突",
  "missing_items": [
    {{
      "dimension": "business_terms|time_frames|legal_terms",
      "sub_dimension": "具体子类",
      "procurement_quote": "采购文件原文，必须可在采购 markdown 中找到",
      "contract_quote": "",
      "analysis": "为什么合同没有同义承接；必须具体",
      "risk_level": "high|medium|low"
    }}
  ],
  "discrepancies": [
    {{
      "dimension": "business_terms|time_frames|legal_terms",
      "sub_dimension": "具体子类",
      "procurement_quote": "采购文件原文，必须可在采购 markdown 中找到",
      "contract_quote": "合同草案原文，必须可在合同 markdown 中找到",
      "analysis": "具体冲突点，不要泛泛而谈",
      "risk_level": "high|medium|low"
    }}
  ],
  "consistent_items": [
    {{
      "dimension": "business_terms|time_frames|legal_terms",
      "sub_dimension": "具体子类",
      "procurement_quote": "采购文件原文",
      "contract_quote": "合同草案原文",
      "analysis": "为什么一致或合同更有利",
      "risk_level": null
    }}
  ]
}}
"""


def _clip_text(text: str, limit: int = 24000) -> str:
    if len(text) <= limit:
        return text

    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return text[:limit]

    _KEY_TERMS = re.compile(
        "|".join(
            [
                r"\d+[万亿千百十]?元",
                r"\d+%",
                r"第[一二三四五六七八九十\d]+条",
                r"合同总[价金]",
                r"付款",
                r"违约",
                r"保密",
                r"知识产权",
                r"验收",
                r"服务[范项]",
                r"交付",
                r"质保",
                r"培训",
                r"应急",
                r"渗透",
                r"扫描",
                r"单价",
                r"数[量目]",
            ]
        )
    )

    scored: list[tuple[int, str]] = []
    for para in paragraphs:
        score = 0
        if _KEY_TERMS.search(para):
            score += 10
        if re.search(r"\d+", para):
            score += 3
        if len(para) > 50:
            score += 2
        scored.append((score, para))
    scored.sort(key=lambda x: x[0], reverse=True)

    selected: list[str] = []
    consumed = 0
    for score, para in scored:
        if consumed + len(para) + 2 > limit:
            remaining = limit - consumed
            if remaining > 100:
                selected.append(para[:remaining] + "\n...")
            break
        selected.append(para)
        consumed += len(para) + 2

    return "\n\n".join(selected) + "\n\n...（部分非关键段落因长度限制省略，请结合已抽取事实复核）..."


def _has_text(value: str | None) -> bool:
    return bool(str(value or "").strip())


_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|directives?)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"new\s+system\s+(prompt|message|instruction)", re.IGNORECASE),
    re.compile(r"<\|im_start\|>|<\|im_end\|>", re.IGNORECASE),
    re.compile(r"\[system\]|\[/system\]|\[/assistant\]", re.IGNORECASE),
]


def _sanitize_markdown_for_prompt(text: str) -> str:
    """Remove potential prompt injection patterns from extracted document text."""
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub("[已过滤]", text)
    return text


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (
            str(item.get("dimension", "")).strip().lower(),
            str(item.get("sub_dimension", "")).strip().lower(),
            str(item.get("procurement_quote", "")).strip()[:120],
            str(item.get("contract_quote", "")).strip()[:120],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _clean_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop low-evidence findings before schema validation."""
    cleaned = dict(payload)
    missing_items = []
    for item in cleaned.get("missing_items", []) or []:
        if isinstance(item, dict) and _has_text(item.get("procurement_quote")):
            item["contract_quote"] = ""
            missing_items.append(item)

    discrepancies = []
    for item in cleaned.get("discrepancies", []) or []:
        if not isinstance(item, dict):
            continue
        procurement_quote = str(item.get("procurement_quote", "")).strip()
        contract_quote = str(item.get("contract_quote", "")).strip()
        analysis = str(item.get("analysis", "")).strip()
        if not procurement_quote or not contract_quote or not analysis:
            continue
        if procurement_quote == contract_quote and not any(
            marker in analysis
            for marker in ("新增", "删除", "缩短", "延长", "降低", "提高", "减少", "增加", "不一致", "冲突", "削弱")
        ):
            continue
        discrepancies.append(item)

    consistent_items = []
    for item in cleaned.get("consistent_items", []) or []:
        if not isinstance(item, dict):
            continue
        if not _has_text(item.get("analysis")):
            continue
        if not _has_text(item.get("procurement_quote")):
            continue
        if not _has_text(item.get("contract_quote")):
            continue
        consistent_items.append(item)

    cleaned["missing_items"] = _dedupe_items(missing_items)
    cleaned["discrepancies"] = _dedupe_items(discrepancies)
    cleaned["consistent_items"] = _dedupe_items(consistent_items)[:8]
    return cleaned


def _empty_extraction(document_role: str) -> dict[str, Any]:
    return {"document_role": document_role, "clauses": []}


def _empty_report(summary: str = "模型未返回可解析的结构化结果，请人工复核原文。") -> dict[str, Any]:
    return {
        "review_summary": summary,
        "missing_items": [],
        "discrepancies": [],
        "consistent_items": [],
    }


def _invoke_json(
    llm,
    prompt: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = llm.invoke(prompt)
    try:
        return extract_json_payload(response.content)
    except Exception:
        repair_prompt = (
            "请把下面内容修正为合法 JSON。要求：只输出一个 JSON 对象，不要 Markdown，不要解释，不要代码块。\n\n"
            f"{response.content}"
        )
        try:
            repaired = llm.invoke(repair_prompt)
            return extract_json_payload(repaired.content)
        except Exception:
            if fallback is not None:
                return fallback
            raise


def build_contract_review_tool(settings: ProviderSettings):
    review_llm = create_chat_model(settings)

    @tool("compare_contract_markdown")
    def compare_contract_markdown(
        procurement_markdown_path: str,
        contract_markdown_path: str,
        prompt_text: str | None = None,
    ) -> str:
        """Compare two markdown contract files clause by clause and perform semantic deep analysis for suspected differences."""
        procurement_path = Path(procurement_markdown_path).resolve()
        contract_path = Path(contract_markdown_path).resolve()

        procurement_markdown = _sanitize_markdown_for_prompt(
            read_text_with_fallback(procurement_path)
        )
        contract_markdown = _sanitize_markdown_for_prompt(
            read_text_with_fallback(contract_path)
        )
        review_prompt = prompt_text or DEFAULT_REVIEW_PROMPT

        procurement_extraction = _invoke_json(
            review_llm,
            EXTRACTION_PROMPT_TEMPLATE.format(
                document_role="procurement",
                markdown_text=procurement_markdown,
            ),
            fallback=_empty_extraction("procurement"),
        )
        contract_extraction = _invoke_json(
            review_llm,
            EXTRACTION_PROMPT_TEMPLATE.format(
                document_role="contract",
                markdown_text=contract_markdown,
            ),
            fallback=_empty_extraction("contract"),
        )

        procurement_facts = ClauseExtractionResult.model_validate(procurement_extraction)
        contract_facts = ClauseExtractionResult.model_validate(contract_extraction)

        comparison_payload = _invoke_json(
            review_llm,
            COMPARISON_PROMPT_TEMPLATE.format(
                review_prompt=review_prompt,
                procurement_facts=to_pretty_json(procurement_facts.model_dump()),
                contract_facts=to_pretty_json(contract_facts.model_dump()),
            ),
            fallback=_empty_report(),
        )
        candidate_report = ContractReviewReport.model_validate(
            _clean_report_payload(comparison_payload)
        )

        verified_payload = _invoke_json(
            review_llm,
            VERIFICATION_PROMPT_TEMPLATE.format(
                procurement_markdown=_clip_text(procurement_markdown),
                contract_markdown=_clip_text(contract_markdown),
                procurement_facts=to_pretty_json(procurement_facts.model_dump()),
                contract_facts=to_pretty_json(contract_facts.model_dump()),
                candidate_report=to_pretty_json(candidate_report.model_dump()),
            ),
            fallback=candidate_report.model_dump(),
        )
        report = ContractReviewReport.model_validate(
            _clean_report_payload(verified_payload)
        )

        return to_pretty_json(
            {
                "procurement_markdown_path": str(procurement_path),
                "contract_markdown_path": str(contract_path),
                "prompt_source": "embedded_default" if not prompt_text else "tool_argument",
                "provider": settings.provider,
                "model": settings.model,
                "procurement_facts": procurement_facts.model_dump(),
                "contract_facts": contract_facts.model_dump(),
                "candidate_review_report": candidate_report.model_dump(),
                "review_report": report.model_dump(),
            }
        )

    return compare_contract_markdown
