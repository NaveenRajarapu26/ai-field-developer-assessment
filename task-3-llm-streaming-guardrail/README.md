# Streaming PII Guardrail

This gateway reads an LLM response as it streams and replaces emails, US SSNs, and Luhn-valid card numbers with `[REDACTED]` before sending text to the client.

The tricky part is chunk boundaries. An email might arrive as `john`, then `.smith@`, then `example.com`. Checking each chunk alone would miss it, so the redactor holds unfinished candidates until it can decide what to release.

## Run the local demo

From this task folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux, activate the environment with `source .venv/bin/activate`.

Start the mock provider:

```powershell
python -m uvicorn mock_provider:app --host 127.0.0.1 --port 8001
```

In a second terminal, activate the same environment and start the gateway:

```powershell
python -m uvicorn gateway:app --host 127.0.0.1 --port 8000
```

Then run the client from another terminal:

```powershell
python test_client.py
```

The client sends a prompt to `POST http://127.0.0.1:8000/generate` and prints the redacted stream. No API key is needed for this demo.

A request body looks like this:

```json
{"prompt":"Show customer details"}
```

## How the stream is handled

`gateway.py` reads the provider's SSE events, extracts text deltas, and passes them to `StreamingRedactor` in `redactor.py`. Safe text is returned as SSE events as soon as it can be released.

The redactor keeps a bounded candidate buffer rather than collecting the whole response. If an ambiguous candidate grows beyond the limit, it is replaced with `[REDACTED]`. This can remove some harmless text, but avoids releasing an oversized candidate unchecked.

The gateway also limits SSE line and event sizes. If the provider fails, sends malformed data, or ends without `[DONE]`, the client receives an error event. Raw upstream error details are not included.

## Tests and timing

Run the automated tests without starting either server:

```powershell
python -m pytest -v
```

The tests cover PII split across chunks, adjacent identifiers, normal text, buffer limits, malformed provider events, and upstream failures. A streaming test checks that the first safe output arrives while the provider is still waiting to send the rest.

With the local servers running, you can measure the time to first safe output and total duration:

```powershell
python test_latency.py
```

These timings depend on the mock provider's delays and the local machine. They are useful for checking the demo, rather than measuring production performance.

`test_redactor_demo.py` is also available for trying the redactor on its own.

## Optional provider configuration

The gateway defaults to the local mock. To use an OpenAI-compatible endpoint, set these environment variables in the terminal where you start the gateway:

```powershell
$env:PROVIDER_MODE = "openai_compatible"
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_MODEL = "your-model-name"
$env:LLM_API_KEY = "your-api-key"
```

`.env.example` lists the settings, but the application does not load that file automatically. The optional provider mode has not been validated against a live provider.

## Tradeoffs

Detection focuses on common ASCII emails, US SSNs, and card formats. Unusual encodings, Unicode variants, and other sensitive identifiers need additional rules.

Holding incomplete candidates adds some delay, especially for long words or numeric sequences. Releasing that text earlier would risk exposing part of a sensitive value. Card detection uses a Luhn check to reduce matches on unrelated numbers; numbers with an invalid checksum are left unchanged.
