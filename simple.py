from sci import Job

job = Job(__name__)


@job.main()
def main():
    print("Hello World")


if __name__ == "__main__":
    job.start()
