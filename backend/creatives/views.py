import mimetypes

from bson import ObjectId
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ads.models import Campaign, Platform
from audit import log as audit
from workspace.decorators import require_perm
from workspace.permissions import has_perm
from workspace.scoping import allowed_clients, ensure_client_allowed, get_scoped_or_404, scope

from .forms import CreativeForm
from .models import Creative
from .workflow import TransitionError, apply_transition, available_actions, checklist


def _read_image_size(creative):
    if creative.kind != Creative.Kind.IMAGE or not creative.file:
        return
    try:
        from PIL import Image

        creative.file.open("rb")
        with Image.open(creative.file) as image:
            creative.width, creative.height = image.size
    except Exception:  # Not a readable image; leave dimensions empty.
        creative.width = creative.height = None
    finally:
        try:
            creative.file.seek(0)
        except Exception:
            pass


def _store_file_meta(creative, upload):
    if upload is None:
        return
    creative.content_type = getattr(upload, "content_type", "") or mimetypes.guess_type(upload.name)[0] or ""
    creative.size_bytes = upload.size
    _read_image_size(creative)


@login_required
@require_perm("creatives.view")
def library(request):
    membership = request.membership
    creatives = scope(Creative.objects.select_related("client"), membership)
    status, kind, platform = request.GET.get("status", ""), request.GET.get("kind", ""), request.GET.get("platform", "")
    if status in Creative.Status.values:
        creatives = creatives.filter(status=status)
    if kind in Creative.Kind.values:
        creatives = creatives.filter(kind=kind)
    client_id = request.GET.get("client", "")
    if ObjectId.is_valid(client_id):
        creatives = creatives.filter(client_id=client_id)
    q = request.GET.get("q", "").strip()[:100]
    if q:
        creatives = creatives.filter(Q(name__icontains=q) | Q(headline__icontains=q) | Q(primary_text__icontains=q))
    items = list(creatives[:300])
    tag = request.GET.get("tag", "").strip().lower()
    if tag:
        items = [c for c in items if tag in c.tags]
    if platform in Platform.values:
        items = [c for c in items if platform in c.platforms]
    counts = {r["status"]: r["n"] for r in scope(Creative.objects.all(), membership).values("status").annotate(n=Count("pk"))}
    return render(request, "creatives/library.html", {
        "items": items, "status": status, "kind": kind, "platform": platform, "q": q, "tag": tag,
        "client_id": client_id, "clients": allowed_clients(membership), "kinds": Creative.Kind.choices,
        "platforms": Platform.choices,
        "statuses": [{"value": s.value, "label": s.label, "count": counts.get(s.value, 0)} for s in Creative.Status],
    })


def _form_kwargs(membership):
    return {"clients": allowed_clients(membership), "campaigns": scope(Campaign.objects.all(), membership)}


@login_required
@require_perm("creatives.edit")
def create(request):
    membership = request.membership
    form = CreativeForm(request.POST or None, request.FILES or None, **_form_kwargs(membership))
    if request.method == "POST" and form.is_valid():
        creative = form.save(commit=False)
        ensure_client_allowed(membership, creative.client)
        creative.organization = request.organization
        creative.created_by = request.user
        creative.platforms = form.cleaned_data["platforms"]
        creative.tags = form.cleaned_data["tags_text"]
        _store_file_meta(creative, request.FILES.get("file"))
        creative.save()
        audit.record(organization=request.organization, action="creative.create", entity=creative, request=request)
        messages.success(request, "Creative saved as a draft.")
        return redirect("creatives:detail", pk=creative.pk)
    return render(request, "creatives/form.html", {"form": form})


@login_required
@require_perm("creatives.view")
def detail(request, pk):
    membership = request.membership
    creative = get_scoped_or_404(Creative.objects.select_related("client", "campaign", "created_by"), membership, pk=pk)
    root = creative.root or creative
    versions = [root] + list(Creative.objects.filter(root=root).order_by("version"))
    return render(request, "creatives/detail.html", {
        "creative": creative,
        "actions": available_actions(creative, lambda perm: has_perm(membership, perm)),
        "checks": checklist(creative),
        "versions": versions if len(versions) > 1 else [],
        "reviews": creative.reviews.select_related("actor"),
        "can_edit": has_perm(membership, "creatives.edit"),
        "flow": [(s.value, s.label) for s in Creative.Status if s != Creative.Status.REJECTED],
    })


@login_required
@require_perm("creatives.edit")
def edit(request, pk):
    membership = request.membership
    creative = get_scoped_or_404(Creative.objects.all(), membership, pk=pk)
    form = CreativeForm(request.POST or None, request.FILES or None, instance=creative, **_form_kwargs(membership))
    if request.method == "POST" and form.is_valid():
        new_version = form.cleaned_data.get("save_as_new_version")
        if new_version:
            # Keep the current row untouched; save the edited copy as the next version.
            original = Creative.objects.get(pk=creative.pk)
            root = original.root or original
            latest = Creative.objects.filter(Q(pk=root.pk) | Q(root=root)).order_by("-version").first()
            updated = form.save(commit=False)
            updated.pk = None
            updated.root = root
            updated.version = latest.version + 1
            updated.status = Creative.Status.DRAFT
            updated.created_by = request.user
            if not request.FILES.get("file"):
                updated.file = original.file
        else:
            updated = form.save(commit=False)
        ensure_client_allowed(membership, updated.client)
        updated.platforms = form.cleaned_data["platforms"]
        updated.tags = form.cleaned_data["tags_text"]
        _store_file_meta(updated, request.FILES.get("file"))
        updated.save()
        audit.record(organization=request.organization, action="creative.new_version" if new_version else "creative.update",
                     entity=updated, request=request)
        messages.success(request, f"Saved as version {updated.version}." if new_version else "Creative updated.")
        return redirect("creatives:detail", pk=updated.pk)
    return render(request, "creatives/form.html", {"form": form, "creative": creative})


@login_required
@require_perm("creatives.view")
def file(request, pk):
    """Stream a creative's file after checking the viewer may see it."""
    creative = get_scoped_or_404(Creative.objects.all(), request.membership, pk=pk)
    if not creative.file:
        raise Http404
    try:
        handle = creative.file.open("rb")
    except FileNotFoundError:
        raise Http404 from None
    response = FileResponse(handle, content_type=creative.content_type or "application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; media-src 'self'"
    if request.GET.get("download"):
        response["Content-Disposition"] = f'attachment; filename="{creative.file.name.rsplit("/", 1)[-1]}"'
    return response


@login_required
@require_POST
@require_perm("creatives.view")
def transition(request, pk):
    membership = request.membership
    creative = get_scoped_or_404(Creative.objects.all(), membership, pk=pk)
    action, comment = request.POST.get("action", ""), request.POST.get("comment", "")
    try:
        before, after = apply_transition(creative, action, actor=request.user, comment=comment,
                                         can=lambda perm: has_perm(membership, perm))
    except PermissionError:
        raise PermissionDenied from None
    except TransitionError as exc:
        messages.error(request, str(exc))
        return redirect("creatives:detail", pk=creative.pk)
    audit.record(organization=request.organization, action=f"creative.{action}", entity=creative, request=request,
                 before={"status": before}, after={"status": after}, message=comment[:300])
    messages.success(request, f"{creative.name} is now {creative.get_status_display().lower()}.")
    return redirect("creatives:detail", pk=creative.pk)
