# Category-Specific Prompt Patterns

Each category provides a **formula template**, **key elements**, **recommended model**, and a **complete example prompt**. Read only the section matching the detected category.

---

## product_hero

**Studio product photography** — Clean, professional shots with controlled lighting.

**Formula:**
```
Create a [lighting] product photograph of [detailed product description]
on/against [surface/background]. Shot with [camera] [lens] at [aperture].
[Lighting description]. [Composition notes]. [Mood/atmosphere].
```

**Key Elements:** Camera hardware, specific surface material, lighting direction/quality, product texture/finish/color, atmosphere

**Recommended model:** `gemini` or `gpt5.4`

**Example:**
> Create a cinematic product photograph of a matte-black wireless headphone on a polished obsidian surface. Shot with Sony A7R IV, 85mm macro lens at f/2.8, 45-degree product angle. Single soft key light from upper-left creates gentle shadows that define the headphone's contours, with a subtle reflection in the obsidian surface. Deep shadows on the right add drama and luxury. The headphone's ear cushion texture is clearly visible — soft leather grain catching the light. Dark, moody atmosphere with rich tonal depth. 4:5 aspect ratio.

---

## lifestyle

**Products in real-world settings** — Environmental storytelling with aspirational context.

**Formula:**
```
Create a [mood] lifestyle photograph showcasing [product] in [real-world setting].
[Environmental details — props, furniture, plants]. [Lighting — natural preferred].
[Human interaction if any]. Shot with [camera] [lens] at [aperture].
```

**Key Elements:** Environmental storytelling, natural lighting, contextual props, aspirational setting, human touch

**Recommended model:** `gemini` or `gpt5.4`

**Example:**
> Create a warm, inviting lifestyle photograph showcasing a compact walnut bookshelf speaker in a cozy reading nook. The speaker sits on a mid-century modern side table beside a plush armchair with a knitted throw blanket. A half-drunk cup of coffee and an open paperback add lived-in charm. Warm afternoon light streams through linen curtains, casting soft shadows across the scene. Shot with Sony A7III, 35mm lens at f/2.8. The composition draws the eye from the warm light to the speaker naturally. Aspirational but attainable — the kind of moment you want to step into.

---

## social_media

**Platform-optimized graphics** — Designed for scroll-stopping impact.

**Formula:**
```
Create a [platform]-optimized [style] image of [subject].
[Composition for scroll-stopping impact]. [Bold colors/high contrast].
[Aspect ratio from prompt-platforms.md]. [Text if any, in quotes].
```

**Key Elements:** Platform-specific ratio, high visual impact in first 50ms, bold colors, clear focal point, text integration

**Recommended model:** `gemini` or `seedream`

**Example:**
> Create a vibrant, scroll-stopping Instagram feed image featuring an artisanal honey jar with a hand-lettered label reading "GOLDEN GROVE" positioned on a rustic wooden board with a honey dipper and scattered wildflowers. Morning sunlight creates a golden backlit glow through the honey, making it luminous. Shot with Canon R5, 100mm macro at f/2.8 for tight detail with dreamy background blur. Bold warm color palette — amber, gold, cream, forest green from the herbs. The composition places the jar at the left-third power point with the honey dipper creating a diagonal leading line. 4:5 vertical format.

---

## marketing_banner

**Web banners, email headers, ad creatives** — Designed with text overlay zones.

**Formula:**
```
Create a [width:height] marketing banner for [product/campaign].
[Product positioned in left/right third]. [Large negative space zone on opposite side
for text overlay]. [Brand colors]. [Clean, professional composition].
```

**Key Elements:** Deliberate negative space for copy, brand color integration, clean zones, product positioning, CTA area

**Recommended model:** `gemini`

**Example:**
> Create a 16:9 widescreen marketing banner for a premium coffee subscription service. A steaming ceramic mug of dark coffee positioned in the right third of the frame, with wisps of steam rising against a warm, blurred café background. The entire left two-thirds is clean negative space with a soft gradient from warm brown to cream, designed for headline text and CTA button overlay. Professional, inviting atmosphere with golden ambient lighting. Muted earth tones — espresso brown, warm cream, subtle copper accents.

