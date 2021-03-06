# -*- coding: utf-8 -*-
#
# Copyright (c) 2014-2015 Université Catholique de Louvain.
#
# This file is part of INGInious.
#
# INGInious is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# INGInious is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with INGInious.  If not, see <http://www.gnu.org/licenses/>.

from frontend.base import renderer
from frontend.pages.course_admin.utils import get_course_and_check_rights
from frontend.batch_manager import get_all_batch_containers_metadata, add_batch_job, get_all_batch_jobs_for_course, get_batch_job_status, \
    get_batch_container_metadata, drop_batch_job
import web
from frontend.base import get_gridfs
import tarfile
import mimetypes
import urllib
import tempfile

class CourseBatchOperations(object):
    """ Batch operation management """

    def GET(self, courseid):
        """ GET request """

        course, _ = get_course_and_check_rights(courseid)

        web_input = web.input()
        if "drop" in web_input: # delete an old batch job
            try:
                drop_batch_job(web_input["drop"])
            except:
                pass

        operations = []
        for entry in list(get_all_batch_jobs_for_course(courseid)):
            ne = {"container_name": entry["container_name"],
                  "bid": str(entry["_id"]),
                  "submitted_on": entry["submitted_on"]}
            if "result" in entry:
                ne["status"] = "ok" if entry["result"]["retval"] == 0 else "ko"
            else:
                ne["status"] = "waiting"
            operations.append(ne)
        operations = sorted(operations, key= (lambda o: o["submitted_on"]), reverse=True)

        return renderer.course_admin.batch(course, operations, get_all_batch_containers_metadata())

class CourseBatchJobCreate(object):
    """ Creates new batch jobs """
    def GET(self, courseid, container_name):
        """ GET request """
        course, container_title, container_description, container_args = self.get_basic_info(courseid, container_name)
        return self.page(course, container_name, container_title, container_description, container_args)

    def POST(self, courseid, container_name):
        """ POST request """
        course, container_title, container_description, container_args = self.get_basic_info(courseid, container_name)
        errors = []

        # Verify that we have the right keys
        try:
            file_args = {key: {} for key in container_args if key != "submissions" and key != "course" and container_args[key]["type"] == "file"}
            batch_input = web.input(**file_args)
            for key in container_args:
                if (key != "submissions" and key != "course") or container_args[key]["type"] != "file":
                    if key not in batch_input:
                        raise Exception("It lacks a field")
                    if container_args[key]["type"] == "file":
                        batch_input[key] = batch_input[key].file
        except:
            raise
            errors.append("Please fill all the fields.")

        if len(errors) == 0:
            try:
                add_batch_job(course, container_name, batch_input)
            except:
                errors.append("An error occured while starting the job")

        if len(errors) == 0:
            raise web.seeother('/admin/{}/batch'.format(courseid))
        else:
            return self.page(course, container_name, container_title, container_description, container_args, errors)

    def get_basic_info(self, courseid, container_name):
        course, _ = get_course_and_check_rights(courseid, allow_all_staff=False)
        try:
            metadata = get_batch_container_metadata(container_name)
            if metadata == (None, None, None):
                raise Exception("Container not found")
        except:
            raise web.notfound()

        container_title = metadata[0]
        container_description = metadata[1]

        container_args = dict(metadata[2])  # copy it

        return course, container_title, container_description, container_args

    def page(self, course, container_name, container_title, container_description, container_args, error=None):

        if "submissions" in container_args and container_args["submissions"]["type"] == "file":
            del container_args["submissions"]
        if "course" in container_args and container_args["course"]["type"] == "file":
            del container_args["course"]

        return renderer.course_admin.batch_create(course, container_name, container_title, container_description, container_args, error)

class CourseBatchJobDownload(object):
    """ Get the file of a batch job """

    def GET(self, courseid, bid, path=""):
        """ GET request """

        course, _ = get_course_and_check_rights(courseid)
        batch_job = get_batch_job_status(bid)

        if batch_job is None:
            raise web.notfound()

        if "result" not in batch_job or "file" not in batch_job["result"]:
            raise web.notfound()

        f = get_gridfs().get(batch_job["result"]["file"])

        #hack for index.html:
        if path == "/":
            path = "/index.html"

        if path == "":
            web.header('Content-Type', 'application/x-gzip', unique=True)
            web.header('Content-Disposition', 'attachment; filename="' + bid + '.tar.gz"', unique=True)
            return f.read()
        else:
            path = path[1:] #remove the first /
            if path.endswith('/'):  # remove the last / if it exists
                path = path[0:-1]

            try:
                tar = tarfile.open(fileobj=f, mode='r:gz')
                file_info = tar.getmember(path)
            except:
                raise web.notfound()

            if file_info.isdir(): #tar.gz the dir and return it
               tmp = tempfile.TemporaryFile()
               new_tar = tarfile.open(fileobj=tmp,mode='w:gz')
               for m in tar.getmembers():
                   new_tar.addfile(m, tar.extractfile(m))
               new_tar.close()
               tmp.seek(0)
               return tmp
            elif not file_info.isfile():
                raise web.notfound()
            else: #guess a mime type and send it to the browser
                to_dl = tar.extractfile(path).read()
                mimetypes.init()
                mime_type = mimetypes.guess_type(urllib.pathname2url(path))
                web.header('Content-Type', mime_type[0])
                return to_dl

class CourseBatchJobSummary(object):
    """ Get the summary of a batch job """

    def GET(self, courseid, bid):
        """ GET request """

        course, _ = get_course_and_check_rights(courseid)
        batch_job = get_batch_job_status(bid)

        if batch_job is None:
            raise web.notfound()

        done = False
        submitted_on = batch_job["submitted_on"]
        container_name = batch_job["container_name"]
        container_title = container_name
        container_description = ""

        file_list = None
        retval = 0
        stdout = ""
        stderr = ""

        try:
            container_metadata = get_batch_container_metadata(container_name)
            if container_metadata == (None, None, None):
                container_title = container_metadata[0]
                container_description = container_metadata[1]
        except:
            pass

        if "result" in batch_job:
            done = True
            retval = batch_job["result"]["retval"]
            stdout = batch_job["result"].get("stdout","")
            stderr = batch_job["result"].get("stderr", "")

            if "file" in batch_job["result"]:
                f = get_gridfs().get(batch_job["result"]["file"])
                try:
                    tar = tarfile.open(fileobj=f,mode='r:gz')
                    file_list = set(tar.getnames()) - set([''])
                    tar.close()
                except:
                    pass
                finally:
                    f.close()

        return renderer.course_admin.batch_summary(course, bid, done, container_name, container_title, container_description, submitted_on,
                                                   retval, stdout, stderr, file_list)