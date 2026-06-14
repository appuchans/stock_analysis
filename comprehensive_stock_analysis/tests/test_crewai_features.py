"""Tests for CrewAI feature adoption: rate limits, guardrails, markdown, date injection."""

from src.stock_analysis.crew.flow_crew import _narrative_guardrail


class TestAgentSafetyFeatures:
    def test_agents_carry_rpm_retry_cache_and_date_settings(self):
        from src.stock_analysis.agents.base_agent import BaseAgent

        agent = BaseAgent("fundamental_analyst").get_agent()
        assert agent.max_rpm == 10
        assert agent.max_retry_limit == 1
        assert agent.max_execution_time == 300
        assert agent.cache is True
        assert agent.inject_date is True


class TestNarrativeGuardrail:
    def test_guardrail_attaches_to_a_real_task(self):
        """CrewAI validates the guardrail's return annotation at Task construction;
        a bare 'tuple' annotation is rejected. Guard against that regression."""
        from crewai import Task
        from src.stock_analysis.agents import ReportGeneratorAgent

        agent = ReportGeneratorAgent().get_agent()
        # Must not raise a pydantic ValidationError
        Task(
            description="d", expected_output="o", agent=agent,
            guardrail=_narrative_guardrail, guardrail_max_retries=1, markdown=True,
        )

    def test_accepts_real_narrative(self):
        doc = ("## Investment Thesis\nBuy, $290 target.\n## Business Overview\ntext\n"
               "## Valuation & Recommendation\ntext\n")
        ok, payload = _narrative_guardrail(doc)
        assert ok is True
        assert "Business Overview" in payload

    def test_rejects_narrative_without_thesis(self):
        doc = ("## Business Overview\ntext\n## Financial Performance\ntext\n"
               "## Valuation & Recommendation\ntext\n")
        ok, feedback = _narrative_guardrail(doc)
        assert ok is False
        assert "Investment Thesis" in feedback

    def test_rejects_status_summary(self):
        summary = ("Completed formatting enforcement for the narrative and "
                   "regenerated the report. File written to reports/X.html.")
        ok, feedback = _narrative_guardrail(summary)
        assert ok is False
        assert "narrative document itself" in feedback

    def test_strips_code_fences_before_checking(self):
        doc = "```markdown\n## Investment Thesis\nx\n## B\ny\n## C\nz\n```"
        ok, _ = _narrative_guardrail(doc)
        assert ok is True
