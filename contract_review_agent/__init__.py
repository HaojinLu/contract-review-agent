__all__ = ["build_contract_review_graph", "ProviderSettings"]


def __getattr__(name: str):
    if name == "build_contract_review_graph":
        from contract_review_agent.graph import build_contract_review_graph

        return build_contract_review_graph
    if name == "ProviderSettings":
        from contract_review_agent.llm import ProviderSettings

        return ProviderSettings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
