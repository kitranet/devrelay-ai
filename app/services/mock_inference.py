"""Deterministic, offline provider for tests and local development."""

import json

from app.models.inference import ChatMessage, InferenceResponse

_SCENARIOS = {
    "mock://health": "MOCK RESPONSE: inference provider is ready.",
    "mock://repository-summary": "MOCK RESPONSE: repository analysis summary scenario.",
    "mock://handoff-summary": "MOCK RESPONSE: engineering handoff summary scenario.",
}


class MockModelProvider:
    async def complete(
        self,
        messages: list[ChatMessage],
        max_tokens: int = 1024,
        *,
        disable_thinking: bool = False,
        json_mode: bool = False,
    ) -> InferenceResponse:
        # Mock outputs are fixed; provider generation options have no effect.
        del max_tokens, disable_thinking, json_mode
        scenario = next((message.content for message in reversed(messages) if message.role == "user"), "")
        content = _SCENARIOS.get(scenario)
        if content is None and scenario.startswith("DEVRELAY_PLAN_REQUEST\n"):
            content = self._plan_response(scenario.removeprefix("DEVRELAY_PLAN_REQUEST\n"))
        if content is None:
            content = "MOCK RESPONSE: no matching inference scenario."
        return InferenceResponse(
            model="devrelay-mock-v1",
            content=content,
            provider="mock",
            is_mock=True,
            completion_status="completed",
            finish_reason="mock_complete",
            model_reported_by_provider=True,
            usage=None,
        )

    @staticmethod
    def _plan_response(encoded_context: str) -> str:
        """Support only explicit evaluation scenarios; never invent a generic plan."""
        try:
            context = json.loads(encoded_context)
            task = str(context["task_description"]).lower()
            available_files = set(context["available_files"])
            references = context["source_references"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return MockModelProvider._unsupported_plan()

        if "division by zero" in task:
            files = ["package/calculator.py", "tests/test_calculator.py"]
            steps = [
                "Inspect the division operation and its current edge-case behavior.",
                "Add a focused zero-divisor regression test, then implement the chosen error behavior.",
                "Run the calculator test module and the full test suite.",
            ]
            risk = "The intended zero-divisor behavior is unspecified; confirm whether to raise or return a sentinel."
        elif "api" in task and ("validation" in task or "validate" in task):
            files = ["package/api.py", "tests/test_api.py"]
            steps = [
                "Inspect the API input model and existing validation conventions.",
                "Add validation cases for valid, missing, and malformed input.",
                "Implement validation at the API boundary and run focused and full tests.",
            ]
            risk = "The accepted input range is not specified and needs confirmation."
        elif "unfamiliar" in task and "dependenc" in task:
            files = ["package/service.py", "package/dependencies.py", "tests/test_service.py"]
            steps = [
                "Trace the target function's imports and callers before proposing a change.",
                "Inspect dependency behavior and the existing service tests.",
                "Add characterization tests for observed behavior and run focused and full tests.",
            ]
            risk = "The requested behavior is exploratory; no implementation change should be made until expected behavior is clarified."
        else:
            return MockModelProvider._unsupported_plan()

        # Emit only traceable references present in the supplied analysis context.
        selected_refs = [ref for ref in references if ref.get("path") in files]
        known = available_files
        missing = [path for path in files if path not in known]
        if missing or not selected_refs:
            return MockModelProvider._unsupported_plan()
        first_ref = selected_refs[0]
        return json.dumps({
            "status": "planned",
            "relevant_files": files,
            "source_references": selected_refs[:10],
            "implementation_steps": [
                {"step": index, "description": description, "source_references": [first_ref]}
                for index, description in enumerate(steps, start=1)
            ],
            "expected_code_changes": [
                {"path": files[0], "description": "Proposed change; requires human approval."}
            ],
            "risks": [risk],
            "dependencies": [],
            "validation_requirements": [f"Run {path}" for path in files if path.startswith("tests/")],
            "assumptions": [],
        })

    @staticmethod
    def _unsupported_plan() -> str:
        return json.dumps({
            "status": "unsupported",
            "relevant_files": [],
            "source_references": [],
            "implementation_steps": [],
            "expected_code_changes": [],
            "risks": [],
            "dependencies": [],
            "validation_requirements": [],
            "assumptions": [],
        })
