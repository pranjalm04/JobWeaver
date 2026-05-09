from celery import Celery

from jobweaver.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "jobweaver",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"

celery_app.conf.task_default_queue = "crawl"
celery_app.conf.task_routes = {
    "jobweaver.crawl_seed": {"queue": "crawl"},
    "jobweaver.run_pipeline": {"queue": "crawl"},
    "jobweaver.analyze_listing": {"queue": "llm"},
    "jobweaver.scrape_job_links": {"queue": "playwright"},
    "jobweaver.extract_job_details": {"queue": "crawl"},
}

celery_app.conf.task_annotations = {
    "*": {
        "time_limit": 3600,
        "soft_time_limit": 3300,
    }
}

celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1
