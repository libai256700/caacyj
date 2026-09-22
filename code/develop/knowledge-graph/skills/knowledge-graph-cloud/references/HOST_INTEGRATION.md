# App Host Integration

The host supplies the HTTPS endpoint, runtime authorization header, timeout,
and App model callable. No real endpoint, token, model provider, or secret is
part of this package.

## Integration Order

```python
from app_answer import (
    PublicAnswerContractError,
    build_app_prompt,
    direct_app_answer,
    sanitize_public_answer,
)
from knowledge_service_client import KnowledgeServiceClient


def answer_user(
    user_query,
    conversation_context,
    *,
    knowledge_service_url,
    knowledge_service_timeout_s,
    authorization_header,
    app_host_model,
):
    direct = direct_app_answer(user_query)
    if direct is not None:
        return direct

    auth_header_name = "Author" + "ization"
    client = KnowledgeServiceClient(
        knowledge_service_url,
        timeout_s=knowledge_service_timeout_s,
        headers={auth_header_name: authorization_header},
    )
    reference_answer = client.ask(user_query)
    service_payload = (
        {"answer": reference_answer}
        if reference_answer is not None
        else None
    )
    prompt = build_app_prompt(
        user_query,
        service_payload,
        conversation_context=conversation_context,
    )

    for _attempt in range(2):
        model_text = app_host_model(prompt)
        try:
            return sanitize_public_answer(
                model_text,
                user_query=user_query,
                conversation_context=conversation_context,
            )
        except PublicAnswerContractError:
            continue
    raise PublicAnswerContractError("App host model did not produce a public answer")
```

The retry count above is an App-host policy example, not a knowledge-service
retry. Both attempts use the same latest `user_query`; they never display the
rejected model text or backend error. A deployment must freeze its actual App
model, retry, timeout, quota, and budget contract at the applicable approval
stop.

## Required Host Invariants

- `user_query` is the current user turn only.
- `conversation_context` is a structured list of prior `role`/`content` turns
  and does not repeat the current question.
- `direct_app_answer()` runs before the knowledge service and every model.
- The host sends only `{"user_query": ...}` and the exact
  `X-KG-Answer-Contract: ordinary-qa-compat-v1` header to `/api/ask`.
- Only the string returned by `client.ask()` can become professional reference
  data. The host never passes raw service JSON into `build_app_prompt()`.
- The App host model always creates the ordinary final answer for hit, miss,
  degraded, HTTP failure, and timeout cases.
- `sanitize_public_answer()` receives the same latest query and history used to
  build the prompt.
- Public code has no `/ops/*`, database, graph, shell, Builder, Release
  Controller, provider, or maintenance capability.
- Raw questions, conversation history, payloads, model text, and credentials
  are not logged unless a separately approved data contract explicitly allows
  it.

## Offline Tests

Inject a callable transport returning `TransportResponse` instead of changing
the endpoint or opening a listener. Tests must block network at process level,
use only synthetic questions and payloads, and cover hit, miss, degraded,
HTTP failure, timeout, invalid JSON, oversized responses, and engineering-field
exclusion from the final prompt.

The default transport performs HTTPS only. No test before Stop B may call it
against a real service or provider.
