from __future__ import print_function
import sublime
import sublime_plugin
import time
import os
import subprocess
import threading
import functools


class PandownProcessListener(object):

    def on_data_out(self, proc, data):
        pass

    def on_data_err(self, proc, data):
        pass

    def on_finished(self, proc):
        pass


class PandownAsyncProcess(object):
    def __init__(self, command, env, listener):
        self.listener = listener
        self.killed = False
        self.start_time = time.time()

        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        processEnvironment = os.environ.copy()
        processEnvironment.update(env)
        for k, v in list(processEnvironment.items()):
            processEnvironment[k] = os.path.expandvars(v)

        if sublime.platform() == "windows":
            shell = True
        else:
            shell = False
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo, env=processEnvironment, shell=shell)
        if self.process.stdout:
            # _thread.start_new_thread(self.read_stdout, ())
            threading.Thread(target=self.read_stdout).start()

        if self.process.stderr:
            # _thread.start_new_thread(self.read_stderr, ())
            threading.Thread(target=self.read_stderr).start()

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

            if len(data) > 0:
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

            if len(data) > 0:
                if self.listener:
                    self.listener.on_data_err(self, data)
            else:
                self.process.stderr.close()
                if self.listener:
                    self.listener.on_finished(self)
                break


class PandownExecCommand(sublime_plugin.WindowCommand, PandownProcessListener):
    def run(self, cmd=None, env={}, file_regex="", line_regex="", encoding="utf-8", quiet=True, kill=False, word_wrap=True, syntax="Packages/Text/Plain text.tmLanguage", working_dir="", output_view=None, **kwargs):
        __ST3 = int(sublime.version()) >= 3000
        if kill:
            if self.proc:
                self.proc.kill()
                self.proc = None
                self.append_string_err(None, "[Cancelled]")
            return

        if not output_view:
            self.output_view = self.window.create_output_panel("exec") if __ST3 else self.window.get_output_panel("exec")
            self.error_view = self.output_view
            self.to_window = False
        elif output_view != None:
            for aView in self.window.views():
                if aView.id() == output_view:
                    self.output_view = aView
            self.error_view = self.window.create_output_panel("exec") if __ST3 else self.window.get_output_panel("exec")
            self.to_window = True

        if (working_dir == "" and self.window.active_view() and self.window.active_view().file_name()):
            working_dir = os.path.dirname(self.window.active_view().file_name())

        self.error_view.settings().set("result_file_regex", "")
        self.error_view.settings().set("result_line_regex", "")
        self.error_view.settings().set("result_base_dir", working_dir)
        self.error_view.settings().set("word_wrap", word_wrap)
        self.error_view.settings().set("line_numbers", False)
        self.error_view.settings().set("gutter", False)
        self.error_view.settings().set("scroll_past_end", False)
        if __ST3:
            self.error_view.assign_syntax(syntax)
        else:
            self.error_view.set_syntax_file(syntax)

        if __ST3:
            self.window.create_output_panel("exec")
        else:
            self.window.get_output_panel("exec")

        self.encoding = encoding
        self.quiet = quiet

        self.proc = None
        if not self.quiet:
            print("Running " + " ".join(cmd))
        
        sublime.status_message("Building")

        show_panel_on_build = sublime.load_settings("Preferences.sublime-settings").get("show_panel_on_build", True)
        if show_panel_on_build:
            self.window.run_command("show_panel", {"panel": "output.exec"})

        merged_env = env.copy()
        if self.window.active_view():
            user_env = self.window.active_view().settings().get("build_env")
            if user_env:
                merged_env.update(user_env)

        if sublime.platform() == "windows":
            for k, v in merged_env.items():
                merged_env[k] = str(v)

        if working_dir != "":
            os.chdir(working_dir)

        self.debug_text = ""
        self.debug_text += "[cmd: " + str(cmd) + "]\n"
        self.debug_text += "[dir: " + str(os.getcwd()) + "]\n"

        if "PATH" in merged_env:
            self.debug_text += "[path: " + str(merged_env["PATH"]) + "]"
        else:
            self.debug_text += "[path: " + str(os.environ["PATH"]) + "]"

        try:
            self.proc = PandownAsyncProcess(cmd, merged_env, self)
        except Exception as e:
            self.append_string_err(None, str(e) + "\n")
            self.append_string_err(None, self.debug_text + "\n")
            print(self.debug_text)
            print(e)
            if not self.quiet:
                self.append_string_err(None, "[Finished]")

    def is_enabled(self, kill=False):
        if kill:
            return hasattr(self, 'proc') and self.proc and self.proc.poll()
        else:
            return True

    def append_string_err(self, proc, string):
        self.append_data_error(proc, string.encode(self.encoding))

    def append_string_out(self, proc, string):
        self.append_data_output(proc, string.encode(self.encoding))

    def finish(self, proc):
        if not self.quiet:
            elapsed = time.time() - proc.start_time
            exit_code = proc.exit_code()
            if exit_code == 0 or exit_code == None:
                self.append_string_err(proc, ("[Finished in %.1fs]" % (elapsed)))
            else:
                self.append_string_err(proc, ("[Finished in %.1fs with exit code %d]\n" % (elapsed, exit_code)))

        if proc != self.proc:
            return

        errs = self.error_view.find_all_results()
        if len(errs) == 0:
            sublime.status_message("Build finished")
        else:
            sublime.status_message("Build finished with %d errors" % len(errs))

    def append_data_error(self, proc, data):
        __ST3 = int(sublime.version()) >= 3000
        if proc != self.proc:
            if proc:
                proc.kill()
            return

        try:
            string = data.decode(self.encoding)
        except:
            string = "[Decode error: output not " + self.encoding + "]\n"
            proc = None

        string = string.replace("\r\n", "\n").replace("\r", "\n")
        if __ST3:
            self.error_view.run_command("append", {"characters": string, "force": True})
        else:
            selection_was_at_end = (len(self.error_view.sel()) == 1
                and self.error_view.sel()[0] == sublime.Region(self.error_view.size()))
            self.error_view.set_read_only(False)
            edit = self.error_view.begin_edit()
            self.error_view.insert(edit, self.error_view.size(), string)
            if selection_was_at_end:
                self.error_view.show(self.error_view.size())
            self.error_view.end_edit(edit)
            self.error_view.set_read_only(True)

    def append_data_output(self, proc, data):
        __ST3 = int(sublime.version()) >= 3000
        if proc != self.proc:
            if proc:
                proc.kill()
            return

        try:
            string = data.decode(self.encoding)
        except:
            string = "[Decode error: output not " + self.encoding + "]\n"
            proc = None

        string = string.replace("\r\n", "\n").replace("\r", "\n")
        if __ST3:
            self.output_view.run_command("append", {"characters": string, "force": True})
        else:
            selection_was_at_end = (len(self.output_view.sel()) == 1
                and self.output_view.sel()[0] == sublime.Region(self.output_view.size()))
            edit = self.output_view.begin_edit()
            self.output_view.insert(edit, self.output_view.size(), string)
            if selection_was_at_end:
                self.output_view.show(self.output_view.size())
            self.output_view.end_edit(edit)

    def on_data_out(self, proc, data):
        if self.to_window == False:
            sublime.set_timeout(functools.partial(self.append_data_error, proc, data), 0)
        else:
            sublime.set_timeout(functools.partial(self.append_data_output, proc, data), 0)

    def on_data_err(self, proc, data):
        sublime.set_timeout(functools.partial(self.append_data_error, proc, data), 0)

    def on_finished(self, proc):
        sublime.set_timeout(functools.partial(self.finish, proc), 0)
 proc), 0)
