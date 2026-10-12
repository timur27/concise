# Wire protocol, v1

The server listens on `127.0.0.1:8765` by default. All responses are JSON (`Content-Type: application/json`).

## `POST /v1/score`
Request body: the text to score, raw UTF-8 (`Content-Type: text/plain; charset=utf-8`), at most `max_bytes` bytes.
Surrounding whitespace is trimmed.

`200`:
```json
{"score": 0.1438, "good": false, "threshold": 0.5, "ms": 17}
```
- `score`: the model's probability that the text is concise, 0 to 1.
- `good`: `score >= threshold`. The server owns the threshold.
- `ms`: time spent in the model.

## `GET /v1/health`
`200`:
```json
{"status": "ok", "api": 1, "backend": "base", "max_bytes": 10000}
```
`backend` is `"base"` (Laya's English model) or `"model"` (a fine-tuned model directory).

## Errors
Every error has the same shape:
```json
{"error": {"code": "too_large", "message": "text longer than 10000 bytes"}}
```

| Status | `code` | Meaning |
|---|---|---|
| 400 | `empty_text` | Body is empty or only whitespace |
| 400 | `bad_encoding` | Body is not valid UTF-8 |
| 400 | `bad_request` | Malformed `Content-Length` |
| 404 | `not_found` | Unknown method or path |
| 413 | `too_large` | Body is longer than `max_bytes` |
| 500 | `model_failed` | The model raised an error or replied in an unexpected shape |

Clients should branch on `code`, not on `message`.

## Compatibility
`POST /` is the pre-v1 endpoint. It behaves like `POST /v1/score` and is kept for older clients and quick `curl` checks.
