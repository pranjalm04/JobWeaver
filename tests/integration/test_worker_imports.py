import unittest


class TestWorkerImports(unittest.TestCase):
    def test_worker_modules_import(self):
        import physicianx.worker.celery_app  # noqa: F401
        import physicianx.worker.tasks  # noqa: F401


if __name__ == "__main__":
    unittest.main()

