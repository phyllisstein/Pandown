from __future__ import print_function
import sublime
__ST3 = int(sublime.version()) >= 3000
import sublime_plugin
import os
import time
import subprocess
import json
if __ST3:
    import Pandown.minify_json as minify_json
    from Pandown.pandownCriticPreprocessor import *
else:
    import minify_json
    from pandownCriticPreprocessor import *
import tempfile

DEBUG_MODE = False


def debug(theMessage):
    if DEBUG_MODE:
        print("[Pandown: " + str(theMessage) + "]")


def err(e):
    print("[Pandown: " + str(e) + "]")


class PandownBuildCommand(sublime_plugin.WindowCommand):
    def run(self, pandoc_from="", pandoc_to=["", ""], do_open=False, prevent_viewing=False, to_window=False, **kwargs):
        global DEBUG_MODE, __ST3
        env = {}
        self.view = self.window.active_view()
        s = sublime.load_settings("Pandown.sublime-settings")
        user_env = s.get("build_env", None)
        if user_env:
            env.update(user_env)
        env.update(os.environ.copy())
        if sublime.platform() == "osx" or sublime.platform() == "linux":
            env['PATH'] = s.get("install_path", "/usr/local/bin") + ":" + s.get("texbin_path", "/usr/texbin") + ":" + env['PATH']
        else:
            env['PATH'] = s.get("install_path", "C:\\Program Files\\") + ";" + s.get("texbin_path", "C:\\Program Files\\MiKTeX 2.9\\miktex\\bin\\") + ";" + env['PATH']
            env['PATH'] = str(env['PATH'])

        # if not self.checkPandoc(env):
        #     sublime.error_message("Pandown requires Pandoc")
        #     return

        DEBUG_MODE = s.get("PANDOWN_DEBUG", False)

        if self.view.encoding() == "UTF-8" or self.view.encoding() == "Undefined":
            self.encoding = "utf-8"
        else:
            sublime.error_message("Error: Pandoc requires UTF-8.")
            err("Error: Current encoding is " + self.view.encoding())
            return

        inFile = self.view.file_name()

        if inFile is None:
            self.toWindow = True
            self.workingDIR = ""
            workingTemp = tempfile.NamedTemporaryFile("w+", delete=False)
            buff = self.view.substr(sublime.Region(0, self.view.size()))
            workingTemp.close()
            with codecs.open(workingTemp.name, "w+", "utf-8") as f:
                f.write(buff)
            inFile = workingTemp.name
            self.shouldOpen = False
            self.shouldDisplay = True
            self.outFile = ""
        else:
            self.workingDIR = os.path.dirname(inFile)
            os.chdir(self.workingDIR)
            self.shouldOpen = True if (s.get("always_open", False) or do_open) else False
            self.shouldDisplay = True if (s.get("always_display", False) and not prevent_viewing) else False
            self.toWindow = to_window
            workingTemp = None

        self.includes_paths = s.get("includes_paths", [])
        if not isinstance(self.includes_paths, list):
            sublime.error_message("Pandown: includes_paths should be a list, or not set.")
            sublime.status_message("Build failed")
            return
        self.includes_paths_len = len(self.includes_paths)

        argDict = s.get("pandoc_arguments", None)

        if s.get("preprocess_critic", False):
            preprocessor = PandownCriticPreprocessor()
            self.origIn = inFile
            self.criticized = True
            inFile = preprocessor.preprocessCritic(inFile)
        else:
            self.criticized = False

        cmd = self.buildPandocCmd(inFile, pandoc_to, pandoc_from, argDict)

        debug(cmd)

        if not cmd:
            sublime.status_message("Build failed.")
            sublime.error_message("Pandown: Error constructing Pandoc command.")
            return

        if self.view.settings().get("show_panel_on_build", True):
            self.window.run_command("show_panel", {"panel": "output.exec"})

        if not self.toWindow:
            self.window.run_command("pandown_exec", {"cmd": cmd, "env": env})
            self.openAndDisplay()
        else:
            wasShowing = False
            for theView in self.window.views():
                if "Pandoc Output: " in theView.name():
                    self.window.focus_view(theView)
                    outView = theView
                    wasShowing = True
                    break
            if not wasShowing:
                self.splitWindowAndFocus()
                self.window.new_file()
                outView = self.window.active_view()
            outView.run_command("pandown_out_view_erase")
            buffView = outView

            self.window.run_command("pandown_exec", {"cmd": cmd, "env": env, "output_view": buffView.id()})

            if not workingTemp and not self.criticized:
                outView.set_name("Pandoc Output: " + os.path.split(inFile)[1])
            elif self.criticized:
                outView.set_name("Pandoc Output: " + os.path.split(self.origIn)[1])
            else:
                outView.set_name("Pandoc Output: " + time.strftime("%X on %x"))

    def checkPandoc(self, env):
        cmd = ['pandoc', '--version']
        try:
            output = subprocess.check_call(cmd, env=env, shell=False)
        except Exception as e:
            err("Exception: " + str(e))
            return False

        return output == 0

    def splitWindowAndFocus(self):
        theLayout = self.window.get_layout()
        theLayout["cells"] = [[0, 0, 1, 1], [1, 0, 2, 1]]
        theLayout["rows"] = [0.0, 1.0]
        theLayout["cols"] = [0.0, 0.5, 1.0]
        self.window.set_layout(theLayout)
        self.window.focus_group(1)

    def openAndDisplay(self):
        if self.shouldOpen:
            plat = sublime.platform()
            if plat == "osx":
                try:
                    o = subprocess.check_output(["open", self.outFile], stderr=subprocess.STDOUT)
                except CalledProcessError as e:
                    err(e.output)
                else:
                    debug("subprocess: " + o)

            elif plat == "windows":
                os.startfile(self.outFile)
            elif plat == "linux":
                subprocess.Popen(["xdg-open", self.outFile])

        if not self.shouldDisplay:
            return
        wasShowing = False
        for aView in self.window.views():
            if aView.file_name() and self.outFile in aView.file_name():
                self.window.focus_view(aView)
                wasShowing = True
                break
        if not wasShowing and not self.shouldOpen:
            self.splitWindowAndFocus()
            self.window.open_file(self.outFile)
        elif wasShowing and self.shouldOpen:
            self.window.run_command("close")
            theLayout = {"cells": [[0, 0, 1, 1]], "rows": [0.0, 1.0], "cols": [0.0, 1.0]}
            self.window.set_layout(theLayout)

    def walkIncludes(self, lookFor, prepend=None):
        '''
        Check the includes_paths, then the project hierarchy, for the file to include,
        but only if we don't already have a path.
        Order of preference should be: working DIR, project DIRs, then includes_paths,
        then finally giving up and passing the filename to Pandoc.
        '''

        debug("Looking for " + lookFor)
        # Did the user pass a specific file?
        tryAbs = os.path.abspath(os.path.expanduser(lookFor))
        if os.path.isfile(tryAbs):
            debug("It's a path! Returning.")
            return prepend + tryAbs if prepend else tryAbs

        # Is the file in the current build directory?
        tryWorking = os.path.join(self.workingDIR, lookFor)
        if os.path.exists(tryWorking):
            debug("It's in the build directory! Returning.")
            return prepend + tryWorking if prepend else tryWorking

        # Is the file anywhere in the project hierarchy?
        allFolders = self.window.folders()
        debug("allFolders: " + str(allFolders))
        if len(allFolders) > 0:
            topLevel = ""
            (garbage, localName) = os.path.split(self.workingDIR)
            for folder in allFolders:
                for root, dirs, files in os.walk(folder, topdown=False):
                    (garbage, rootTail) = os.path.split(root)
                    if rootTail == localName:
                        topLevel = root
                    for name in dirs:
                        debug("name: " + name)
                        if name == localName:
                            topLevel = folder
            debug("topLevel: " + topLevel)
            checkDIR = self.workingDIR
            debug("Initial checkDIR: " + checkDIR)
            if topLevel:
                while True:
                    fileToCheck = os.path.join(checkDIR, lookFor)
                    if os.path.exists(fileToCheck):
                        debug("It's in the project! Returning %s." % fileToCheck)
                        return prepend + fileToCheck if prepend else fileToCheck
                    if checkDIR == topLevel:
                        break
                    else:
                        checkDIR = os.path.abspath(os.path.join(checkDIR, os.path.pardir))

        # Are there no paths to check?
        if self.includes_paths_len == 0 and lookFor != "pandoc-config.json":
            debug("No includes paths to check. Returning the input for Pandoc to handle.")
            return prepend + lookFor if prepend else lookFor
        # Is the file in the includes_paths?
        for pathToCheck in self.includes_paths:
            pathToCheck = os.path.expanduser(pathToCheck)
            pathToCheck = os.path.abspath(pathToCheck)
            fileToCheck = os.path.join(pathToCheck, lookFor)
            if os.path.isfile(fileToCheck):
                debug("It's in the includes paths! Returning: " + fileToCheck)
                return prepend + fileToCheck if prepend else fileToCheck

        # If the script was checking for a pandoc-config.json, return None.
        if lookFor == "pandoc-config.json":
            debug("Couldn't find config file in project path.")
            return None
        else:
            # The file wasn't anywhere, so let Pandoc handle it.
            debug("Can't find %s. Letting Pandoc deal with it." % lookFor)
            return prepend + lookFor if prepend else lookFor

        sublime.error_message("Fatal error looking for {0}".format(lookFor))
        return None

    def buildPandocCmd(self, inFile, to, pandoc_from, a):
        __ST3 = int(sublime.version()) >= 3000
        cmd = ['pandoc']

        unzipped = os.path.join(sublime.packages_path(), 'Pandown', 'default-pandoc-config-plain.json')
        if os.path.exists(unzipped):
            with codecs.open(unzipped, "r", "utf-8") as f:
                s = json.load(f)
            s = s["pandoc_arguments"]
        else:
            r = sublime.load_resource("Packages/Pandown/default-pandoc-config-plain.json")
            s = json.loads(r)
            s = s["pandoc_arguments"]

        s["command_arguments"]["indented-code-classes"].extend(a["command_arguments"].pop("indented-code-classes", []))
        s["command_arguments"]["variables"].update(a["command_arguments"].pop("variables", {}))
        s["command_arguments"]["include-in-header"].extend(a["command_arguments"].pop("include-in-header", []))
        s["command_arguments"]["include-before-body"].extend(a["command_arguments"].pop("include-before-body", []))
        s["command_arguments"]["include-after-body"].extend(a["command_arguments"].pop("include-after-body", []))
        s["command_arguments"]["css"].extend(a["command_arguments"].pop("css", []))
        s["command_arguments"]["number-offset"].extend(a["command_arguments"].pop("number-offset", []))
        s["command_arguments"].update(a["command_arguments"])
        s["markdown_extensions"].update(a.get("markdown_extensions", {}))

        configLoc = self.walkIncludes("pandoc-config.json")
        if configLoc:
            try:
                f = codecs.open(configLoc, "r", "utf-8")
            except IOError as e:
                sublime.status_message("Error: pandoc-config exists, but could not be read.")
                err("Pandown Exception: " + str(e))
                err("See README for help and support information.")
                f.close()
            else:
                pCommentedStr = f.read()
                f.close()
                pStr = minify_json.json_minify(pCommentedStr)
                try:
                    p = json.loads(pStr)
                except (KeyError, ValueError) as e:
                    sublime.status_message("JSON Error: Cannot parse pandoc-config. See console for details.")
                    err("Pandown Exception: " + str(e))
                    err("See README for help and support information.")
                    return None
                if "pandoc_arguments" in p:
                    pArg = p["pandoc_arguments"]
                    p = pArg

            if p.get("command_arguments", None):
                s["command_arguments"]["indented-code-classes"].extend(p["command_arguments"].pop("indented-code-classes", []))
                s["command_arguments"]["variables"].update(p["command_arguments"].pop("variables", {}))
                s["command_arguments"]["include-in-header"].extend(p["command_arguments"].pop("include-in-header", []))
                s["command_arguments"]["include-before-body"].extend(p["command_arguments"].pop("include-before-body", []))
                s["command_arguments"]["include-after-body"].extend(p["command_arguments"].pop("include-after-body", []))
                s["command_arguments"]["css"].extend(p["command_arguments"].pop("css", []))
                s["command_arguments"]["number-offset"].extend(p["command_arguments"].pop("number-offset", []))
                s["command_arguments"].update(p["command_arguments"])
            if p.get("markdown_extensions", None):
                s["markdown_extensions"].update(p["markdown_extensions"])

        markdown_extensions = s["markdown_extensions"]
        if pandoc_from == "markdown":
            md_config = "markdown"
            for (k, v) in markdown_extensions.items():
                sign = "+" if v else "-"
                append = "%s%s" % (sign, k)
                md_config += append
            pandoc_from = md_config

        # if self.makePDF:
        #     self.outFile = os.path.splitext(inFile)[0] + ".pdf" if not self.criticized else os.path.splitext(self.origIn)[0] + ".pdf"
        #     cmd.append("--output=" + self.outFile)
        #     cmd.append("--from=" + pandoc_from)
        if self.toWindow:
            pass
        else:
            self.outFile = os.path.splitext(inFile)[0] + to[1] if not self.criticized else os.path.splitext(self.origIn)[0] + to[1]
            cmd.append("--output=" + self.outFile)
            cmd.append("--to=" + to[0])
            cmd.append("--from=" + pandoc_from)

        command_arguments = s["command_arguments"]
        for (k, v) in command_arguments.items():
            if v is False:
                pass
            elif v is True and k != "toc-depth" and k != "base-header-level" and k != "slide-level" and k != "tab-stop":
                cmd.append("--%s" % k)
            elif isinstance(v, list) and len(v) > 0:
                if k == "indented-code-classes" or k == "number-offset":
                    buff = "--%s=" % k
                    for item in v:
                        buff += str(item) + ","
                    cmd.append(buff[:-1])
                else:
                    for theFile in v:
                        toAppend = self.walkIncludes(theFile, prepend="--%s=" % k)
                        cmd.append(toAppend)
            elif isinstance(v, dict):
                for (_k, _v) in v.items():
                    if isinstance(_v, list):
                        for item in _v:
                            cmd.append("--variable=" + _k + ":" + item)
                    else:
                        if _v is not False:
                            cmd.append("--variable=" + _k + ":" + _v)
            elif not __ST3 and (((isinstance(v, unicode) or isinstance(v, str)) and len(v) > 0) or isinstance(v, int)):
                if k == "template":
                    cmd.append(self.walkIncludes(v, prepend="--%s=" % k))
                else:
                    cmd.append("--%s=%s" % (k, v))
            elif __ST3 and ((isinstance(v, str) and len(v) > 0) or isinstance(v, int)):
                if k == "template":
                    cmd.append(self.walkIncludes(v, prepend="--%s=" % k))
                else:
                    cmd.append("--%s=%s" % (k, v))
        cmd.append(inFile)

        return cmd


class PandownOutViewEraseCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.erase(edit, sublime.Region(0, self.view.size()))
