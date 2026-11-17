# AI Agent Assistant

A local, multi-model chat application that uses the official GitHub Copilot SDK for Python, FastAPI, SQLite, and Streamlit. The model list and model IDs come from the authenticated Copilot runtime; the app does not simulate model responses, scrape VS Code credentials, or hardcode a model catalog.

## Requirements

- Python 3.11 or newer
- A GitHub Copilot account with access to the models you want to use
- The official Copilot runtime and a supported local authentication session

## Installation

From the project directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m copilot download-runtime
```

### Sign in to Copilot

Run the app and select **Sign in with GitHub**. Open the verification link shown on the page, enter the one-time code, and approve the request on GitHub. The app detects successful sign-in and loads the models available to your account. You enter your GitHub credentials only on GitHub, not in this app; no separate CLI sign-in is required.

The app uses the SDK's experimental device-code login API and a Copilot home at `data\copilot` by default. The runtime manages credential storage using the OS credential manager; the app does not collect or log tokens. If secure credential storage is unavailable and the runtime requests plaintext storage, the app declines the flow rather than silently accepting it. A VS Code sign-in alone does not necessarily authenticate this runtime.

## Run

```powershell
streamlit run frontend\app.py
```

The Streamlit app starts the FastAPI backend locally on `127.0.0.1:8765`. To run the API separately instead, start it with:

```powershell
python main.py
```

Then set `API_BASE_URL=http://127.0.0.1:8765` in the environment before launching Streamlit. The backend API documentation is available at `http://127.0.0.1:8765/docs`.

If models cannot be discovered, verify runtime installation, Copilot authentication, and access to at least one model. The application reports the error and does not silently select a substitute.

## Features

- Live SDK model discovery and per-conversation model selection
- Streaming responses, a bottom-pinned chat input, stop-generation action, and tool activity indicators
- Background refresh only while a response or device sign-in is in progress; saved messages stay in place during streaming
- Account-wide premium quota usage, model multiplier, and per-response SDK-reported premium units
- Saved conversations, messages, selected model, SDK session IDs, and tool execution records in SQLite
- Delete a selected chat from the conversation sidebar after confirmation
- Seven SDK-loaded skills under `skills/`
- Registered calculator, date/time, static Python analysis, and read-only workspace file tools
- Safe AST-based arithmetic; user-provided Python is parsed but never executed
- Read-only file tools constrained to `COPILOT_WORKSPACE_DIR`; common dependency directories, credentials, and private-key files are excluded
- Rotating application logs under `logs/`, without logging user prompts, tool arguments, or credentials

Only model IDs returned by `CopilotClient.list_models()` are selectable; an Auto option appears only if the runtime returns it.
To delete a saved chat, select it under **Conversations**, choose **Delete selected chat**, and confirm. This removes its local messages and tool activity; deleting a chat with a response in progress stops that response.
Premium units sum the SDK's per-model-call `assistant.usage` cost multipliers for a response, including tool-loop and sub-agent calls. They are not dollar charges or a billing statement. Account quota is not a per-model percentage. Old responses and calls without reported usage show unavailable; partially reported totals are labeled "at least". Quota and multipliers may be unavailable for some accounts or models. Cancelled or failed requests may consume quota even when no response usage is saved. The SDK's usage cost and account quota APIs are experimental and may change.

## Configuration

Copy `.env.example` to `.env` if you want to configure values, then export them in the shell or load them with your preferred environment manager. `.env` loading is intentionally not implicit.

| Variable | Default | Description |
|---|---|---|
| `COPILOT_WORKSPACE_DIR` | Project root | Root for read-only file tools |
| `DATABASE_PATH` | `data/conversations.sqlite3` | Local SQLite history database |
| `LOG_LEVEL` | `INFO` | Application log level |
| `BACKEND_HOST` | `127.0.0.1` | Local FastAPI bind address |
| `BACKEND_PORT` | `8765` | Local FastAPI port |
| `API_BASE_URL` | Unset | Use an already-running backend instead of starting one |

Conversation content and tool execution results are stored locally in SQLite without application-level encryption. Protect the workspace and database according to your local data-handling requirements.
The SDK stores runtime/session state in a `copilot` directory alongside the configured database. The application uses the SDK's CLI mode to permit OS credential storage and explicitly restricts session tools and ambient capabilities. This mode is intended for a single local user, not shared or multi-tenant deployments.
This project is intended for a single local user and does not provide application-level accounts. Keep the backend on its default loopback address; do not expose it to a network without adding authentication and access controls.

## Tests

Tests use local implementations and mocked SDK sessions; no Copilot subscription or live runtime is needed:

```powershell
python -m pytest
```

## Verified SDK integration

The integration follows the official [`github/copilot-sdk` Python README](https://github.com/github/copilot-sdk/tree/main/python) and SDK source APIs:

- `CopilotClient.start()`, `list_models()`, `create_session()`, and `resume_session()`
- Session `streaming=True`, `skill_directories`, custom `Tool` handlers, and `send_and_wait()`
- `AssistantMessageDeltaData`/session event callbacks for response streaming

The installed and tested SDK version is 1.0.34 (the dependency requires 1.0.34 or newer within major version 1). The SDK is in public preview and may introduce breaking changes. Check its official documentation if upgrading the SDK dependency.
