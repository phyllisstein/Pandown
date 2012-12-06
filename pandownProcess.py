import sublime
import time
import os
import subprocess
import sys
import thread
import functools


class ProcessListener(object):

    def on_data_out(self, proc, data):
        pass

    def on_data_err(self, proc, data):
        pass

    def on_finished(self, proc):
        pass


class AsyncProcess(object):
    def __init__(self, command, env, listener):
        self.listener = listener
        self.killed = False
        self.startTime = time.time()

        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        processEnvironment = os.environ.copy()
        processEnvironment.update(env)
        for k, v in processEnvironment.items():
            processEnvironment[k] = os.path.expandvars(v).encode(sys.getfilesystemencoding())

        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo, env=processEnvironment)
        if self.process.stdout:
            thread.start_new_thread(self.read_stdout, ())

        if self.process.stderr:
            thread.start_new_thread(self.read_stderr, ())

    def kill(self):
        if not self.killed:
            self.killed = True
            self.process.terminate()
            self.listener = None

    def poll(self):
        return self.process.poll() == None

    def exit_code(self):
        return self.process.poll()

    def read_stdout(self):
        while True:
            data = os.read(self.process.stdout.fileno(), 2 ** 15)

            if data != "":
                if self.listener:
                    self.listener.on_data_out(self, data)
            else:
                self.process.stdout.close()
                if self.listener:
                    self.listener.on_finished(self)
                break

    def read_stderr(self):
        while True:
            data = os.read(self.process.stderr.fileno(), 2 ** 15)

            if data != "":
                if self.listener:
                    self.listener.on_data_err(self, data)
            else:
                self.process.stderr.close()
                if self.listener:
                    self.listener.on_finished(self)
                break


class pandownSTDIOListener(ProcessListener):
    def __init__(self, caller, errorPanel, outputView):
        self.caller = caller
        self.err = errorPanel
        self.view = outputView

    def append_data_output(self, proc, data):
        if proc != self.caller.buildProcess:
            if proc:
                proc.kill()
            return

        try:
            theStr = data.decode(self.caller.encoding)
        except:
            theStr = "[Decode error: output not " + self.caller.encoding + "]\n"
            proc = None

        theStr = theStr.replace('\r\n', '\n').replace('\r', '\n')

        selection_was_at_end = (len(self.view.sel()) == 1
                                and self.view.sel()[0] == sublime.Region(self.view.size()))

        edit = self.view.begin_edit()
        self.view.insert(edit, self.view.size(), theStr)
        if selection_was_at_end:
            self.view.show(self.view.size())
        self.view.end_edit(edit)

    def append_data_error(self, proc, data):
        if proc != self.caller.buildProcess:
            if proc:
                proc.kill()
            return

        try:
            theStr = data.decode(self.caller.encoding)
        except:
            theStr = "[Decode error: output not " + self.caller.encoding + "]\n"
            proc = None

        theStr = theStr.replace('\r\n', '\n').replace('\r', '\n')

        selection_was_at_end = (len(self.err.sel()) == 1
                                and self.err.sel()[0] == sublime.Region(self.err.size()))
        self.err.set_read_only(False)
        edit = self.err.begin_edit()
        self.err.insert(edit, self.err.size(), theStr)
        if selection_was_at_end:
            self.err.show(self.err.size())
        self.err.end_edit(edit)
        self.err.set_read_only(True)

    def finish(self, proc):
        elapsed = time.time() - proc.startTime
        exit_code = proc.exit_code()
        if exit_code == 0 or exit_code == None:
            self.append_data_error(proc, ("[Finished in %.1fs]") % (elapsed))
            smoothExit = True
        else:
            self.append_data_error(proc, ("[Finished in %.1fs with error code %d]") % (elapsed, exit_code))
            smoothExit = False

        if proc != self.caller.buildProcess:
            return

        errs = self.err.find_all_results()
        if len(errs) == 0 and smoothExit == True:
            sublime.status_message("Build finished")
        elif len(errs) == 0 and smoothExit == False:
            sublime.status_message(("Build failed with error code %d") % exit_code)
        else:
            sublime.status_message(("Build failed with %d errors") % len(errs))

        edit = self.err.begin_edit()
        self.err.sel().clear()
        self.err.sel().add(sublime.Region(0))
        self.err.end_edit(edit)

        edit = self.view.begin_edit()
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(0))
        self.view.end_edit(edit)

    def on_data_out(self, proc, data):
        sublime.set_timeout(functools.partial(self.append_data_output, proc, data), 0)

    def on_data_err(self, proc, data):
        sublime.set_timeout(functools.partial(self.append_data_error, proc, data), 0)

    def on_finished(self, proc):
        sublime.set_timeout(functools.partial(self.finish, proc), 0)


class pandownDefaultListener(ProcessListener):
    def __init__(self, caller, errorPanel):
        self.caller = caller
        self.err = errorPanel

    def append_data(self, proc, data):
        if proc != self.caller.buildProcess:
            if proc:
                proc.kill()
            return

        try:
            theStr = data.decode(self.caller.encoding)
        except:
            theStr = "[Decode error: output not " + self.encoding + "]\n"
            proc = None

        theStr = theStr.replace('\r\n', '\n').replace('\r', '\n')

        selection_was_at_end = (len(self.err.sel()) == 1
                                and self.err.sel()[0] == sublime.Region(self.err.size()))
        self.err.set_read_only(False)
        edit = self.err.begin_edit()
        self.err.insert(edit, self.err.size(), theStr)
        if selection_was_at_end:
            self.err.show(self.err.size())
        self.err.end_edit(edit)
        self.err.set_read_only(True)

    def finish(self, proc):
        elapsed = time.time() - proc.startTime
        exit_code = proc.exit_code()
        if exit_code == 0 or exit_code == None:
            self.append_data(proc, ("[Finished in %.1fs]") % (elapsed))
            smoothExit = True
        else:
            self.append_data(proc, ("[Finished in %.1fs with error code %d]") % (elapsed, exit_code))
            smoothExit = False

        if proc != self.caller.buildProcess:
            return

        errs = self.err.find_all_results()
        if len(errs) == 0 and smoothExit == True:
            sublime.status_message("Build finished")
        elif len(errs) == 0 and smoothExit == False:
            sublime.status_message(("Build failed with error code %d") % exit_code)
        else:
            sublime.status_message(("Build failed with %d errors") % len(errs))

        edit = self.err.begin_edit()
        self.err.sel().clear()
        self.err.sel().add(sublime.Region(0))
        self.err.end_edit(edit)

        self.caller._openAndDisplay()

    def on_data_out(self, proc, data):
        sublime.set_timeout(functools.partial(self.append_data, proc, data), 0)

    def on_data_err(self, proc, data):
        sublime.set_timeout(functools.partial(self.append_data, proc, data), 0)

    def on_finished(self, proc):
        sublime.set_timeout(functools.partial(self.finish, proc), 0)
