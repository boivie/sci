from testbase import EmptyTestBase


class TC(EmptyTestBase):
    def testMock(self):
        self.job.artifacts.add("test.txt")
        self.job.artifacts.get("test.txt")
        self.job.artifacts.create_zip("file.zip", "*.txt")
