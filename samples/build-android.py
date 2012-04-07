#!/usr/bin/env python
#
# Description:
#    Builds android (several products and variants) and saves the
#    resulting images as zip-files.
#
# Tags: [android, zipped]
#
# Parameters:
#  BRANCH:
#    description: Manifest branch
#    required: True
#
#  BUILD_ID_PREFIX:
#    description: The build ID prefix to use
#
#  PRODUCTS:
#    description: The products to build (will be guessed if not specified)
#    type: array
#
#  MANIFEST_FILE:
#    description: Manifest filename
#    default: default.xml
#
#  VARIANTS:
#    description: Variants to build
#    type: checkbox
#    options: [eng, userdebug, user]
#    default: [eng, userdebug, user]
#
import time
from sci import Job

job = Job(__name__, debug = True)


@job.default("PRODUCTS")
def get_products():
    """A function that will be evaluated to get the default
       value for 'products' in case it's not specified"""

    if "donut" in job.env['BRANCH']:
        return ["g1", "emulator"]
    if "eclair" in job.env['BRANCH']:
        return ["droid", "nexus_one", "emulator"]
    if "gingerbread" in job.env['BRANCH']:
        return ["nexus_one", "nexus_s", "emulator"]
    job.error("Don't know which products to build!")


@job.default("BUILD_ID_PREFIX")
def default_build_id_prefix():
    return job.env['BRANCH'].upper().replace("-", "_")


@job.step("Create Build ID")
def create_build_id():
    build_id = job.env['BUILD_ID_PREFIX'] + "_" + time.strftime("%Y%m%d_%H%M%S")
    return build_id


@job.step("Create Static Manifest")
def create_manifest():
    """These commands will automatically run in a temporary directory
       that will be wiped once the entire job finishes"""
    job.run("repo init -u {{MANIFEST_URL}} -b {{BRANCH}} -m {{MANIFEST_FILE}}")
    job.run("repo sync --jobs={{SYNC_JOBS}}", name = "sync")
    job.run("repo manifest -r -o static_manifest.xml")

    # Upload the result of this step to the 'file storage node'
    job.artifacts.add("static_manifest.xml")


@job.step("Get source code")
def get_source():
    job.run("repo init -u {{MANIFEST_URL}} -b {{BRANCH}}")
    job.run("cp static_manifest.xml .repo/manifest.xml")
    job.run("repo sync --jobs={{SYNC_JOBS}}")


@job.step("Build Android")
def build_android():
    job.run("""
. build/envsetup.sh
lunch {{PRODUCT}}-{{VARIANT}}
make -j{{JOB_CPUS}}""")


@job.step("ZIP resulted files")
def zip_result():
    zip_file = "result-{{BUILD_ID}}-{{PRODUCT}}-{{VARIANT}}.zip"
    input_files = "out/target/product/{{PRODUCT}}/*.img"

    job.artifacts.create_zip(zip_file, input_files)
    return job.format(zip_file)


@job.step("Run single matrix job")
def run_single_matrix_job(product, variant):
    """This job will be running on a separate machine, in parallel with
       a lot of other similar jobs. It will perform a few build steps."""
    job.env["PRODUCT"] = product
    job.env["VARIANT"] = variant
    job.artifacts.get("static_manifest.xml")

    get_source()
    build_android()
    return zip_result()


@job.step("Run matrix jobs")
def run_matrix_jobs():
    """Running jobs asynchronously"""
    for product in job.env["PRODUCTS"]:
        for variant in job.env["VARIANTS"]:
            job.agents.async(run_single_matrix_job, args = [product, variant])

    for result in job.agents.run():
        print("Result: " + result)


@job.step("Send Report")
def send_report():
    pass


@job.main()
def main():
    """This is the job's entry point."""
    job.env["BUILD_ID"] = create_build_id()
    job.description = "{{BUILD_ID}}"
    create_manifest()
    run_matrix_jobs()
    send_report()


if __name__ == "__main__":
    job.start()
