# API Reference — AI Image Creator

## Supported Models (OpenRouter)

All models use the same OpenRouter `/v1/chat/completions` endpoint and response format. The `modalities` value differs by model type.

| Keyword | Model ID | Modalities | Type |
|---------|----------|------------|------|
| `gemini` | [`google/gemini-3.1-flash-image`](https://openrouter.ai/google/gemini-3.1-flash-image) | `["image", "text"]` | Multimodal (default) |
| `geminipro` | [`google/gemini-3-pro-image`](https://openrouter.ai/google/gemini-3-pro-image) | `["image", "text"]` | Multimodal |
| `riverflow` | [`sourceful/riverflow-v2-pro`](https://openrouter.ai/sourceful/riverflow-v2-pro) | `["image"]` | Image-only |
| `flux2` | [`black-forest-labs/flux.2-max`](https://openrouter.ai/black-forest-labs/flux.2-max) | `["image"]` | Image-only |
| `seedream` | [`bytedance-seed/seedream-4.5`](https://openrouter.ai/bytedance-seed/seedream-4.5) | `["image"]` | Image-only |
| `gpt5` | [`openai/gpt-5-image`](https://openrouter.ai/openai/gpt-5-image) | `["image", "text"]` | Multimodal |
| `gpt5.4` | [`openai/gpt-5.4-image-2`](https://openrouter.ai/openai/gpt-5.4-image-2) | `["image", "text"]` | Multimodal |

**Important:** Image-only models MUST use `"modalities": ["image"]`. Using `["image", "text"]` may cause errors with these models. The script handles this automatically when using keywords.

**Reference image support:** Only multimodal models (gemini, geminipro, gpt5, gpt5.4) support image input for editing and style transfer. Image-only models (riverflow, flux2, seedream) do not accept reference images.

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
