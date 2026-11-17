from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from copilot.generated.rpc import (
    AuthLoginAdvanceRequest,
    AuthLoginBeginRequest,
    AuthLoginCancelRequest,
    AuthLoginMethod,
    AuthLoginResultStatus,
    AuthLoginStepKind,
    LoginProviderKind,
)
from copilot.session import CopilotSession

from backend.copilot_client import CopilotGateway

logger = logging.getLogger(__name__)


class AuthenticationManager:
    """Manage one local, browser-authorized SDK device login."""

    def __init__(self, gateway: CopilotGateway) -> None:
        self.gateway = gateway
        self._lock = asyncio.Lock()
        self._session: CopilotSession | None = None
        self._flow_id: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._state: dict[str, object] = {"status": "idle"}

    def status(self) -> dict[str, object]:
        return dict(self._state)

    async def start(self) -> dict[str, object]:
        async with self._lock:
            if self._task is not None and not self._task.done():
                return self.status()
            if await self.gateway.is_authenticated():
                self._state = {"status": "authenticated"}
                return self.status()

            client = self.gateway.client
            if client is None:
                raise RuntimeError("Copilot runtime is not started.")

            session = await client.create_session(
                available_tools=[],
                enable_config_discovery=False,
                skip_custom_instructions=True,
                enable_on_demand_instruction_discovery=False,
                enable_file_hooks=False,
                enable_host_git_operations=False,
                enable_session_telemetry=False,
                enable_skills=False,
                included_builtin_skills=[],
                memory={"enabled": False},
            )
            try:
                flow = await session.rpc.accounts.login.begin(
                    AuthLoginBeginRequest(
                        kind=LoginProviderKind.GITHUB_DOT_COM,
                        method=AuthLoginMethod.DEVICE_CODE,
                    )
                )
                step = flow.step
                parsed_uri = urlparse(step.verification_uri or "")
                if (
                    step.kind != AuthLoginStepKind.DEVICE_CODE
                    or not step.user_code
                    or parsed_uri.scheme != "https"
                    or parsed_uri.hostname != "github.com"
                    or parsed_uri.path != "/login/device"
                    or parsed_uri.username is not None
                    or parsed_uri.password is not None
                    or parsed_uri.port not in (None, 443)
                ):
                    await session.rpc.accounts.login.cancel(
                        AuthLoginCancelRequest(flow_id=flow.flow_id)
                    )
                    raise RuntimeError("The Copilot runtime returned an unsupported login step.")
            except BaseException:
                await session.disconnect()
                raise

            self._session = session
            self._flow_id = flow.flow_id
            self._state = {
                "status": "pending",
                "user_code": step.user_code,
                "verification_uri": step.verification_uri,
                "expires_in": step.expires_in,
            }
            self._task = asyncio.create_task(
                self._advance(session, flow.flow_id, step.expires_in),
                name="copilot-device-login",
            )
            logger.info("Copilot device sign-in started")
            return self.status()

    async def _advance(
        self, session: CopilotSession, flow_id: str, expires_in: int | None
    ) -> None:
        try:
            timeout = max(1, expires_in or 900)
            step = await asyncio.wait_for(
                session.rpc.accounts.login.advance(
                    AuthLoginAdvanceRequest(flow_id=flow_id),
                    timeout=timeout + 5,
                ),
                timeout=timeout + 5,
            )
            if (
                step.kind == AuthLoginStepKind.COMPLETED
                and step.result is not None
                and step.result.status == AuthLoginResultStatus.COMPLETED
            ):
                if await self.gateway.is_authenticated():
                    self._state = {"status": "authenticated"}
                    logger.info("Copilot device sign-in completed")
                else:
                    self._state = {
                        "status": "error",
                        "message": "Sign-in completed, but the Copilot runtime did not report an authenticated account.",
                    }
            elif (
                step.result is not None
                and step.result.status == AuthLoginResultStatus.NEEDS_PLAINTEXT_CONSENT
            ):
                self._state = {
                    "status": "error",
                    "message": (
                        "The runtime requested permission to store credentials in plaintext. "
                        "Sign-in was not completed. Check that the OS credential manager is available, "
                        "then try again."
                    ),
                }
            else:
                self._state = {
                    "status": "error",
                    "message": "GitHub sign-in did not complete. Please try again.",
                }
                logger.warning("Copilot device sign-in ended with step %s", step.kind.value)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            self._state = {"status": "error", "message": "The sign-in code expired. Please try again."}
        except Exception as exc:
            logger.warning("Copilot device sign-in failed (%s)", type(exc).__name__)
            self._state = {"status": "error", "message": "GitHub sign-in failed. Please try again."}
        finally:
            try:
                await session.rpc.accounts.login.cancel(AuthLoginCancelRequest(flow_id=flow_id))
            except Exception as exc:
                logger.debug("Login flow cleanup: %s", type(exc).__name__)
            try:
                await session.disconnect()
            except Exception as exc:
                logger.warning("Could not close the sign-in session (%s)", type(exc).__name__)
            finally:
                self._session = None
                self._flow_id = None

    async def cancel(self) -> None:
        async with self._lock:
            task = self._task
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._task = None
            self._state = {"status": "idle"}
