# Setting up token-level telemetry for Copilot Studio

Copilot Studio meters generative AI in **messages / Copilot Credits**, not tokens.
To capture **real token counts**, emit a custom Application Insights event at the point
the model is called, then notebook `03_copilotstudio_appinsights_tokens.py` reads it back.

## Option A — Custom event from a Power Automate flow / connector
If your agent calls Azure OpenAI (or an API returning token usage) via a Power Automate
flow, add a step that sends a custom event to Application Insights using the
**Track Event** action or an HTTP POST to the App Insights ingestion endpoint.

Send an event named `TokenUsage` with these `customDimensions`:

| Dimension          | Example        | Source                                   |
| ------------------ | -------------- | ---------------------------------------- |
| `conversationId`   | `abc-123`      | `System.Conversation.Id`                 |
| `agentId`          | `agent-hr-bot` | your agent name/id                       |
| `model`            | `gpt-4o`       | model deployment name                    |
| `promptTokens`     | `812`          | `usage.prompt_tokens` from the API reply |
| `completionTokens` | `240`          | `usage.completion_tokens`                |
| `totalTokens`      | `1052`         | `usage.total_tokens`                     |

## Option B — Skill / Azure Function in front of the model
Route model calls through an Azure Function. In the function, read `response.usage`
and log it. Example (Python):

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace

configure_azure_monitor(connection_string=APPINSIGHTS_CONNECTION_STRING)
tracer = trace.get_tracer(__name__)

def log_token_usage(usage, conversation_id, agent_id, model):
    with tracer.start_as_current_span("TokenUsage") as span:
        span.set_attribute("conversationId", conversation_id)
        span.set_attribute("agentId", agent_id)
        span.set_attribute("model", model)
        span.set_attribute("promptTokens", usage.prompt_tokens)
        span.set_attribute("completionTokens", usage.completion_tokens)
        span.set_attribute("totalTokens", usage.total_tokens)
```

> The KQL in notebook 03 looks for events named `TokenUsage` or `GenAITokenUsage`.
> Keep the dimension names identical so the parser lines up.

## Verify it flows
1. Trigger a conversation that calls the model.
2. In Application Insights → Logs, run:
   ```kql
   customEvents | where name == "TokenUsage" | take 20
   ```
3. Once rows appear, run notebook `03` — data lands in `bronze_copilotstudio_token_usage`.