---

## web_app

**Website/app logos, banners, ad format creatives** — Professional digital assets with standard sizing.

**Formula:**
```
Create a [style] [asset type] for [brand/product].
[Dimensions/format from prompt-platforms.md]. [Brand elements].
[Text in quotes if any]. [Background specification].
[CTA zone / layout zones if ad format].
```

**Key Elements:** Standard ad sizes (IAB), favicon/logo constraints, CTA zones, brand consistency, responsive considerations

**Recommended model:** `gemini` (best text rendering)

**Example (logo):**
> Create a clean, modern website logo for a timezone scheduling tool. Simple globe icon with vertical meridian lines suggesting time zones, rendered in a flat design style with two colors: deep navy blue and bright teal accent. The globe shape must be recognizable at 32x32 pixels. Solid white background. No gradients, no 3D effects — pure flat vector aesthetic.

**Example (leaderboard ad):**
> Create a 4:1 wide horizontal leaderboard banner ad for a SaaS productivity app. Clean white background with a laptop mockup showing the app interface in the left quarter. The right three-quarters features large clean space for headline text. Accent color: electric blue (#0066FF) used sparingly for a thin border and small CTA button zone in the lower-right. Professional, minimal, corporate aesthetic. Sharp edges, no rounded corners on the overall banner.

---

## icon_logo

**App icons, favicons, brand marks** — Must work at tiny sizes.

**Formula:**
```
Create a [style] icon/logo of [subject]. Simple, recognizable silhouette
that reads clearly at [target size]. Maximum [N] colors on [background].
[Shape constraints]. No fine detail — bold shapes only.
```

**Key Elements:** Readability at small sizes, bold silhouette, limited colors, solid background, simple geometry

**Recommended model:** `gemini`

**Example:**
> Create a flat-design app icon of a world clock. A simplified globe shape with 3 vertical timezone band lines in teal and navy blue, with a small clock hand overlay at the 12 o'clock position. Pure white background. Maximum 3 colors. The icon must be recognizable at 32x32 pixels — bold shapes, no thin lines, no fine detail. Clean vector style suitable for iOS and Android app stores. Square format, 1:1 aspect ratio.

---

## illustration

**Characters, mascots, creative artwork** — Artistic and expressive.

**Formula:**
```
Create a [style] illustration of [subject/character].
[Composition and pose]. [Color palette]. [Art style direction].
[Level of detail]. [Background treatment].
```

**Key Elements:** Style direction (flat, realistic, anime, watercolor, etc.), composition, color palette, character design, background

**Recommended model:** `riverflow` or `flux2`

**Example:**
> Create a charming flat-illustration mascot character of a friendly robot holding a coffee mug. The robot has a rounded rectangular body in brushed silver with a glowing teal chest panel, stubby arms, and expressive dot eyes with a slight smile. It holds an oversized white ceramic mug with both hands. Warm, inviting pose slightly tilted. Color palette: silver, teal, white, warm amber highlights. Clean line work, subtle gradients for dimension. Solid light grey background. Suitable for web app branding — must look friendly and approachable, not threatening.

---

## food_drink

**Food and beverage photography** — Appetizing and detailed.

**Formula:**
```
Create a [mood] food photograph of [dish/beverage description].
[Styling details — garnish, props, surface]. [Steam/condensation/texture].
Shot with [camera] [macro lens] at [aperture].
[Lighting — natural preferred]. [Color temperature].
```

**Key Elements:** Macro lens detail, food styling (garnish, drips, steam), appetizing color temperature, surface/props

**Recommended model:** `gemini` or `gpt5.4`

**Example:**
> Create a warm, appetizing overhead photograph of a rustic sourdough pizza fresh from a wood-fired oven. Bubbling mozzarella with golden-brown leopard spots, scattered fresh basil leaves, a drizzle of olive oil catching the light. The pizza sits on a weathered wooden cutting board with a pizza cutter, scattered flour, and a small bowl of chili flakes nearby. Shot with Canon R5, 100mm macro lens at f/2.8. Warm natural window light from the left creating gentle shadows. Steam rising from the cheese. Rich, warm color palette — golden crust, vivid green basil, white mozzarella, deep red sauce peeking through.

---

## architecture

**Interior and exterior spaces** — Accurate perspective and materials.

**Formula:**
```
Create a [style] architectural photograph of [space/building description].
[Materials and finishes]. [Perspective and composition].
Shot with [wide-angle lens] at [aperture].
[Lighting — time of day, ambient]. [Atmosphere/mood].
```

**Key Elements:** Wide angle, corrected verticals, material accuracy, ambient lighting, atmosphere

**Recommended model:** `gpt5.4` or `flux2`

**Example:**
> Create a bright, airy interior photograph of a modern Scandinavian living room. Floor-to-ceiling windows flooding the space with soft diffused daylight. Light oak hardwood floors, a low-profile grey linen sofa, a round marble coffee table, and a single Monstera plant in a ceramic pot. White walls with subtle texture. Shot with Canon 5D, 24mm tilt-shift lens at f/11 for corrected verticals and deep focus. The composition leads from the plant in the foreground through the sofa to the window view. Minimal, serene atmosphere with muted neutral tones — cream, grey, natural oak, touches of sage green.

---

## infographic

**Data visualization, diagrams, charts** — Clear and structured.

**Formula:**
```
Create a [style] infographic about [topic].
[Grid/layout description]. [Data elements with content].
[Color coding system]. [Icon style]. [Aspect ratio — usually vertical].
```

**Key Elements:** Clear grid structure, data hierarchy, icon consistency, color coding, readability

**Recommended model:** `gemini` (best text rendering)

**Example:**
> Create a clean, modern infographic comparing 4 coffee brewing methods. Vertical 2:3 format with a bento-grid layout: title bar at top, then a 2x2 grid of equal cards below. Each card contains: a simple line-art icon of the brewing device (French press, pour-over, espresso machine, AeroPress), the method name in bold sans-serif, brew time, and a 1-5 strength rating shown as filled circles. Color coding: each method gets a distinct warm tone (amber, terracotta, coffee brown, burnt orange). White background, dark grey text. Clean, minimal design language with consistent 16px rounded corners on all cards.

---

## pod_design

**Print-on-demand designs** — Isolated graphics for t-shirts, mugs, posters, stickers.

**Formula:**
```
Create a [style] design of [subject] for [product type].
[Composition — center, badge, statement typography].
[Color palette — limited, print-friendly]. [Background: solid black/white OR use -t].
Sharp edges, no gradients at border, no ambient shadows.
[Print placement if apparel].
```

**Key Elements:** Solid background for easy removal (or `-t` for transparency), isolated design, print-friendly colors, clean edges

**Recommended model:** `riverflow` or `flux2`

**Example (t-shirt):**
> Create a dark gothic illustration of a highly detailed human skull with ornate filigree engravings carved into the bone surface. Blooming roses with thorned vines intertwine through the eye sockets and jaw, their petals showing individual vein details. Center-radiate composition — skull as the dominant focal point surrounded by organic flourishes. Hand-drawn etching style with meticulous crosshatching. Color palette strictly limited to bone white and blood red on a pure solid black background. Sharp edges between design and background with no gradients, no ambient shadows, no noise — optimized for print production. 4:5 vertical format.

**Example (mug wrap):**
> Create a seamless horizontal wrap-around design for an 11oz coffee mug. A continuous mountain range landscape in a minimalist line-art style — clean single-weight lines depicting peaks, valleys, and a winding river. Subtle dawn gradient from deep navy at the bottom to warm peach at the peaks. The design must tile seamlessly left-to-right for the wrap. White background with the design occupying the middle 60% vertically. 21:9 ultra-wide aspect ratio.
