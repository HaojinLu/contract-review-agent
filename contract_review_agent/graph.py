from __future__ import annotations

from typing import Annotated

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from contract_review_agent.llm import ProviderSettings, create_chat_model
from contract_review_agent.tools import (
    build_contract_review_tool,
    build_convert_to_markdown_tool,
    build_quality_report_tool,
)


class ContractReviewState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


AGENT_SYSTEM_PROMPT = """你是一个双合同审核 Agent，总是以工具优先的方式工作。

工作规则：
1. 如果输入文件是 .pdf 或 .docx，先调用 `convert_contract_to_markdown`
2. 当两份 markdown 都准备好后，再调用 `compare_contract_markdown`
3. 得到比对 JSON 后，调用 `generate_quality_report` 生成质检报告
4. 不要自己伪造条款对比结果，最终结论必须基于工具结果
5. 完成审核后，最终回答输出 JSON，至少包含 review_report 和 report_markdown
6. 证据不足时不要报风险项；普通措辞差异、合同条款更详细或更有利于银行，不得判为矛盾
7. 最终输出必须采用 `compare_contract_markdown` 工具返回的 `review_report`，不要自行新增风险项
8. 文档转换产物必须使用 `convert_contract_to_markdown` 工具默认目录，不要指定临时目录或自定义输出目录

你要重点关注：
- 商务条款匹配度：价格、数量、服务范围
- 时间框架吻合度：交付周期、合同期限
- 法律条款完整性：违约责任、支付条件、保密条款
- 对疑似差异条款做语义级深度分析
"""


def build_contract_review_graph(settings: ProviderSettings):
    model = create_chat_model(settings)
    tools = [
        build_convert_to_markdown_tool(),
        build_contract_review_tool(settings),
        build_quality_report_tool(),
    ]
    tool_node = ToolNode(tools)
    tool_enabled_model = model.bind_tools(tools)

    def agent_node(state: ContractReviewState):
        response = tool_enabled_model.invoke(
            [SystemMessage(content=AGENT_SYSTEM_PROMPT), *state["messages"]]
        )
        return {"messages": [response]}

    graph = StateGraph(ContractReviewState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            END: END,
        },
    )
    graph.add_edge("tools", "agent")
    return graph.compile()
