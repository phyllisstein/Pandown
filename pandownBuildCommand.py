import sublime
import sublime_plugin
import os
import time
import subprocess
import json
import minify_json
import tempfile
import pandownProcess


DEBUG_MODE = False


def debug(theMessage, shouldLog=False):
    if DEBUG_MODE:
        print "[" + str(theMessage) + "]"


class pandownBuildCommand(sublime_plugin.WindowCommand):
    def run(self, pandoc_from="", pandoc_to=["", ""], do_open=False, prevent_viewing=False, flag_pdf=False, to_window=False, **kwargs):
        sublime.status_message("Building")

        self.view = self.window.active_view()

        global DEBUG_MODE
        DEBUG_MODE = self._getSetting("PANDOWN_DEBUG", False)

        if self.view.encoding() == "UTF-8" or self.view.encoding() == "Undefined":
            self.encoding = "utf-8"
        else:
            sublime.error_message("Error: Pandoc requires UTF-8.")
            print "[Error: Current encoding is " + self.view.encoding() + "]"
            return

        self.inFile = self.view.file_name()

        if self.inFile == None:
            self.toWindow = True
            self.fromDirty = False
            self.workingDIR = ""
            self.workingTemp = tempfile.NamedTemporaryFile("w+", delete=False)
            buff = self.view.substr(sublime.Region(0, self.view.size()))
            self.workingTemp.write(buff)
            self.workingTemp.close()
            self.inFile = self.workingTemp.name
        elif self.view.is_dirty():  # There is a file, but it's dirty
            self.toWindow = True
            self.fromDirty = True
            self.workingDIR = os.path.dirname(self.inFile)
            os.chdir(self.workingDIR)
            self.workingTemp = tempfile.NamedTemporaryFile("w+", delete=False)
            buff = self.view.substr(sublime.Region(0, self.view.size()))
            self.workingTemp.write(buff)
            self.workingTemp.close()
            self.tempLoc = self.workingTemp.name
        else:
            self.workingDIR = os.path.dirname(self.inFile)
            os.chdir(self.workingDIR)
            self.shouldOpen = True if ((self._getSetting("always_open", False) or do_open) and not prevent_viewing) else False
            self.shouldDisplay = True if (self._getSetting("always_display", False) and not prevent_viewing) else False
            self.fromDirty = False
            self.makePDF = flag_pdf
            self.toWindow = to_window

        self.includes_paths = self._getSetting("includes_paths", [])
        if not isinstance(self.includes_paths, list):
            sublime.error_message("Pandown: includes_paths should be a list, or not set.")
            sublime.status_message("Build failed")
            return
        self.includes_paths_len = len(self.includes_paths)

        env = {}
        user_env = self._getSetting("build_env", {})
        if user_env:
            env.update(user_env)
        env.update(os.environ.copy())
        env['PATH'] = env['PATH'] + ":" + self._getSetting("install_path", "/usr/local/bin") + ":" + self._getSetting("texbin_path", "/usr/texbin")

        argDict = self._getSetting("pandoc_arguments", None)
        cmd = self._buildPandocCmd(self.inFile, pandoc_to, pandoc_from, argDict)

        debug(cmd)

        if not cmd:
            sublime.status_message("Build failed. See console for details.")
            raise Exception("Error constructing Pandoc command.")

            return

        if sublime.load_settings("Preferences.sublime-settings").get("show_panel_on_build", True):
            self.window.run_command("show_panel", {"panel": "output.exec"})

        if not self.toWindow:
            self.output_view = self.window.get_output_panel("exec")
            self.output_view.settings().set("result_file_regex", "")
            self.output_view.settings().set("result_line_regex", "")
            self.output_view.settings().set("result_base_dir", "")
            self.window.get_output_panel("exec")

            errorType = OSError
            try:
                self.theListener = pandownProcess.pandownDefaultListener(self, self.output_view)
                self.buildProcess = pandownProcess.AsyncProcess(cmd, env, self.theListener)
            except errorType as e:
                self.theListener.append_data(None, str(e) + "\n")
                self.theListener.append_data(None, "[cmd: " + str(cmd) + "]\n")
                self.theListener.append_data(None, "[dir: " + str(os.getcwdu()) + "]\n")
                self.theListener.append_data(None, "[path: " + str(env['PATH']) + "]\n")
            self.theListener.append_data(None, "[Finished]")
        else:
            self.errorView = self.window.get_output_panel("exec")
            self.errorView.settings().set("result_file_regex", "")
            self.errorView.settings().set("result_line_regex", "")
            self.errorView.settings().set("result_base_dir", "")
            self.window.get_output_panel("exec")

            # self.window.run_command("save")
            wasShowing = False
            for theView in self.window.views():
                if "Pandoc Output: " in theView.name():
                    self.window.focus_view(theView)
                    outView = theView
                    wasShowing = True
                    break
            if not wasShowing:
                self._splitWindowAndFocus()
                outView = self.window.new_file()
            edit = outView.begin_edit()
            outView.erase(edit, sublime.Region(0, outView.size()))
            outView.end_edit(edit)
            self.buffView = outView

            errorType = OSError
            try:
                self.theListener = pandownProcess.pandownSTDIOListener(self, self.errorView, self.buffView)
                self.buildProcess = pandownProcess.AsyncProcess(cmd, env, self.theListener)
            except errorType as e:
                self.theListener.append_data_error(None, str(e) + "\n")
                self.theListener.append_data_error(None, "[cmd: " + str(cmd) + "]\n")
                self.theListener.append_data_error(None, "[dir: " + str(os.getcwdu()) + "]\n")
                self.theListener.append_data_error(None, "[path: " + str(env['PATH']) + "]\n")
            self.theListener.append_data_error(None, "[Finished]")

            if not hasattr(self, "workingTemp") or self.fromDirty:
                outView.set_name("Pandoc Output: " + os.path.split(self.inFile)[1])
            else:
                outView.set_name("Pandoc Output: " + time.strftime("%X on %x"))

    def is_enabled(self, kill=False):
        if kill:
            return hasattr(self, 'buildProcess') and self.buildProcess and self.buildProcess.poll()
        else:
            return True

    def _getSetting(self, theSetting, default):
        viewSetting = self.view.settings().get(theSetting) if self.view.settings().has(theSetting) else None
        packageSetting = sublime.load_settings("Pandown.sublime-settings").get(theSetting) if sublime.load_settings("Pandown.sublime-settings").has(theSetting) else None
        shouldMerge = (getattr(viewSetting, "update", None)) and (getattr(packageSetting, "update", None))
        if shouldMerge:
            packageSetting.update(viewSetting)
            return packageSetting
        if not viewSetting and not packageSetting:
            return default
        return viewSetting if viewSetting else packageSetting

    def _splitWindowAndFocus(self):
        theLayout = self.window.get_layout()
        theLayout["cells"] = [[0, 0, 1, 1], [1, 0, 2, 1]]
        theLayout["rows"] = [0.0, 1.0]
        theLayout["cols"] = [0.0, 0.5, 1.0]
        self.window.set_layout(theLayout)
        self.window.focus_group(1)

    def _openAndDisplay(self):
        if self.shouldOpen:
            plat = sublime.platform()
            if plat == "osx":
                subprocess.call(["open", self.outFile])
            elif plat == "windows":
                os.startfile(self.outFile)
            elif plat == "linux":
                subprocess.call(["xdg-open", self.outFile])

        if not self.shouldDisplay:
            return
        wasShowing = False
        for aView in self.window.views():
            if aView.file_name() and self.outFile in aView.file_name():
                self.window.focus_view(aView)
                wasShowing = True
                break
        if not wasShowing and not self.shouldOpen:
            self._splitWindowAndFocus()
            self.window.open_file(self.outFile)
        elif wasShowing and self.shouldOpen:
            self.window.run_command("close")
            theLayout = {"cells": [[0, 0, 1, 1]], "rows": [0.0, 1.0], "cols": [0.0, 1.0]}
            self.window.set_layout(theLayout)

    def _walkIncludes(self, lookFor, prepend=None):
        # Check the includes_paths, then the project hierarchy, for the file to include,
        # but only if we don't already have a path.
        # Order of preference should be: working DIR, project DIRs, then includes_paths,
        # then finally giving up and passing the filename to Pandoc.

        debug("Looking for " + lookFor)
        # Did the user pass a specific file?
        tryAbs = os.path.abspath(os.path.expanduser(lookFor))
        if os.path.isfile(tryAbs):
            debug("It's a path! Returning.")
            return prepend + tryAbs if prepend else tryAbs
        # Are there no paths to check? Don't do this if we're looking for the config file,
        # which doesn't need includes_paths to work.
        if self.includes_paths_len == 0 and lookFor != "pandoc-config.json":
            debug("No includes paths to check. Returning the input for Pandoc to handle.")
            return prepend + lookFor if prepend else lookFor

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
            while True:
                fileToCheck = os.path.join(checkDIR, lookFor)
                if os.path.exists(fileToCheck):
                    debug("It's in the project! Returning %s." % fileToCheck)
                    return prepend + fileToCheck if prepend else fileToCheck
                    break
                if checkDIR == topLevel:
                    break
                else:
                    checkDIR = os.path.abspath(os.path.join(checkDIR, os.path.pardir))

        # Is the file in the includes_paths?
        for pathToCheck in self.includes_paths:
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

        sublime.error_message("Fatal error looking for " + lookFor)
        return None

    def _buildPandocCmd(self, inFile, to, pandoc_from, a):
        cmd = ['pandoc']

        if self.fromDirty:
            cmd.append("--from=" + pandoc_from)
            cmd.append("--to=" + to[0])
            inFile = self.tempLoc
        elif self.toWindow:
            pass
        elif self.makePDF:
            self.outFile = os.path.splitext(inFile)[0] + ".pdf"
            cmd.append("--output=" + self.outFile)
            cmd.append("--from=" + pandoc_from)
        else:
            self.outFile = os.path.splitext(inFile)[0] + to[1]
            cmd.append("--output=" + self.outFile)
            cmd.append("--to=" + to[0])
            cmd.append("--from=" + pandoc_from)

        try:
            f = open(os.path.join(sublime.packages_path(), 'Pandown', '.default-pandoc-config-plain.json'))
        except IOError as e:
            sublime.message_dialog("Could not open default configuration file. See console for details.")
            print "[Pandown Exception: " + str(e) + "]"
            print "[See README for help and support information.]"
            return None
        else:
            s = json.load(f)
            f.close()
            sArg = s["pandoc_arguments"]
            s = sArg

        s["indented_code_classes"].extend(a.pop("indented_code_classes", []))
        s["variables"].update(a.pop("variables", []))
        s["include_in_header"].extend(a.pop("include_in_header", []))
        s["include_before_body"].extend(a.pop("include_before_body", []))
        s["include_after_body"].extend(a.pop("include_after_body", []))
        s["css"].extend(a.pop("css", []))
        s.update(a)

        configLoc = self._walkIncludes("pandoc-config.json")
        if configLoc:
            try:
                f = open(configLoc)
            except IOError as e:
                sublime.status_message("Error: pandoc-config exists, but could not be read.")
                print "[Pandown Exception: " + str(e) + "]"
                print "[See README for help and support information.]"
            else:
                pCommentedStr = f.read()
                f.close()
                pStr = minify_json.json_minify(pCommentedStr)
                try:
                    p = json.loads(pStr)
                except (KeyError, ValueError) as e:
                    sublime.status_message("JSON Error: Cannot parse pandoc-config. See console for details.")
                    print "[Pandown Exception: " + str(e) + "]"
                    print "[See README for help and support information.]"
                    return None
                if "pandoc_arguments" in p:
                    pArg = p["pandoc_arguments"]
                    p = pArg
            s["indented_code_classes"].extend(p.pop("indented_code_classes", []))
            s["variables"].update(p.pop("variables", []))
            s["include_in_header"].extend(p.pop("include_in_header", []))
            s["include_before_body"].extend(p.pop("include_before_body", []))
            s["include_after_body"].extend(p.pop("include_after_body", []))
            s["css"].extend(p.pop("css", []))
            s.update(p)

        try:
            if s["data_dir"]:
                cmd.append("--data-dir=" + s["data_dir"])
            if s["markdown_strict"]:
                cmd.append("--markdown-strict")
            if s["parse_raw"]:
                cmd.append("--parse-raw")
            if s["smart"]:
                cmd.append("--smart")
            if s["old_dashes"]:
                cmd.append("--old-dashes")
            if s["base_header_level"] != 1:
                cmd.append("--base-header-level=" + str(s["base_header_level"]))

            if len(s["indented_code_classes"]) > 0 and isinstance(s["indented_code_classes"], list):
                buff = "--indented-code-classes="
                for theClass in s["indented_code_classes"]:
                    buff = buff + str(theClass) + " "
                cmd.append(buff)

            if s["normalize"]:
                cmd.append("--normalize")
            if s["tab_stop"] != 4:
                cmd.append("--tab-stop=" + str(s["tab_stop"]))
            if s["standalone"]:
                cmd.append("--standalone")

            if s["template"]:
                toAppend = self._walkIncludes(s["template"], "--template=")
                cmd.append(toAppend)

            if s["variables"] != {}:
                for (k, v) in s["variables"].iteritems():
                    if isinstance(v, list):
                        for items in v:
                            cmd.append("--variable=" + str(k) + ":" + str(items))
                    else:
                        if v != False:
                            cmd.append("--variable=" + str(k) + ":" + str(v))
            if s["no_wrap"]:
                cmd.append("--no-wrap")
            if s["columns"] > 0:
                cmd.append("--columns=" + repr(s["columns"]))
            if s["table_of_contents"]:
                cmd.append("--table-of-contents")
            if s["no_highlight"]:
                cmd.append("--no-highlight")
            if s["highlight_style"]:
                cmd.append("--highlight-style=" + s["highlight_style"])

            # As inappropriate as all this typechecking is, I can't think of another way to
            # be absolutely sure that the user didn't pass in a single string.
            if isinstance(s["include_in_header"], list):
                for theInclude in s["include_in_header"]:
                    toAppend = self._walkIncludes(theInclude, "--include-in-header=")
                    cmd.append(toAppend)
            else:
                print "[Pandown Warning: include_in_header should be a list. Ignoring.]"
                sublime.status_message("include_in_header not a list.")

            if isinstance(s["include_before_body"], list):
                for theInclude in s["include_before_body"]:
                    toAppend = self._walkIncludes(theInclude, "--include-before-body=")
                    cmd.append(toAppend)
            else:
                print "[Pandown Warning: include_before_body should be a list. Ignoring.]"
                sublime.status_message("include_before_body not a list.")

            if isinstance(s["include_after_body"], list):
                for theInclude in s["include_after_body"]:
                    toAppend = self._walkIncludes(theInclude, "--include-after-body=")
                    cmd.append(toAppend)
            else:
                print "[Pandown Warning: include_after_body should be a list. Ignoring.]"
                sublime.status_message("include_after_body not a list.")

            if s["self_contained"]:
                cmd.append("--self-contained")
            if s["ascii"]:
                cmd.append("--ascii")
            if s["reference_links"]:
                cmd.append("--reference-links")
            if s["atx_headers"]:
                cmd.append("--atx-headers")
            if s["chapters"]:
                cmd.append("--chapters")
            if s["number_sections"]:
                cmd.append("--number-sections")
            if s["no_tex_ligatures"]:
                cmd.append("--no-tex-ligatures")
            if s["listings"]:
                cmd.append("--listings")
            if s["incremental"]:
                cmd.append("--incremental")
            if s["slide_level"] > -1:
                cmd.append("--slide-level=" + str(s["slide_level"]))
            if s["section_divs"]:
                cmd.append("--section-divs")
            if s["email_obfuscation"] != "":
                cmd.append("--email-obfuscation=" + s["email_obfuscation"])
            if s["id_prefix"]:
                cmd.append("--id-prefix=" + s["id_prefix"])
            if s["title_prefix"]:
                cmd.append("--title-prefix=" + s["title_prefix"])

            if isinstance(s["css"], list) and len(s["css"]) > 0:
                for theCSS in s["css"]:
                    cmd.append("--css=" + theCSS)

            if s["reference_odt"] != "":
                toAppend = self._walkIncludes(s["reference_odt"], "--reference-odt=")
                cmd.append(toAppend)
            if s["reference_docx"] != "":
                toAppend = self._walkIncludes(s["reference_docx"], "--reference-docx=")
                cmd.append(toAppend)
            if s["epub_stylesheet"] != "":
                toAppend = self._walkIncludes(s["epub_stylesheet"], "--epub-stylesheet=")
                cmd.append(toAppend)
            if s["epub_coverimage"] != "":
                toAppend = self._walkIncludes(s["epub_coverimage"], "--epub-cover-image=")
                cmd.append(toAppend)
            if s["epub_metadata"] != "":
                toAppend = self._walkIncludes(s["epub_metadata"], "--epub-metadata=")
                cmd.append(toAppend)
            if s["epub_embed_font"] != "":
                toAppend = self._walkIncludes(s["epub_embed_font"], "--epub-embed-font=")
                cmd.append(toAppend)
            if s["latex_engine"] != "":
                cmd.append("--latex-engine=" + s["latex_engine"])
            if s["bibliography"] != "":
                toAppend = self._walkIncludes(s["bibliography"], "--bibliography=")
                cmd.append(toAppend)
            if s["csl"] != "":
                toAppend = self._walkIncludes(s["csl"], "--csl=")
                cmd.append(toAppend)
            if s["citation_abbreviations"] != "":
                toAppend = self._walkIncludes(s["citation_abbreviations"], "--citation-abbreviations=")
                cmd.append(toAppend)
            if s["natbib"]:
                cmd.append("--natbib")
            if s["biblatex"]:
                cmd.append("--biblatex")
            if s["gladtex"]:
                cmd.append("--gladtex")

            latexmathml = s["latexmathml"]
            if latexmathml == False:
                pass
            elif latexmathml == True:
                cmd.append("--latexmathml")
            else:
                cmd.append("--latexmathml=" + latexmathml)

            mathml = s["mathml"]
            if mathml == False:
                pass
            elif mathml == True:
                cmd.append("--mathml")
            else:
                cmd.append("--mathml=" + mathml)

            jsmath = s["jsmath"]
            if jsmath == False:
                pass
            elif jsmath == True:
                cmd.append("--jsmath")
            else:
                cmd.append("--jsmath=" + jsmath)

            mathjax = s["mathjax"]
            if mathjax == False:
                pass
            elif mathjax == True:
                cmd.append("--mathjax")
            else:
                cmd.append("--mathjax=" + mathjax)

            mimetex = s["mimetex"]
            if mimetex == False:
                pass
            elif mimetex == True:
                cmd.append("--mimetex")
            else:
                cmd.append("--mimetex=" + mimetex)

            webtex = s["webtex"]
            if webtex == False:
                pass
            elif webtex == True:
                cmd.append("--webtex")
            else:
                cmd.append("--webtex=" + webtex)
        except (KeyError, ValueError) as e:
            sublime.error_message("Pandown: Errors in configuration file. See console for details.")
            print "[Pandown Exception: " + str(e) + "]"
            print "[See README for help and support information.]"
            return None

        cmd.append(inFile)

        return cmd
