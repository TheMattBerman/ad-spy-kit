---
name: ad-teardown
description: Analyze competitor ads using Matt's psychology framework. Use when you have an ad screenshot, URL, or description to break down hooks, triggers, and stealable patterns.
---

# Ad Teardown

Analyze competitor ads using the Puppet Strings psychology framework.

## Invocation
/ad-teardown [ad-description, URL, or image]

## Psychology Framework

Reference `/social-media-strategist` for full framework. Key elements:

**Puppet Strings (Target Drives)**
- Wealth
- Health
- Status/Access
- Escape
- Romance
- Fear (amplifier, not a drive — dials up urgency on any of the 5)

**Psychological Triggers**
- Curiosity gap
- Social proof
- Scarcity/urgency
- Authority
- Contrast/transformation
- Identity/belonging

Don't duplicate the framework here — pull from the skill when analyzing.

## Analysis Process

### 1. Capture
- Screenshot or describe the ad
- Note: platform, brand, approximate date seen
- First impression: why did this stop your scroll?

### 2. Hook Analysis (First 3 Seconds)
- Opening line / visual hook
- Pattern used (question, contrast, story, shock, curiosity)
- Which Puppet String it pulls
- Why it works (or doesn't)

### 3. Drive Mapping
- Primary Puppet String pulled
- Secondary drive (if any)
- Fear amplifier used? (yes/no, how)
- Pain vs aspiration framing
- Specificity level (vague promise vs concrete outcome)

### 4. Trigger Breakdown
- List each psychological trigger used
- How it's deployed
- Strength rating (subtle / moderate / heavy)

### 5. Structure Analysis
- Format: static / carousel / video
- Copy structure: [hook] → [body] → [CTA]
- Length and pacing
- Visual hierarchy

### 6. CTA Evaluation
- CTA text
- Placement
- Friction level
- Commitment ask (low/medium/high)

### 7. Visual Elements
- Color psychology
- Face presence (yes/no, expression)
- Text overlay style
- Brand presence level

## Output Format

Save to: `09-swipe-files/ads/[brand]-[YYYY-MM-DD]-[platform].md`

```markdown
---
source: [URL or "screenshot"]
platform: [meta | linkedin | google | twitter | youtube]
brand: [Company name]
industry: [saas | ecommerce | fintech | etc]
captured: YYYY-MM-DD
puppet_string: [wealth | health | status-access | escape | romance]
triggers: [list primary triggers]
format: [static | carousel | video]
tags: [swipefile, ad, platform, industry, puppet-string]
---

# [Brand] - [Hook Summary]

## The Ad
[Screenshot embed or description]

## First Impression
[Why this stopped the scroll — gut reaction]

## Hook Analysis
**Opening:** [Exact text or visual description]
**Pattern:** [question | contrast | story | shock | curiosity | list]
**Puppet String:** [Primary drive targeted]
**Why it works:**

## Psychological Triggers

| Trigger | How It's Used | Strength |
|---------|---------------|----------|
| [Trigger] | [Deployment] | [subtle/moderate/heavy] |

## Structure Breakdown
```
[Hook]
↓
[Body - key points]
↓
[CTA]
```

## Copy Analysis
- Voice:
- Specificity:
- Proof elements:
- Objection handling:

## Visual Analysis
- Format:
- Key visual elements:
- Color/mood:
- Face/human presence:

## CTA
- Text: "[CTA copy]"
- Placement:
- Friction level: [low | medium | high]

---

## Steal This

### Hook Template
> [Abstracted, reusable version]

### For [Industry 1] Client
[Specific adaptation]

### For [Industry 2] Client
[Specific adaptation]

### Universal Pattern
[What works across niches]

---

## Skip

- [Brand-specific element that won't transfer]
- [Requires their authority/proof]
- [Platform-specific that won't work elsewhere]

---

## Rating

**Effectiveness:** [1-10]
**Steal Priority:** [high | medium | low]
**Best For:** [awareness | consideration | conversion | retargeting]
```

## Batch Mode

For multiple ads, invoke with list:
```
/ad-teardown
1. [Ad 1 description/URL]
2. [Ad 2 description/URL]
3. [Ad 3 description/URL]
```

Process each, save to separate files, then output summary:
```
## Batch Summary

| Brand | Platform | Puppet String | Steal Priority |
|-------|----------|--------------|----------------|
| [Brand 1] | [Platform] | [Drive] | [Priority] |
| [Brand 2] | [Platform] | [Drive] | [Priority] |

Top patterns found:
- [Pattern 1]
- [Pattern 2]
```

## Integration

- Psychology framework: `/social-media-strategist`
- Client inspiration: `/client-context [client]` then browse `09-swipe-files/ads/`
- Newsletter content: Filter by `#viral` or high steal-priority
- StealAds training: All teardowns feed product patterns
