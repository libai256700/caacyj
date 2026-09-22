# App Knowledge Service Contract

This contract keeps the public App on the `App-host-final` architecture. The
knowledge service provides optional professional reference text; it does not
produce the customer-facing answer.

## Request

The App performs a read-only HTTPS request to the configured `/api/ask`
endpoint:

```http
POST /api/ask
Content-Type: application/json
Accept: application/json
X-KG-Answer-Contract: ordinary-qa-compat-v1

{"user_query":"<current user turn only>"}
```

The JSON object contains exactly `user_query`. Conversation history, App model
prompts, credentials, provider configuration, maintenance instructions, and
operator context must not be sent. Authentication is injected by the App host
at runtime and is never stored in this skill.

The client accepts only an exact HTTPS `/api/ask` URL without embedded
credentials, query parameters, or fragments. Redirects are rejected so runtime
authorization cannot be forwarded to another endpoint. It performs one request
per call and does not retry. Timeout and response-size limits are explicit
constructor inputs.

## Response Boundary

`KnowledgeServiceClient.ask()` returns only:

- a non-empty natural-language `str` when HTTP succeeded and the payload
  explicitly states `degraded: false`; or
- `None` for a miss, degraded/rejected/error payload, invalid payload, non-2xx
  response, oversized response, connection failure, or timeout.

The raw JSON and its `source`, URL, route, degraded, error, HTTP, trace, claim,
provider, model, cost, or evaluation fields are never returned by the client.
The App must not infer customer-visible text from those fields.

| Service outcome | Client result | App behavior |
| --- | --- | --- |
| Usable hit | `answer` string | Use as optional professional reference |
| Miss or empty answer | `None` | App host model answers normally |
| Degraded/rejected/error | `None` | App host model answers normally |
| HTTP 4xx/5xx | `None` | App host model answers normally |
| Timeout/connection failure | `None` | App host model answers normally |

These outcomes are invisible to the final user. Observability belongs to the
private service plane and must not be reconstructed from the App prompt.

## Final Answer Ownership

The App executes `direct_app_answer()` before this client. If no deterministic
identity answer applies, it converts a non-`None` result to
`{"answer": answer}`, passes that mapping to `build_app_prompt()`, calls the App
host model, and checks the model text with `sanitize_public_answer()`.

Neither the client nor `/api/ask` output may be displayed directly. A sanitizer
failure triggers regeneration for the same latest user question; the original
model text, client error, and service payload are not fallback answers.

Weather and web search remain independent App skills. This client does not
route to them and exposes no operations, database, graph, deployment, or
maintenance capability.
