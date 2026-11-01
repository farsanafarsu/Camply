"""Approval workflow and platform checklists for creatives."""

from ads.models import Platform

from .models import Creative, CreativeReview

S = Creative.Status
A = CreativeReview.Action

# action -> (allowed from statuses, resulting status, permission required, comment required)
TRANSITIONS = {
    A.SUBMITTED: ({S.DRAFT}, S.INTERNAL_REVIEW, "creatives.edit", False),
    A.APPROVED_INTERNAL: ({S.INTERNAL_REVIEW}, S.CLIENT_APPROVAL, "creatives.edit", False),
    A.APPROVED_CLIENT: ({S.CLIENT_APPROVAL}, S.READY, "creatives.approve", False),
    A.CHANGES: ({S.INTERNAL_REVIEW, S.CLIENT_APPROVAL}, S.DRAFT, "creatives.view", True),
    A.REJECTED: ({S.INTERNAL_REVIEW, S.CLIENT_APPROVAL}, S.REJECTED, "creatives.approve", True),
}


def available_actions(creative, can):
    """Actions this user may take now. `can(perm)` answers permission checks."""
    actions = []
    for action, (sources, _target, perm, needs_comment) in TRANSITIONS.items():
        if creative.status in sources and can(perm):
            # Asking for changes needs edit or approve rights, not just view.
            if action == A.CHANGES and not (can("creatives.edit") or can("creatives.approve")):
                continue
            actions.append({"value": action.value, "label": action.label, "needs_comment": needs_comment})
    return actions


class TransitionError(Exception):
    pass


def apply_transition(creative, action, *, actor, can, comment=""):
    if action not in TRANSITIONS:
        raise TransitionError("Unknown action.")
    sources, target, perm, needs_comment = TRANSITIONS[action]
    if creative.status not in sources:
        raise TransitionError(f"This creative is {creative.get_status_display().lower()}, so that isn't possible.")
    if action not in {a["value"] for a in available_actions(creative, can)}:
        raise PermissionError
    if needs_comment and not comment.strip():
        raise TransitionError("Please say what needs to change.")
    before = creative.status
    creative.status = target
    creative.save(update_fields=["status", "updated_at"])
    CreativeReview.objects.create(creative=creative, actor=actor, action=action, comment=comment.strip()[:4000])
    return before, target


# Practical limits from each platform's ad specs (characters, recommended sizes).
PLATFORM_SPECS = {
    Platform.META: {"headline": 40, "primary_text": 125, "description": 30,
                    "sizes": [(1080, 1080), (1080, 1350), (1080, 1920)], "video_seconds": (1, 240)},
    Platform.GOOGLE: {"headline": 30, "primary_text": 90, "description": 90,
                      "sizes": [(1200, 628), (1200, 1200), (960, 1200)], "video_seconds": (6, 180)},
    Platform.TIKTOK: {"headline": 40, "primary_text": 100, "description": None,
                      "sizes": [(1080, 1920)], "video_seconds": (5, 60)},
    Platform.OPENAI: {"headline": 50, "primary_text": 150, "description": None,
                      "sizes": [(1200, 628), (1080, 1080)], "video_seconds": None},
}


def checklist(creative):
    """[(ok: bool|None, message)] for each selected platform. None means 'can't tell'."""
    results = []
    platforms = creative.platforms or []
    if not platforms:
        return [(None, "Choose the platforms this creative is for to see their checks.")]
    for code in platforms:
        if code not in PLATFORM_SPECS:
            continue
        spec, label = PLATFORM_SPECS[code], Platform(code).label
        for field, name in (("headline", "Headline"), ("primary_text", "Primary text"), ("description", "Description")):
            limit, value = spec.get(field), getattr(creative, field) or ""
            if limit and value:
                ok = len(value) <= limit
                results.append((ok, f"{label}: {name} {len(value)}/{limit} characters"
                                    + ("" if ok else " (will be cut off)")))
        if creative.kind == Creative.Kind.IMAGE and creative.width and creative.height:
            ratio = creative.width / creative.height
            matches = [f"{w}×{h}" for w, h in spec["sizes"] if abs(ratio - w / h) < 0.02]
            results.append((bool(matches), f"{label}: image {creative.width}×{creative.height}"
                                            + (f" fits {matches[0]}" if matches else
                                               f", recommended {', '.join(f'{w}×{h}' for w, h in spec['sizes'])}")))
            if min(creative.width, creative.height) < 600:
                results.append((False, f"{label}: image is small; use at least 1080 px on the short side"))
        if creative.kind == Creative.Kind.VIDEO and spec["video_seconds"]:
            low, high = spec["video_seconds"]
            results.append((None, f"{label}: video should be {low}–{high} seconds, vertical 9:16 works best"))
        if creative.kind in (Creative.Kind.IMAGE, Creative.Kind.VIDEO, Creative.Kind.COPY) and not creative.landing_url:
            results.append((None, f"{label}: add the landing page URL (with UTM tags) before publishing"))
    return results or [(None, "No checks for the selected platforms.")]
