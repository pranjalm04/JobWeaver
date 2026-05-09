import unittest


class TestWorkerImports(unittest.TestCase):
    def test_worker_modules_import(self):
        import jobweaver.worker.celery_app  # noqa: F401
        import jobweaver.worker.tasks  # noqa: F401


if __name__ == "__main__":
    unittest.main()

