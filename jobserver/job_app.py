import json

import web
import yaml

from jobserver.db import conn
from jobserver.gitdb import config, create_commit, update_head
from jobserver.gitdb import NoChangesException, CommitException
from jobserver.webutils import abort, jsonify
from jobserver.job import get_job, KEY_JOB
from jobserver.build import KEY_BUILD, KEY_JOB_BUILDS, KEY_SESSION

urls = (
    '',                        'ListJobs',
    '/(.+)',                   'GetPutJob',
)

job_app = web.application(urls, locals())


class GetPutJob:
    def POST(self, name):
        repo = config()
        input = json.loads(web.data())
        job = input['contents']
        job['name'] = name

        while True:
            old = input.get('old')
            if name == 'private':
                try:
                    old = repo.refs['refs/heads/jobs/private']
                except KeyError:
                    old = None
            contents = yaml.safe_dump(job, default_flow_style = False)
            try:
                commit = create_commit(repo, [('job.yaml', 0100644, contents)],
                                       parent = old,
                                       message = "Updated Job")
            except NoChangesException:
                return jsonify(ref = old)

            try:
                update_head(repo, 'refs/heads/jobs/%s' % name, old, commit.id)
                return jsonify(ref = commit.id)
            except CommitException as e:
                if name != 'private':
                    abort(412, str(e))

    def GET(self, query):
        db = conn()
        results = {}
        parts = query.split(',')
        name = parts[0]
        repo = config()
        results['settings'], results['ref'] = get_job(repo, name)
        success_bid = db.hget(KEY_JOB % name, 'success')
        if success_bid:
            success_no = db.hget(KEY_BUILD % success_bid, 'number')
            results['success_no'] = int(success_no)
        results['latest_no'] = db.llen(KEY_JOB_BUILDS % name)
        # Fetch information about the latest 10 builds
        history = []
        build_keys = ('number', 'created', 'description', 'session_id')
        session_keys = ('state', 'result')
        for build_id in db.lrange(KEY_JOB_BUILDS % name, -10, -1):
            number, created, description, session_id = \
                db.hmget(KEY_BUILD % build_id, build_keys)
            state, result = db.hmget(KEY_SESSION % session_id, session_keys)

            history.append(dict(number = number, created = created,
                                description = description,
                                state = state, result = result))
        history.reverse()
        return jsonify(history = history, **results)


class ListJobs:
    def GET(self):
        db = conn()
        repo = config()
        jobs = []
        for name in repo.refs.keys():
            if not name.startswith('refs/heads/jobs/'):
                continue
            job_name = name[16:]
            job, job_ref = get_job(repo, job_name, repo.refs[name])

            info = dict(id = job_name,
                        recipe_name = job['recipe_name'],
                        latest_no = db.llen(KEY_JOB_BUILDS % job_name))
            if 'recipe_ref' in job:
                info['recipe_ref'] = job['recipe_ref']
            jobs.append(info)
        return jsonify(jobs = jobs)
