from .models import Case


def case_list(query=""):
    cases = Case.objects.all()
    if query:
        from django.db.models import Q

        cases = cases.filter(
            Q(reference__icontains=query)
            | Q(title__icontains=query)
            | Q(cadastral_number__icontains=query)
        )
    return cases
