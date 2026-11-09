"""Versioned, machine-readable guidance for classifying observed CIE creative."""

from __future__ import annotations

import json
from typing import Any

from .taxonomy import ALL_FORMATS, ALL_HOOK_TYPES, ALL_MECHANICS, ALL_MESSAGE_FRAMES


CATALOG_VERSION = "1.2.0"
DIMENSIONS = ("format", "message_frame", "hook_type", "mechanic")


def _entry(
    definition: str,
    visual_positive_signals: tuple[str, ...],
    disambiguation_notes: str,
    *,
    canonical: bool = True,
) -> dict[str, Any]:
    return {
        "definition": definition,
        "visual_positive_signals": visual_positive_signals,
        "disambiguation_notes": disambiguation_notes,
        "canonical": canonical,
    }


# Entries are intentionally keyed by dimension, not globally by label. A label can
# describe a structural format and a message frame without the dimensions colliding.
TAXONOMY_CATALOG: dict[str, dict[str, dict[str, Any]]] = {
    "format": {
        "yapper": _entry(
            "A raw, direct-to-camera talking-head monologue that feels like an organic creator post.",
            ("one person speaking to the lens", "minimal editing", "casual phone-camera setting"),
            "Use for the visual delivery style, not every creator testimonial. Do not require captions or a product demo.",
        ),
        "faceless-demo": _entry(
            "A product demo or lifestyle video narrated from behind the camera without showing the creator's face.",
            ("hands-only action", "product in use", "camera operator remains unseen"),
            "Use pov-fps when the camera is visibly worn by the user; use asmr-audio-only when sound is the primary content.",
        ),
        "pov-fps": _entry(
            "First-person product use, mixing, unboxing, or demonstration filmed from a worn or handheld user viewpoint.",
            ("wearer-height camera", "hands entering frame", "continuous first-person motion"),
            "The camera perspective is the deciding signal; hands-only footage alone is faceless-demo.",
        ),
        "group-reaction": _entry(
            "Multiple people test, taste, discuss, or react to a product together in an organic-feeling scene.",
            ("two or more participants", "shared reaction", "group testing or conversation"),
            "Use interview-podcast-street-mic when the setup is a host-led Q&A rather than a group reaction.",
        ),
        "tiktok-shop-hustle": _entry(
            "A hyper-lo-fi creator pitch that holds the product close to the lens and points viewers to a checkout link.",
            ("ring light or bedroom-floor setup", "product thrust toward camera", "pointing down at link or cart"),
            "This is more sales-forward and visibly shoppable than a general yapper.",
        ),
        "interview-podcast-street-mic": _entry(
            "Conversational creative built as a public interview, mock podcast, street mic, or quick-fire Q&A.",
            ("microphone", "host and guest", "alternating question-and-answer shots"),
            "The interview setup matters more than the topic; a lone expert speaking is authority-figure.",
        ),
        "employee-warehouse": _entry(
            "Lo-fi brand-staff or employee content, including warehouse tours and raw operations footage.",
            ("staff badge or uniform", "warehouse or fulfillment setting", "behind-the-scenes operations"),
            "Use founder-bts when the founder is central; this label covers staff-made content and operational spaces.",
        ),
        "founder-bts": _entry(
            "Founder-led storytelling or behind-the-scenes operations that makes the brand builder the central character.",
            ("founder addressing camera", "brand operations", "personal founder story or customer call"),
            "A generic employee tour is employee-warehouse; an expert credential pitch is authority-figure.",
        ),
        "gossip-grwm": _entry(
            "A casual Story or TikTok-style personal monologue, often while getting ready, doing makeup, or talking in a car.",
            ("makeup or getting-ready activity", "car selfie framing", "high-drama personal story"),
            "The gossip or GRWM wrapper is required; a plain monologue is yapper.",
        ),
        "authority-figure": _entry(
            "An expert or credentialed professional educates the viewer while lending the product credibility.",
            ("lab coat or professional uniform", "credential cues", "expert demonstration or explanation"),
            "Use authority-education as the message frame when the teaching angle matters; this format describes who delivers it.",
        ),
        "narrative-vlog-ditl": _entry(
            "A day-in-the-life or journal-style vlog that shows the product fitting naturally into a routine over time.",
            ("morning-to-night sequence", "routine transitions", "day count or journal markers"),
            "A before/after claim may be the message frame; the format requires an unfolding routine or journal structure.",
        ),
        "de-influencing": _entry(
            "A creator dismisses popular or expensive alternatives before naming the product they actually recommend.",
            ("rejected product lineup", "anti-haul language", "alternative product reveal"),
            "Use us-vs-them or comparison for the angle when applicable; this format is the anti-recommendation narrative device.",
        ),
        "realistic-unboxing": _entry(
            "An intentionally imperfect unboxing that shows ordinary shipping materials, tape, inserts, and small friction.",
            ("cardboard shipping box", "struggling with tape", "invoice or package insert"),
            "Use anxious-unboxing-like cues only as a curiosity angle; this format is grounded in believable logistics.",
        ),
        "vsl": _entry(
            "A long-form or mini video sales letter that deeply explains the problem, mechanism, science, or offer.",
            ("extended explanatory sequence", "mechanism diagrams or proof", "dense sales education"),
            "Wall-of-text may appear inside a VSL, but VSL is defined by sustained explanatory sales structure.",
        ),
        "wall-of-text": _entry(
            "A video where scrolling, dense, or screen-dominating copy carries most of the communication.",
            ("large text blocks", "scrolling script", "copy occupies most of frame"),
            "Do not use for ordinary subtitles; the text itself must be the primary visual content.",
        ),
        "desire-metaphor-short": _entry(
            "A short cinematic video that visualizes an abstract desire or outcome through aesthetic metaphor.",
            ("symbolic stock imagery", "cinematic lifestyle cutaways", "abstract outcome visualization"),
            "Use when the visual sells a feeling or aspiration rather than directly demonstrating the product.",
        ),
        "split-screen-sludge": _entry(
            "A two-part video with the pitch above and hypnotic gameplay, sand, baking, or similar stimulation below.",
            ("horizontal split", "product pitch in one panel", "hypnotic filler footage in another panel"),
            "This is a complete format; tag split-screen separately as a mechanic when recording execution devices.",
        ),
        "micro-loop": _entry(
            "A very short, high-speed repeating visual designed to make viewers watch again to process a transformation.",
            ("3-to-5-frame repeat", "rapid transformation", "visibly seamless restart"),
            "This is the primary asset format; tag loop separately when a longer creative merely uses looping.",
        ),
        "ai-vo-broll": _entry(
            "Direct-response copy delivered by an AI-sounding voiceover over fast B-roll, product footage, or metaphors.",
            ("continuous voiceover", "rapid B-roll cuts", "no on-camera speaker"),
            "Do not infer AI from polished narration alone; use when the voiceover-plus-B-roll construction is clear.",
        ),
        "ai-song": _entry(
            "An ad whose product pitch is carried by an AI-generated or synthetic-sounding song with lyric-led cuts.",
            ("sung product claims", "beat-synced fast cuts", "lyric captions"),
            "The sung delivery is required; ordinary background music does not qualify.",
        ),
        "asmr-audio-only": _entry(
            "A no-talking, no-caption sensory video driven by close-miked product sounds.",
            ("close-up texture action", "pouring, clicking, tearing, or crunching", "no spoken narration"),
            "Sound is essential but may not be visible in a still; only use with audio evidence.",
        ),
        "voice-note-mimic": _entry(
            "A UGC narrative packaged visually as a playing WhatsApp or iMessage voice note over B-roll.",
            ("voice-message waveform", "messaging-app chrome", "B-roll behind audio UI"),
            "Use ui-mimic for broader interface imitation; this label specifically needs a voice-message presentation.",
        ),
        "retention-edit-technique": _entry(
            "A video whose defining idea is attention-retention editing, such as aggressive subtitle pattern interrupts or ad stacking.",
            ("erratic highlighted captions", "rapid hook changes", "stitched winning creative segments"),
            "Use only when editing is the main recognizable format; tag kinetic-captions or loop as mechanics when applicable.",
        ),
        "ai-avatar-presenter": _entry(
            "A synthetic, AI-generated human presenter delivers the pitch to camera: a lip-synced digital avatar "
            "(HeyGen / Synthesia / Argil style) rather than a real filmed person.",
            (
                "uncanny or too-even lip-sync",
                "static, looping, or plate-composited background",
                "avatar-stock wardrobe and centered framing",
                "subtle facial or edge warping that shifts across frames",
            ),
            "yapper is a real filmed person; ai-vo-broll has no on-camera speaker. This is the single hardest "
            "real-vs-synthetic call and REQUIRES watching frames: a single still can look like a genuine talking-head. "
            "When unsure between yapper and ai-avatar-presenter and frames do not settle it, use insufficient-evidence.",
        ),
        "ai-cinematic-broll": _entry(
            "Photoreal AI-generated cinematic or surreal footage (Veo / Sora / Kling style) carries the ad, often "
            "showing impossible product scenes, morphs, or dreamlike sequences meant to read as real video.",
            (
                "physically impossible motion or morphing",
                "photoreal but subtly warping objects, hands, or text",
                "cinematic AI-generated environments",
                "no real filmed presenter or genuine product footage",
            ),
            "desire-metaphor-short uses real stock/lifestyle footage; ai-animation is stylized/non-photoreal; "
            "ai-vo-broll is defined by the AI-voiceover-over-B-roll construction, not by AI-generated visuals.",
        ),
        "ai-motion-graphics": _entry(
            "An AI or automation-built motion-graphics explainer: animated UI, kinetic diagrams, flat 2D shapes, and "
            "on-screen text move to walk through how the product works.",
            (
                "animated interface or dashboard elements",
                "kinetic diagrams, arrows, and flat 2D shapes",
                "on-screen text as the primary motion",
                "no filmed footage and no character animation",
            ),
            "ui-mimic is a STATIC app-screen still; wall-of-text is dominated by copy, not motion; ai-animation is "
            "character/world animation. Use this when animated graphics/UI are the main moving content.",
        ),
        "ai-animation": _entry(
            "A stylized, non-photoreal animated ad: clay, anime, 3D-character, or cross-section illustration animates "
            "to explain or dramatize the product.",
            ("animated characters or worlds", "clay, anime, 3D, or cross-section style", "non-photoreal, non-UI animation"),
            "Photoreal AI video is ai-cinematic-broll; animated UI/diagrams/text is ai-motion-graphics; a synthetic "
            "human presenter is ai-avatar-presenter. Animation alone is not enough when a different structural format dominates.",
        ),
        "partnership-native-mimic": _entry(
            "Paid creative presented through a creator, expert, or thematic publisher identity to borrow native trust signals.",
            ("creator or publication handle", "partnership disclosure", "third-party account identity"),
            "Use creator-handle as the mechanic when noting the identity signal; this format captures the paid-native presentation.",
        ),
        "text-only-founders-letter": _entry(
            "A minimalist static consisting almost entirely of a founder letter or plain text on a simple background.",
            ("solid background", "long founder-style note", "little or no product photography"),
            "A text-heavy video is wall-of-text; this label is for static text-led creative.",
        ),
        "native-photo-long-copy": _entry(
            "A plain, unedited-looking photo paired with a long emotional or testimonial-style primary caption.",
            ("raw phone photo", "simple portrait or product snap", "long-form caption evidence"),
            "The long copy may be outside the image, so use accompanying post text when available.",
        ),
        "post-it-note": _entry(
            "A handwritten offer, code, or benefit presented on a physical Post-it note attached to a surface or product.",
            ("sticky note", "handwritten text", "note physically placed in scene"),
            "A digital sticky-note graphic is not enough unless it clearly imitates the physical note treatment.",
        ),
        "ui-mimic": _entry(
            "A static creative designed to resemble an app screen, text thread, dashboard, or native interface.",
            ("interface chrome", "app-like panels", "message thread or dashboard layout"),
            "Use the more specific tweet-reddit-ui or notification-ui when those interfaces are clear.",
        ),
        "tweet-reddit-ui": _entry(
            "A static deliberately styled as a tweet, Reddit post, comment thread, or similar social-post interface.",
            ("social-platform post layout", "upvotes or reply thread", "tweet-style profile row"),
            "This is a specific ui-mimic subtype; prefer it when the social platform convention is unmistakable.",
        ),
        "advertorial": _entry(
            "A static styled as a premium press headline, news article, or editorial screenshot.",
            ("publication masthead", "article headline", "editorial page layout"),
            "Use testimonial-screenshot for customer comments and tweet-reddit-ui for social posts.",
        ),
        "notification-ui": _entry(
            "A static that imitates a phone notification, lock screen, message alert, DM, or system prompt.",
            ("lock-screen notification", "iOS-like alert", "DM or message pop-up"),
            "Use ui-mimic for general app screens; this label requires an interruptive notification treatment.",
        ),
        "infographic-proof": _entry(
            "An educational, saveable graphic that explains a concept or makes proof legible through structured information.",
            ("labeled steps", "educational diagram", "data points or visual explanation"),
            "A simple comparison matrix can be quadrant-matrix; this label is broader educational proof design.",
        ),
        "grid-static": _entry(
            "A clean collage or grid that displays multiple products, SKUs, colorways, or variations at once.",
            ("repeated product tiles", "multiple colorways", "orderly collage grid"),
            "Do not use for a multi-card carousel; this is one static frame containing the grid.",
        ),
        "testimonial-screenshot": _entry(
            "A customer review, social comment, or star-rating receipt used as the central visual hook.",
            ("quoted customer review", "star rating", "comment screenshot"),
            "Use tweet-reddit-ui only when the social UI is the defining treatment rather than the testimonial itself.",
        ),
        "timeline-proof": _entry(
            "A visual before-and-after or time-based proof asset that makes change over a period immediately clear.",
            ("side-by-side transformation", "day labels", "progress timeline"),
            "Use before-after as the message frame when relevant; this format is the visual proof construction.",
        ),
        "first-frame-static": _entry(
            "A standalone static made from the opening frame of a winning video creative.",
            ("video-like freeze frame", "opening-hook composition", "no obvious static redesign"),
            "Requires source knowledge that it originated as a first video frame; do not infer from appearance alone.",
        ),
        "thermal-vision": _entry(
            "A disruptive faux thermal, X-ray, MRI, or scan-style image used to visualize a pain point or benefit.",
            ("heat-map colors", "X-ray or scan overlay", "anatomical or product cross-view"),
            "Use ai-animation for moving animated explainers; this label is the static scan-like treatment.",
        ),
        "diagram-puzzle": _entry(
            "A static visual puzzle or explanatory diagram that invites inspection to understand the claim.",
            ("annotated diagram", "puzzle-like comparison", "viewer challenge"),
            "Prefer the specific flat-lay-fit-test, spot-the-difference, quadrant-matrix, or chart-breakout when one fits.",
        ),
        "flat-lay-fit-test": _entry(
            "A top-down, tightly organized product layout proving that an item fits in a constrained space.",
            ("top-down flat lay", "suitcase, purse, or drawer", "precise packed arrangement"),
            "This is a size or utility proof, not a general product flat lay.",
        ),
        "spot-the-difference": _entry(
            "Two near-identical side-by-side visuals that challenge viewers to find the meaningful difference.",
            ("paired comparison images", "find the difference prompt", "subtle highlighted variation"),
            "A normal product comparison is comparison or us-vs-them; this requires a visual-search challenge.",
        ),
        "circle-arrow-explainer": _entry(
            "A raw product image with hand-drawn-looking circles and arrows that force attention to one feature.",
            ("bright red circle", "hand-drawn arrow", "rough MS-Paint-style annotation"),
            "Use when the intentionally crude annotation is central, not for polished callout diagrams.",
        ),
        "quadrant-matrix": _entry(
            "A Venn, two-by-two, or quadrant chart that positions the brand against a marketplace trade-off.",
            ("four-quadrant axes", "Venn overlap", "competitor positions"),
            "Use us-vs-them as the message frame when it argues sides; this format describes the matrix visual.",
        ),
        "chart-breakout": _entry(
            "A chart showing a metric flatlining and then sharply rising after the brand or product enters the story.",
            ("line graph", "sudden vertical spike", "started using brand annotation"),
            "This is a specific proof-chart pattern, not any graph or data point.",
        ),
        "carousel": _entry(
            "A swipeable multi-card static unit whose story, proof, or segmentation unfolds across cards.",
            ("multiple numbered cards", "swipe instruction", "consistent card sequence"),
            "Tag carousel-reveal or carousel-self-segmentation as mechanics when the card behavior is clear.",
        ),
        "insufficient-evidence": _entry(
            "A retained observation that lacks enough reliable visual or contextual evidence for a scoreable format.",
            ("missing creative asset", "unreadable preview", "conflicting or incomplete evidence"),
            "This is a closed-vocabulary fallback, not a creative style. Do not use it when one supported label fits.",
        ),
        "us-vs-them": _entry(
            "A structurally explicit two-side comparison that visually separates the brand or audience from an opposing option.",
            ("our product versus competitor columns", "us and them labels", "side-by-side trade-off table"),
            "Catalog-only format guidance: taxonomy.py currently permits this label only as a message frame. Classify the underlying canonical format separately and use us-vs-them as the frame.",
            canonical=False,
        ),
    },
    "message_frame": {
        "us-vs-them": _entry("Frames the market as a direct contrast between the audience or brand and an opposing alternative.", ("us versus them wording", "competitor contrast", "two-sided claim"), "Can coexist with the catalog-only us-vs-them format entry; the frame is the argument, not the layout."),
        "old-way-new-way": _entry("Contrasts an outdated approach with a better current alternative.", ("old way versus new way labels", "then-and-now comparison", "outdated workflow shown"), "Use us-vs-them for named sides or competitors; this frame emphasizes replacement over opposition."),
        "hidden-cost": _entry("Reveals an unseen leak, waste, missed revenue, or drag caused by the status quo.", ("cost callout", "waste visualization", "leak or loss annotation"), "Cost-transparency explains pricing mechanics; hidden-cost exposes a consequence of inaction."),
        "before-after": _entry("Claims or shows a meaningful change from an earlier state to a later result.", ("before and after labels", "transformation pairing", "time progression"), "Timeline-proof is the visual format when time-based proof is the construction."),
        "mistake-to-avoid": _entry("Warns the viewer against a common error that the product or advice can prevent.", ("warning headline", "wrong action highlighted", "avoid this language"), "Use myth-bust when correcting a belief rather than an action."),
        "myth-bust": _entry("Challenges a widely held belief and replaces it with a corrective claim.", ("myth versus fact", "false claim crossed out", "correction headline"), "Contrarian-take is a broader unpopular opinion; myth-bust specifically corrects a perceived fact."),
        "contrarian-take": _entry("Leads with an opinion that deliberately runs against conventional wisdom.", ("hot take headline", "unpopular opinion cue", "strong disagreement language"), "Use skeptical-expose when the device is an investigation or exposé."),
        "proof-stack": _entry("Builds belief by accumulating visible evidence such as numbers, receipts, cases, and results.", ("multiple proof points", "screenshots or receipts", "statistics and outcomes"), "Social-proof focuses on other people endorsing; proof-stack can include any evidence."),
        "comparison": _entry("Evaluates options against each other on features, price, ingredients, or utility.", ("comparison table", "side-by-side options", "feature checklist"), "Us-vs-them carries an adversarial side-taking claim; comparison can be neutral."),
        "social-proof": _entry("Uses customer adoption, reviews, popularity, or peer endorsement to make the choice feel validated.", ("reviews", "customer quotes", "sold-out or popularity cues"), "Testimonial-screenshot is a possible format; this frame is the persuasion angle."),
        "authority-education": _entry("Teaches through expert credibility, professional explanation, or technical authority.", ("expert teaching", "credentials", "educational demonstration"), "Authority-figure is the delivery format when an expert visibly appears."),
        "self-diagnosis": _entry("Lets viewers assess whether they have a problem, symptom, or qualifying condition.", ("checklist", "quiz-like questions", "symptom scoring"), "Avatar-callout names who the viewer is; self-diagnosis asks them to evaluate their state."),
        "failed-attempts": _entry("Acknowledges previous solutions that did not work before introducing a better path.", ("tried everything language", "failed product lineup", "frustration recap"), "De-influencing is a format that may use this frame, but it is not required."),
        "villain-callout": _entry("Identifies a person, industry, system, or practice as the source of the viewer's problem.", ("blamed institution", "enemy label", "callout headline"), "Ancestral-tradition often targets modern systems, but requires the traditional alternative."),
        "identity-belonging": _entry("Makes the product a signal of group membership, values, or desired identity.", ("tribal language", "identity label", "community cues"), "Avatar-callout identifies a segment; identity-belonging asks the viewer to align with an identity."),
        "risk-reversal": _entry("Reduces perceived downside through guarantees, trials, returns, or low-risk reassurance.", ("guarantee badge", "free trial", "easy returns"), "Offer-led presents a deal; risk-reversal specifically neutralizes hesitation."),
        "urgency-scarcity": _entry("Pushes action through limited time, stock, access, or fear of missing out.", ("countdown", "low stock", "limited drop"), "An apology or sell-out story can use this frame, but the frame is the scarcity pressure."),
        "feature-to-benefit": _entry("Translates a product feature into a concrete customer outcome or payoff.", ("feature arrow to result", "because it has X, you get Y", "benefit callout"), "How-it-works explains operation; feature-to-benefit explains why that operation matters."),
        "how-it-works": _entry("Explains the mechanism, process, or steps behind how the product delivers its result.", ("step sequence", "mechanism diagram", "process explanation"), "VSL and ai-animation are possible formats for this frame."),
        "offer-led": _entry("Makes the price, bundle, discount, or purchase offer the main reason to act.", ("discount badge", "bundle pricing", "buy-now offer"), "Cost-transparency explains why the price is fair; offer-led foregrounds the deal itself."),
        "skeptical-expose": _entry("Starts from skepticism or a fake investigation before turning toward the product case.", ("scam or expose headline", "investigative styling", "skeptical opening"), "Contrarian-take can be skeptical but does not require an exposé structure."),
        "reverse-psychology": _entry("Tells the wrong audience not to buy, making the desired audience want the product more.", ("don't buy this if", "not for everyone", "disqualifying statement"), "Use avatar-callout when it simply names a target audience without the reversal."),
        "life-hack": _entry("Presents the product as an insider shortcut, overlooked trick, or newly discovered practical knowledge.", ("life hack label", "today years old language", "shortcut demonstration"), "Forbidden-secret is more provocative or restricted; life-hack is practical and accessible."),
        "forbidden-secret": _entry("Suggests the product reveals information that is hidden, disallowed, or too good to share.", ("is this legal headline", "they do not want you to know", "secret reveal"), "Ancestral-tradition invokes historical methods; forbidden-secret foregrounds prohibition or concealment."),
        "ancestral-tradition": _entry("Pits modern or synthetic solutions against traditional, raw, or ancestral methods.", ("ancient remedy cues", "traditional ingredients", "modern versus ancestral contrast"), "Use villain-callout when blame is the main message without a traditional alternative."),
        "skeptic-to-believer": _entry("Shows a doubtful person becoming convinced after trying or seeing the result.", ("initial disbelief", "reaction shift", "conversion testimony"), "Failed-attempts focuses on prior solutions; skeptic-to-believer focuses on the person's belief change."),
        "reasons-why": _entry("Lists distinct numbered reasons to buy, switch, or believe the claim.", ("numbered list", "reason one, two, three", "stacked purchase reasons"), "Proof-stack accumulates evidence; reasons-why organizes persuasive reasons whether or not they are proof."),
        "avatar-callout": _entry("Addresses a narrow audience persona directly so that person recognizes themselves immediately.", ("for nurses or golfers headline", "occupation or identity callout", "specific use-case label"), "Identity-belonging builds aspiration or affiliation; this frame selects the audience."),
        "cost-transparency": _entry("Explains retail markup, middlemen, or direct costs to justify a lower or fairer price.", ("price breakdown", "middleman crossed out", "retail versus direct cost"), "Hidden-cost reveals waste; cost-transparency explains how the seller can charge differently."),
        "challenge": _entry("Invites or stages a game, test, dare, or competition that proves the value proposition.", ("challenge prompt", "blind test", "score or contest"), "Spot-the-difference is a specific visual format that may use this frame."),
        "insufficient-evidence": _entry("A retained observation without enough reliable evidence to determine its message frame.", ("missing copy", "unreadable creative", "ambiguous context"), "This fallback is not a persuasion angle and should be replaced when stronger evidence arrives."),
    },
    "hook_type": {
        "direct-callout": _entry("Opens by directly naming the viewer or audience as a statement, not a question.", ("speaker addresses a named audience", "opening text begins with 'you' or 'for'", "pointing-to-viewer framing"), "Use pain-callout when the opening centers a present complaint; if the address is phrased as a QUESTION ('Gym owner losing members?'), it is diagnostic-question."),
        "pain-callout": _entry("Opens with the viewer's current frustration, symptom, or complaint.", ("exasperated reaction", "problem visibly shown", "present-tense complaint on screen"), "Unlike warning-shot, this names pain happening now; unlike diagnostic-question, it is not a grammatical question."),
        "warning-shot": _entry("Opens with an imperative loss-avoidance warning: stop/avoid this or it will cost you.", ("'stop doing this' or 'this is costing you' headline", "warning gesture", "act-now loss framing"), "The tell is imperative/act-now framing (stop, avoid, don't). A passive future forecast with no call to act is prediction-fortune-teller. Use pain-callout for current frustration."),
        "us-vs-them": _entry("Opens by sharply contrasting the brand or viewer with an opposing option.", ("two opposing labels", "versus layout", "competitor or enemy named immediately"), "Use contrarian-snapback for rejecting a belief; this hook needs visible opposing sides."),
        "curiosity-gap": _entry("Opens with an unresolved mystery, reveal, or withheld explanation.", ("teased reveal text", "obscured object or result", "speaker pauses before answer"), "Use hidden-feature-fakeout when the opening deliberately misleads about what is being shown."),
        "contrarian-snapback": _entry("Opens by forcefully rejecting common advice or expectation.", ("'stop doing this' opening", "dismissive gesture", "conventional claim crossed out"), "Unlike us-vs-them, the conflict is with a belief or norm, not necessarily an opposing party."),
        "pov-mind-read": _entry("Opens as if narrating the viewer's private thought or exact situation.", ("POV caption", "inner-thought text", "recognition reaction"), "Use direct-callout when the speaker simply addresses an audience without voicing their internal experience."),
        "shocking-stat": _entry("Opens with a surprising numerical fact or quantified claim.", ("large number in first frame", "percentage headline", "chart or statistic overlay"), "A normal proof point later in the creative is not enough; the number must carry the opening."),
        "before-after-tease": _entry("Opens by teasing a transformation between an old and new state.", ("before-and-after pairing", "transformation glimpse", "then-versus-now opening text"), "Use testimonial-social-proof when another person's endorsement is the opening proof instead."),
        "listicle-promise": _entry("Opens by promising a numbered list of takeaways, reasons, or steps.", ("numbered headline", "'three reasons' text", "visible list count"), "Use diagnostic-question when the opening asks the viewer to assess themselves rather than promising items."),
        "authority-credential": _entry("Opens by foregrounding the speaker's expert role, credential, or insider access.", ("professional title on screen", "uniform or credential cue", "expert introduction"), "Use testimonial-social-proof for customer proof; this hook depends on authority at the opening."),
        "diagnostic-question": _entry("Opens with a question that helps the viewer identify a problem or condition.", ("question mark headline", "speaker asks a symptom question", "check-yourself prompt"), "Any grammatical QUESTION wins here over direct-callout even if it names the audience; unlike pain-callout it must be a question; unlike curiosity-gap it seeks self-diagnosis rather than a reveal."),
        "in-media-res-panic": _entry("Opens mid-crisis, with urgent action or a visibly escalating problem already underway.", ("rushed motion", "alarm or frantic reaction", "urgent interruption text"), "Use warning-shot for a stated future threat; this hook begins inside the immediate event."),
        "hidden-feature-fakeout": _entry("Opens on a FAMILIAR app, product, or object and frames it as secretly having a capability nobody knows about ('since when does X do THIS?').", ("familiar UI or product in first frame", "'wait, since when...' surprise line", "screen-recording of a known app with a shocked reaction"), "The opening cue is the familiar-thing-with-a-secret framing, observable up front. Use curiosity-gap for a generic withheld answer where no familiar object is being re-framed."),
        "i-tried-x": _entry("Opens with the creator's firsthand attempt, experiment, or trial.", ("'I tried' opening text", "creator starts a test", "product attempt in first frame"), "Use confession-receipts when the opening reveals a personal admission or supporting receipt rather than an experiment."),
        "trend-hijack": _entry("Opens by borrowing a recognizable current meme, sound, visual convention, or cultural moment.", ("recognizable trend setup", "meme-style opening text", "trend audio or challenge cue"), "Use pattern-interrupt for a disruptive visual without a recognizable cultural reference."),
        "pattern-interrupt": _entry("Opens with a content-free visual or audio jolt that carries NO spoken hook, claim, question, or callout — the shock itself is the whole device.", ("jarring first frame with no text claim", "sudden visual/audio disruption before any words", "strange composition standing alone"), "Only when the opening is a pure jolt with no verbal hook. If ANY spoken/on-screen hook leads (question, claim, callout, POV), classify THAT type instead. Use trend-hijack when the jolt is a recognizable meme/sound."),
        "confession-receipts": _entry("Opens with a candid admission backed by a visible receipt, message, or proof artifact.", ("confessional first line", "receipt or screenshot shown", "embarrassed or candid reaction"), "Use testimonial-social-proof when the proof belongs to a customer endorsement rather than the speaker's admission."),
        "prediction-fortune-teller": _entry("Opens with a passive forecast of what will happen to the viewer or market, with no call to act.", ("future-tense claim ('by 2027...')", "prediction headline", "fortune-teller styling"), "A neutral forecast with no imperative. If the opening tells the viewer to act now or avoid a loss, it is warning-shot."),
        "testimonial-social-proof": _entry("Opens with a customer's result, review, or visible evidence of other people endorsing the product.", ("review quote in first frame", "customer testimonial opening", "star rating or result receipt"), "Use authority-credential when credibility comes from expertise rather than customer adoption or endorsement."),
    },
    "mechanic": {
        "green-screen": _entry("A creator talks in front of replaced background footage, a website, chart, or other visual source.", ("speaker cutout", "background website or B-roll", "platform green-screen look"), "This can appear inside many formats and is not itself the primary format."),
        "split-screen": _entry("The frame is visibly divided into two simultaneous visual panels.", ("vertical or horizontal split", "two concurrent scenes", "divided frame border"), "Tag alongside split-screen-sludge only when the division is present; the sludge format needs a pitch-plus-hypnotic layout."),
        "kinetic-captions": _entry("Captions move, resize, change color, or jump position to repeatedly pull the eye.", ("animated word highlights", "variable caption size", "erratic text placement"), "Ordinary subtitles do not qualify; visible motion or deliberate pattern interruption is required."),
        "loop": _entry("The creative or a segment is designed to repeat seamlessly.", ("ending matches opening", "repeated action", "cyclical motion"), "Use micro-loop as the format when the entire asset is the tiny high-speed loop."),
        "story-poll-mimic": _entry("A fake Instagram Story poll or quiz sticker invites an instinctive tap.", ("poll choices", "Story sticker treatment", "quiz interface"), "This is an execution device and can appear in static or video creative."),
        "carousel-reveal": _entry("Carousel cards withhold an answer or image and deliver the payoff on a later swipe.", ("blurred first card", "swipe to reveal prompt", "answer on later card"), "Requires a carousel; do not apply to a single static with a reveal effect."),
        "carousel-self-segmentation": _entry("Carousel cards let viewers identify their persona, use case, or path by swiping through options.", ("for side sleepers card", "persona-labeled cards", "choose your path sequence"), "Requires a carousel and differs from a generic avatar-callout by using multiple self-selecting cards."),
        "creator-handle": _entry("A creator, expert, or publisher account identity is visibly used as a trust signal for the ad.", ("visible handle", "creator profile identity", "partnership attribution"), "Partnership-native-mimic is the broader paid presentation format; this mechanic records the identity cue."),
        "stitch-bait": _entry("The creative opens with a polarizing external clip and then cuts to a creator responding as if stitching it.", ("viral clip opening", "abrupt response cut", "stitch framing"), "A generic reaction is not enough; the borrowed clip and response setup must be visible."),
    },
}


