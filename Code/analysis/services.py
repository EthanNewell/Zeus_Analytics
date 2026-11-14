class AnalysisNotConfigured(Exception):
    pass


def run_analysis(*, actor, case_ids):
    raise AnalysisNotConfigured("Анализ пока недоступен. Результаты индикаторов не рассчитаны.")
