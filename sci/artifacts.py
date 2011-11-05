"""
    sci.artifacts
    ~~~~~~~~~~~~~

    Artifacts

    Artifacts are the results of a build. They will be saved
    whereas all other intermediate files will be deleted
    upon the completion of a build.

    :copyright: (c) 2011 by Victor Boivie
    :license: Apache License 2.0
"""


class Artifacts(object):
    def __init__(self, job):
        self.job = job

    def add(self, filename):
        if self.job.debug:
            print("Storing '%s' on the storage node" % filename)

    def get(self, filename):
        if self.job.debug:
            print("Retrieving stored '%s' from the storage node" % filename)

    def create_zip(self, zip_filename, input_files):
        if self.job.debug:
            print("Zipping '%s' and storing as %s" % \
                      (input_files, zip_filename))
