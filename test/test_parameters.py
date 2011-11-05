from testbase import EmptyTestBase
from sci.params import ParameterError


class TC(EmptyTestBase):
    def testSet(self):
        self.job.parameter("FOO")
        self.job.start(FOO = "bar")
        assert(self.job.format("{{FOO}}") == "bar")

    def testNotRequiredAndDefault(self):
        self.job.parameter("FOO", required = True, default = "Foo")
        try:
            self.job.params.evaluate()
            assert False
        except ParameterError:
            pass

    def testMustSpecifyRequired(self):
        self.job.parameter("FOO", required = True)
        try:
            self.job.params.evaluate()
            assert False
        except ParameterError:
            pass