def _ordered_labels(dimension: str) -> tuple[str, ...]:
    if dimension == "format":
        # The catalog intentionally carries one non-canonical visual alias.
        return tuple(sorted(ALL_FORMATS)) + ("us-vs-them",)
    if dimension == "message_frame":
        return tuple(sorted(ALL_MESSAGE_FRAMES))
    if dimension == "hook_type":
        return tuple(sorted(ALL_HOOK_TYPES - {"hook-unknown"}))
    if dimension == "mechanic":
        return tuple(sorted(ALL_MECHANICS))
    raise ValueError(f"unknown taxonomy dimension: {dimension!r}")


def get_catalog_entry(dimension: str, label: str) -> dict[str, Any]:
    """Return a JSON-safe copy of the catalog guidance for one dimensional label."""
    try:
        entry = TAXONOMY_CATALOG[dimension][label]
    except KeyError as exc:
        raise KeyError(f"unknown catalog label {dimension}:{label}") from exc
    return {"label": label, **entry}


def catalog_payload() -> dict[str, Any]:
    """Return a deterministic, JSON-safe catalog payload for tools and classifiers."""
    return {
        "catalog_version": CATALOG_VERSION,
        "dimensions": [
            {
                "name": dimension,
                "labels": [get_catalog_entry(dimension, label) for label in _ordered_labels(dimension)],
            }
            for dimension in DIMENSIONS
        ],
    }


def vision_classifier_prompt_payload() -> str:
    """Serialize stable catalog guidance for insertion into a vision-classifier prompt."""
    payload = {
        "task": "Classify observed creative only. Do not invent hooks, concepts, copy, or unseen evidence.",
        "selection_rules": [
            "Choose one canonical format, one message frame when supported, one primary hook type when opening evidence supports it, and zero or more mechanics.",
            "Use visual_positive_signals as supporting evidence, not as a reason to infer hidden audio or context.",
            "Labels may overlap across dimensions: classify each dimension independently.",
            "The catalog-only format us-vs-them is visual guidance only; runtime format output must use a canonical format and may use us-vs-them as its message frame.",
        ],
        "catalog": catalog_payload(),
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
