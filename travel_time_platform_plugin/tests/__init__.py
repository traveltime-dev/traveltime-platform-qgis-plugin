import unittest


def run_suite(stream) -> unittest.TestResult:
    from . import tests_express_tools

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite = loader.loadTestsFromModule(tests_express_tools)
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    return runner.run(suite)
