# API Reference — AI Image Creator

## Supported Models (OpenRouter)

Chat models use the OpenRouter `/v1/chat/completions` endpoint, and their `modalities` value differs by model type. Images-API models use the dedicated `/v1/images` endpoint (see [OpenRouter Images API](#openrouter-images-api-v1images) below).

| Keyword | Model ID | Endpoint | Modalities / limits |
|---------|----------|----------|---------------------|
| `gemini` | [`google/gemini-3.1-flash-image`](https://openrouter.ai/google/gemini-3.1-flash-image) | chat | `["image", "text"]` (default) |
| `gemini-lite` | [`google/gemini-3.1-flash-lite-image`](https://openrouter.ai/google/gemini-3.1-flash-lite-image) | chat | `["image", "text"]`, 1K only |
| `geminipro` | [`google/gemini-3-pro-image`](https://openrouter.ai/google/gemini-3-pro-image) | chat | `["image", "text"]` |
| `riverflow` | [`sourceful/riverflow-v2-pro`](https://openrouter.ai/sourceful/riverflow-v2-pro) | chat | `["image"]` |
| `flux2` | [`black-forest-labs/flux.2-max`](https://openrouter.ai/black-forest-labs/flux.2-max) | chat | `["image"]` |
| `gpt5.4` | [`openai/gpt-5.4-image-2`](https://openrouter.ai/openai/gpt-5.4-image-2) | chat | `["image", "text"]` |
| `seedream` | [`bytedance-seed/seedream-5-0-lite`](https://openrouter.ai/bytedance-seed/seedream-5-0-lite) | images | resolution 2K/4K, 14 refs |
| `gpt-sunburst` | [`openai/gpt-image-2.5-sunburst`](https://openrouter.ai/openai/gpt-image-2.5-sunburst) | images | quality auto→max, background, 16 refs |
| `gpt-flare` | [`openai/gpt-image-2.5-flare`](https://openrouter.ai/openai/gpt-image-2.5-flare) | images | quality auto→max, background, 16 refs |
| `mai` | [`microsoft/mai-image-2.6`](https://openrouter.ai/microsoft/mai-image-2.6) | images | 5 refs |
| `mai-flash` | [`microsoft/mai-image-2.6-flash`](https://openrouter.ai/microsoft/mai-image-2.6-flash) | images | 5 refs |
| `grok` | [`x-ai/grok-imagine-image-2.0`](https://openrouter.ai/x-ai/grok-imagine-image-2.0) | images | resolution 1K/2K, quality low/medium, 3 refs |
| `qwen` | [`qwen/qwen-image-3`](https://openrouter.ai/qwen/qwen-image-3) | images | resolution 1K/2K, 4 refs |
| `qwen-pro` | [`qwen/qwen-image-3-pro`](https://openrouter.ai/qwen/qwen-image-3-pro) | images | resolution 1K/2K, 4 refs |
| `muse` | [`meta/muse-image`](https://openrouter.ai/meta/muse-image) | images | prompt only (no aspect ratio, size or refs) |
| `recraft-flash` | [`recraft/recraft-v4.1-flash`](https://openrouter.ai/recraft/recraft-v4.1-flash) | images | aspect ratio only (no refs) |

**Important:** Image-only chat models MUST use `"modalities": ["image"]`. Using `["image", "text"]` may cause errors with these models. The script handles this automatically when using keywords.

**Reference image support:** Multimodal chat models (gemini, gemini-lite, geminipro, gpt5.4) accept image input via message content. Images-API models accept up to their `input_references` limit (above). Chat image-only models (riverflow, flux2) and `muse`/`recraft-flash` do not accept reference images through this script.

---

## Reference Images (Multimodal Input)

### OpenRouter Format

When sending reference images via OpenRouter, change `messages[0].content` from a string to an array of content parts:

```json
{
  "model": "google/gemini-3.1-flash-image",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Change the background to a sunset scene"},
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,iVBORw0KGgo..."
          }
        }
      ]
    }
  ],
  "modalities": ["image", "text"]
}
```

Multiple images: add additional `image_url` entries to the content array. Text should come first.

### Google AI Studio Format

Add `inline_data` parts alongside the text part:

```json
{
  "contents": [
    {
      "parts": [
        {"text": "Change the background to a sunset scene"},
        {
          "inline_data": {
            "mime_type": "image/png",
            "data": "iVBORw0KGgo..."
          }
        }
      ]
    }
  ]
}
```

### Supported Input Formats

PNG, JPEG, WebP, GIF. Images are base64-encoded inline (data URLs for OpenRouter, inline_data for Google).

---

## Providers & Endpoints

### OpenRouter (via CF AI Gateway)

**Gateway URL:**
```
https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/openrouter/v1/chat/completions
```

**Direct URL:**
```
https://openrouter.ai/api/v1/chat/completions
```

**Request format (OpenAI-compatible):**
```json
{
  "model": "google/gemini-3.1-flash-image",
  "messages": [
    {"role": "user", "content": "Generate a beautiful sunset over mountains"}
  ],
  "modalities": ["image", "text"],
  "image_config": {
    "aspect_ratio": "16:9",
    "image_size": "1K"
  }
}
```

**Response format:**
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Here is your generated image",
        "images": [
          {
            "image_url": {
              "url": "data:image/png;base64,iVBORw0KGgo..."
            }
          }
        ]
      }
    }
  ]
}
```

**Image extraction:** `choices[0].message.images[0].image_url.url` — strip `data:image/png;base64,` prefix, then base64 decode.

**curl example (gateway):**
```bash
curl -s -X POST \
  "https://gateway.ai.cloudflare.com/v1/${AI_IMG_CREATOR_CF_ACCOUNT_ID}/${AI_IMG_CREATOR_CF_GATEWAY_ID}/openrouter/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "cf-aig-authorization: Bearer ${AI_IMG_CREATOR_CF_TOKEN}" \
  -d '{
    "model": "google/gemini-3.1-flash-image",
    "messages": [{"role": "user", "content": "A blue circle on white background"}],
    "modalities": ["image", "text"]
  }'
```

**curl example (direct):**
```bash
curl -s -X POST \
  "https://openrouter.ai/api/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${AI_IMG_CREATOR_OPENROUTER_KEY}" \
  -d '{
    "model": "google/gemini-3.1-flash-image",
    "messages": [{"role": "user", "content": "A blue circle on white background"}],
    "modalities": ["image", "text"]
  }'
```

---

### OpenRouter Images API (`/v1/images`)

Used by every registry entry marked `"api": "images"`. The script builds the URL, body and headers itself; the same BYOK headers apply as for chat.

**Gateway URL:**
```
https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/openrouter/v1/images
```

**Direct URL:**
```
https://openrouter.ai/api/v1/images
```

**Request format:** flat fields rather than `messages`/`image_config`. The script sends only the fields the model supports:
```json
{
  "model": "openai/gpt-image-2.5-flare",
  "prompt": "A friendly robot mascot",
  "aspect_ratio": "1:1",
  "resolution": "2K",
  "quality": "high",
  "background": "transparent",
  "input_references": [
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo..."}}
  ]
}
```

`-a` → `aspect_ratio`, `-s` → `resolution`, `--quality` → `quality`, native `-t` → `background: "transparent"`, `-r` → `input_references`.

**Response format:**
```json
{
  "data": [{"b64_json": "iVBORw0KGgo...", "media_type": "image/png"}],
  "usage": {"prompt_tokens": 0, "completion_tokens": 4175, "total_tokens": 4175, "cost": 0.04}
}
```

**Image extraction:** base64-decode `data[0].b64_json`. Billing is all-or-nothing: a failed generation is not charged. `usage.cost` (USD) is recorded in the cost log.

**Per-model capabilities:** `GET https://openrouter.ai/api/v1/images/models` (free) returns each model's `supported_parameters` (value lists, max `input_references`). The registry `caps` mirror it; re-check it when adding or updating a model.

---

### Google AI Studio (via CF AI Gateway)

**Gateway URL:**
```
https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/google-ai-studio/v1beta/models/{model}:generateContent
```

**Direct URL:**
```
https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
```

**Request format (Gemini native):**
```json
{
  "contents": [
    {
      "parts": [
        {"text": "Generate a beautiful sunset over mountains"}
      ]
    }
  ]
}
```

**Response format:**
```json
{
  "candidates": [
    {
      "content": {
        "parts": [
          {"text": "Here is your generated image"},
          {
            "inlineData": {
              "mimeType": "image/png",
              "data": "iVBORw0KGgo..."
            }
          }
        ]
      }
    }
  ]
}
```

**Image extraction:** Iterate `candidates[0].content.parts[]`, find the part with `inlineData`, then base64 decode `inlineData.data`.

**curl example (gateway):**
```bash
curl -s -X POST \
  "https://gateway.ai.cloudflare.com/v1/${AI_IMG_CREATOR_CF_ACCOUNT_ID}/${AI_IMG_CREATOR_CF_GATEWAY_ID}/google-ai-studio/v1beta/models/gemini-3.1-flash-image:generateContent" \
  -H "Content-Type: application/json" \
  -H "cf-aig-authorization: Bearer ${AI_IMG_CREATOR_CF_TOKEN}" \
  -H "cf-aig-byok-alias: aistudio" \
  -d '{
    "contents": [{"parts": [{"text": "A blue circle on white background"}]}]
  }'
```

**curl example (direct):**
```bash
curl -s -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image:generateContent" \
  -H "Content-Type: application/json" \
  -H "x-goog-api-key: ${AI_IMG_CREATOR_GEMINI_KEY}" \
  -d '{
    "contents": [{"parts": [{"text": "A blue circle on white background"}]}]
  }'
```

---

## CF AI Gateway BYOK Headers

| Header | Purpose |
|--------|---------|
| `cf-aig-authorization: Bearer {token}` | Gateway authentication (required if auth enabled) |
| `cf-aig-byok-alias: {alias}` | Select which stored provider key to use (default: `default`) |
| `cf-aig-cache-ttl: {seconds}` | Cache responses for N seconds (optional) |

**Configured BYOK aliases:**
- `default` — OpenRouter API key
- `aistudio` — Google AI Studio API key

---

## Supported Aspect Ratios (OpenRouter `image_config`)

| Ratio | Pixels | Notes |
|-------|--------|-------|
| `1:1` | 1024x1024 | Default if not specified |
| `2:3` | 832x1248 | Portrait |
| `3:2` | 1248x832 | Landscape |
| `3:4` | 864x1184 | Portrait |
| `4:3` | 1184x864 | Landscape |
| `4:5` | 896x1152 | Portrait |
| `5:4` | 1152x896 | Landscape |
| `9:16` | 768x1344 | Mobile/vertical |
| `16:9` | 1344x768 | Widescreen |
| `21:9` | 1536x672 | Ultra-wide |
| `1:4` | Tall narrow | Gemini 3.1 Flash only |
| `4:1` | Wide short | Gemini 3.1 Flash only |

## Supported Image Sizes (OpenRouter `image_config`)

| Size | Description |
|------|-------------|
| `0.5K` | Lower resolution, efficient (Gemini 3.1 Flash only) |
| `1K` | Standard resolution (default) |
| `2K` | Higher resolution |
| `4K` | Highest resolution |

---

## Error Response Formats

**OpenRouter error:**
```json
{
  "error": {
    "message": "Description of the error",
    "code": 400
  }
}
```

**Google AI Studio error (safety block):**
```json
{
  "promptFeedback": {
    "blockReason": "SAFETY"
  }
}
```

**Google AI Studio error (no image generated):**
Response has `candidates[0].content.parts` with only `text` parts and no `inlineData`.
