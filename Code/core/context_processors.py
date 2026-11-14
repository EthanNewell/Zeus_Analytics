from django.conf import settings


def application(request):
    return {"app_version": settings.APP_VERSION}
