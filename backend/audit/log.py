from .models import AuditEvent


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record(*, organization, action, entity=None, entity_type="", actor=None, request=None, client=None,
           platform="", before=None, after=None, outcome=AuditEvent.Outcome.SUCCESS, message=""):
    """Write an audit event. `entity` may be any model instance; its type, id and label are captured."""
    if entity is not None:
        entity_type = entity_type or entity._meta.model_name
        client = client if client is not None else getattr(entity, "client", None)
        platform = platform or getattr(entity, "platform", "")
    if actor is None and request is not None and request.user.is_authenticated:
        actor = request.user
    return AuditEvent.objects.create(
        organization=organization,
        client=client,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity.pk) if entity is not None else "",
        entity_label=str(entity)[:200] if entity is not None else "",
        platform=platform,
        before=before or {},
        after=after or {},
        outcome=outcome,
        message=message[:300],
        ip_address=client_ip(request),
    )
