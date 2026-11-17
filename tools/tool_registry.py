from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

from copilot import Tool, ToolInvocation, ToolResult
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from database.repositories import ConversationRepository
from tools.calculator_tools import calculate
from tools.datetime_tools import (
    calculate_date_difference,
    get_current_date,
    get_current_datetime,
    get_current_time,
)
from tools.file_tools import read_file, search_files
from tools.python_tools import analyze_python_code

logger = logging.getLogger(__name__)


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TwoNumbers(Parameters):
    a: float
    b: float


class PercentageParameters(Parameters):
    value: float
    percent: float


class PowerParameters(Parameters):
    base: float
    exponent: float


class OneNumber(Parameters):
    value: float


class ExpressionParameters(Parameters):
    expression: str = Field(min_length=1, max_length=512)


class DateRangeParameters(Parameters):
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class PythonAnalysisParameters(Parameters):
    code: str = Field(min_length=1, max_length=20_000)
    task: str = Field(default="analyze", pattern=r"^(analyze|explain|improve)$")


class SearchFilesParameters(Parameters):
    query: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=20, ge=1, le=50)


class ReadFileParameters(Parameters):
    path: str = Field(min_length=1, max_length=500)


Executor = Callable[[dict[str, Any]], dict[str, object]]


def _calculator(name: str) -> Executor:
    return lambda values: calculate(name, **values)


class ToolRegistry:
    def __init__(
        self,
        conversation_id: str,
        repository: ConversationRepository,
        emit: Callable[[dict[str, object]], None],
    ) -> None:
        self.conversation_id = conversation_id
        self.repository = repository
        self.emit = emit
        self.specs: dict[str, tuple[str, type[Parameters], Executor]] = {
            "calculator_add": (
                "Add two numbers.",
                TwoNumbers,
                _calculator("add"),
            ),
            "calculator_subtract": (
                "Subtract b from a.",
                TwoNumbers,
                _calculator("subtract"),
            ),
            "calculator_multiply": (
                "Multiply two numbers.",
                TwoNumbers,
                _calculator("multiply"),
            ),
            "calculator_divide": (
                "Divide a by b; reports division by zero as an error.",
                TwoNumbers,
                _calculator("divide"),
            ),
            "calculator_percentage": (
                "Calculate a percentage of a value.",
                PercentageParameters,
                _calculator("percentage"),
            ),
            "calculator_power": (
                "Raise a base to a numeric exponent.",
                PowerParameters,
                _calculator("power"),
            ),
            "calculator_square_root": (
                "Calculate the non-negative square root of a value.",
                OneNumber,
                _calculator("square_root"),
            ),
            "calculator_evaluate_expression": (
                "Evaluate a safe arithmetic expression using numeric literals and basic operators.",
                ExpressionParameters,
                lambda values: calculate("evaluate_expression", **values),
            ),
            "get_current_datetime": (
                "Get the current local date, time, and timezone.",
                Parameters,
                lambda _: get_current_datetime(),
            ),
            "get_current_date": (
                "Get the current local calendar date.",
                Parameters,
                lambda _: get_current_date(),
            ),
            "get_current_time": (
                "Get the current local time.",
                Parameters,
                lambda _: get_current_time(),
            ),
            "calculate_date_difference": (
                "Find the signed day difference between two ISO dates (YYYY-MM-DD).",
                DateRangeParameters,
                lambda values: calculate_date_difference(**values),
            ),
            "analyze_python_code": (
                "Statically analyze, explain, or suggest improvements to Python source without executing it.",
                PythonAnalysisParameters,
                lambda values: analyze_python_code(**values),
            ),
            "search_workspace_files": (
                "Search filenames in the configured workspace; hidden credential files and dependency folders are excluded.",
                SearchFilesParameters,
                lambda values: search_files(**values),
            ),
            "read_workspace_file": (
                "Read a UTF-8 text file within the configured workspace, excluding credential files.",
                ReadFileParameters,
                lambda values: read_file(**values),
            ),
        }

    def build(self) -> list[Tool]:
        tools: list[Tool] = []
        for name, (description, parameters, executor) in self.specs.items():
            tools.append(
                Tool(
                    name=name,
                    description=description,
                    parameters=parameters.model_json_schema(),
                    handler=self._handler(name, parameters, executor),
                    skip_permission=True,
                    idempotent=True,
                )
            )
        return tools

    def _handler(
        self,
        name: str,
        parameter_type: type[Parameters],
        executor: Executor,
    ) -> Callable[[ToolInvocation], ToolResult]:
        def execute(invocation: ToolInvocation) -> ToolResult:
            started = time.perf_counter()
            arguments = invocation.arguments
            self.emit({"type": "tool_start", "tool_name": name})
            logger.info("Tool started: %s", name)
            try:
                validated = parameter_type.model_validate(arguments)
                values = validated.model_dump()
                result = executor(values)
                serialized = json.dumps(result, ensure_ascii=True, default=str)
                self.repository.add_tool_execution(
                    self.conversation_id, name, values, result, "success"
                )
                logger.info(
                    "Tool completed: %s duration_ms=%.2f",
                    name,
                    (time.perf_counter() - started) * 1000,
                )
                self.emit({"type": "tool_complete", "tool_name": name, "status": "success"})
                return ToolResult(
                    text_result_for_llm=serialized,
                    result_type="success",
                    session_log=f"Completed {name}",
                )
            except (ValidationError, ValueError, TypeError, OverflowError) as exc:
                result = {"error": str(exc)}
                self.repository.add_tool_execution(
                    self.conversation_id,
                    name,
                    arguments if isinstance(arguments, dict) else {},
                    result,
                    "failure",
                )
                logger.warning("Tool rejected: %s (%s)", name, type(exc).__name__)
                self.emit({"type": "tool_complete", "tool_name": name, "status": "failure"})
                return ToolResult(
                    text_result_for_llm=json.dumps(result),
                    result_type="failure",
                    error=str(exc),
                )
            except Exception:
                self.repository.add_tool_execution(
                    self.conversation_id,
                    name,
                    arguments if isinstance(arguments, dict) else {},
                    {"error": "Internal tool error."},
                    "failure",
                )
                logger.exception("Unexpected tool failure: %s", name)
                self.emit({"type": "tool_complete", "tool_name": name, "status": "failure"})
                return ToolResult(
                    text_result_for_llm='{"error":"Internal tool error."}',
                    result_type="failure",
                    error="Internal tool error.",
                )

        return execute
