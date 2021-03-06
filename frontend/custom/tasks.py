# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 Université Catholique de Louvain.
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
""" Classes modifying basic tasks, problems and boxes classes """
from common.base import id_checker
from common.task_file_managers.manage import get_task_file_manager
import common.tasks
from frontend.accessible_time import AccessibleTime
from frontend.custom.task_problems import DisplayableCodeProblem, DisplayableCodeSingleLineProblem, DisplayableMatchProblem, \
    DisplayableMultipleChoiceProblem, DisplayableCodeFileProblem
from frontend.parsable_text import ParsableText
from frontend.plugins.plugin_manager import PluginManager


class FrontendTask(common.tasks.Task):
    """ A task that stores additionnal context informations """

    # Redefine _problem_types with displayable ones
    _problem_types = {
        "code": DisplayableCodeProblem,
        "code-file": DisplayableCodeFileProblem,
        "code-single-line": DisplayableCodeSingleLineProblem,
        "multiple-choice": DisplayableMultipleChoiceProblem,
        "match": DisplayableMatchProblem}

    def __init__(self, course, taskid, init_data=None):
        # We load the descriptor of the task here to allow plugins to modify settings of the task before it is read by the Task constructor
        if not id_checker(taskid):
            raise Exception("Task with invalid id: " + course.get_id() + "/" + taskid)
        if init_data is None:
            try:
                init_data = get_task_file_manager(course.get_id(), taskid).read()
            except Exception as inst:
                raise Exception("Error while reading task file: " + course.get_id() + "/" + taskid + " :\n" + str(inst))
        PluginManager.get_instance().call_hook('modify_task_data', course=course, taskid=taskid, data=init_data)

        # Now init the task
        common.tasks.Task.__init__(self, course, taskid, init_data)

        self._name = self._data.get('name', 'Task {}'.format(taskid))

        self._context = ParsableText(self._data.get('context', ""), "HTML" if self._data.get("contextIsHTML", False) else "rst")

        # Authors
        if isinstance(self._data.get('author'), basestring):  # verify if author is a string
            self._author = [self._data['author']]
        elif isinstance(self._data.get('author'), list):  # verify if author is a list
            for author in self._data['author']:
                if not isinstance(author, basestring):  # authors must be strings
                    raise Exception("This task has an invalid author")
            self._author = self._data['author']
        else:
            self._author = []

        # Grade weight
        self._weight = float(self._data.get("weight", 1.0))

        # _accessible
        self._accessible = AccessibleTime(self._data.get("accessible", None))

        # Order
        self._order = int(self._data.get('order', -1))

    def get_name(self):
        """ Returns the name of this task """
        return self._name

    def get_context(self):
        """ Get the context(description) of this task """
        return self._context

    def get_authors(self):
        """ Return the list of this task's authors """
        return self._author

    def get_order(self):
        """ Get the position of this task in the course """
        return self._order

    def get_grading_weight(self):
        """ Get the relative weight of this task in the grading """
        return self._weight

    def is_visible_by_students(self):
        """ Returns true if the task is accessible by all students that are not administrator of the course """
        return self.get_course().is_open_to_non_staff() and self._accessible.after_start()

    def is_visible_by_user(self, username=None):
        """ Returns true if the task is visible by the user """
        if username is None:
            import frontend.user as User

            username = User.get_username()
        return (self.get_course().is_open_to_user(username) and self._accessible.after_start()) or username in self.get_course().get_staff()

    def can_user_submit(self, username=None):
        """ returns true if the user can submit his work for this task """
        if username is None:
            import frontend.user as User

            username = User.get_username()
        return (self.get_course().is_open_to_user(username) and self._accessible.is_open()) or username in self.get_course().get_staff()

    def get_deadline(self):
        """ Returns a string containing the deadline for this task """
        if self._accessible.is_always_accessible():
            return "No deadline"
        elif self._accessible.is_never_accessible():
            return "It's too late"
        else:
            return self._accessible.get_end_date().strftime("%d/%m/%Y %H:%M:%S")

    def get_user_status(self):
        """ Returns "succeeded" if the current user solved this task, "failed" if he failed, and "notattempted" if he did not try it yet """
        import frontend.user as User  # insert here to avoid initialisation of session

        task_cache = User.get_data().get_task_data(self.get_course_id(), self.get_id())
        if task_cache is None:
            return "notviewed"
        if task_cache["tried"] == 0:
            return "notattempted"
        return "succeeded" if task_cache["succeeded"] else "failed"

    def get_user_grade(self):
        """ Returns the grade (a floating-point number between 0 and 100) of the student """
        import frontend.user as User  # insert here to avoid initialisation of session

        task_cache = User.get_data().get_task_data(self.get_course_id(), self.get_id())
        if task_cache is None:
            return 0.0
        return task_cache.get("grade", 0.0)

    def adapt_input_for_backend(self, input_data):
        """ Adapt the input from web.py for the backend """
        for problem in self._problems:
            input_data = problem.adapt_input_for_backend(input_data)
        return input_data
