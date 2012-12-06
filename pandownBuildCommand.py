import sublime
import sublime_plugin
import os
import subprocess
import json
import minify_json
import pandownProcess


DEBUG_MODE = False


def debug(theMessage, shouldLog=False):
    if DEBUG_MODE:
        print "[" + str(theMessage) + "]"


class pandownBuildCommand(sublime_plugin.WindowCommand):
    def run(self, pandoc_from="", pandoc_to=["", ""], do_open=False, prevent_viewing=False, flag_pdf=False, to_window=False, **kwargs):
        sublime.status_message("Building")

        self.view = self.window.active_view()

        if self.view.encoding() == "UTF-8" or self.view.encoding() == "Unknown":
            self.encoding = "utf-8"
        else:
            sublime.error_message("Error: Pandoc requires UTF-8.")
            print "[Error: Current encoding is " + self.view.encoding() + "]"
            return

        self.inFile = self.view.file_name()

        self.workingDIR = os.path.dirname(self.inFile)
        os.chdir(self.workingDIR)

        global DEBUG_MODE
        DEBUG_MODE = self._getSetting("PANDOWN_DEBUG", False)

        self.shouldOpen = True if ((self._getSetting("always_open", False) or do_open) and not prevent_viewing) else False

        self.shouldDisplay = True if (self._getSetting("always_display", False) and not prevent_viewing) else False

        self.makePDF = flag_pdf
        self.toWindow = to_window

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
            self.window.run_command("save")
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

            outView.set_name("Pandoc Output: " + os.path.split(self.inFile)[1])

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
            if self.outFile in aView.file_name():
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

    def _buildPandocCmd(self, inFile, to, pandoc_from, a):
        cmd = ['pandoc']

        if self.makePDF:
            self.outFile = os.path.splitext(inFile)[0] + ".pdf"
            cmd.append("--output=" + self.outFile)
            cmd.append("--from=" + pandoc_from)
        elif self.toWindow:
            pass
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

        if len(self.window.folders()) > 0:
            allFolders = self.window.folders()
            inHere = ""
            (garbage, localName) = os.path.split(self.workingDIR)
            debug("allFolders: " + str(allFolders))
            for folder in allFolders:
                for root, dirs, files in os.walk(folder, topdown=False):
                    for name in dirs:
                        debug("name: " + str(name))
                        if name == localName:
                            inHere = folder
            debug("inHere: " + inHere)
            checkDIR = self.workingDIR
            foundConfig = False
            while not foundConfig:
                if os.path.exists(os.path.join(checkDIR, 'pandoc-config.json')):
                    configLoc = os.path.join(checkDIR, 'pandoc-config.json')
                    foundConfig = True
                else:
                    if checkDIR == inHere:
                        break
                    else:
                        (checkDIR, garbage) = os.path.split(checkDIR)
        if foundConfig:
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
            includes_paths = self._getSetting("includes_paths", [])
            includes_paths_len = len(includes_paths)
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
                if includes_paths_len == 0:
                    cmd.append("--template=" + s["template"])
                elif includes_paths_len > 0 and isinstance(includes_paths, list):
                    toAppend = ""
                    if os.path.exists(os.path.join(self.workingDIR, s["template"])):
                        toAppend = "--template=" + os.path.join(self.workingDIR, s["template"])
                    else:
                        for theIncludesPath in includes_paths:
                            theIncludesPath = os.path.abspath(theIncludesPath)
                            checkFile = os.path.join(theIncludesPath, s["template"])
                            if os.path.exists(checkFile):
                                toAppend = "--template=" + checkFile
                                break
                    if not toAppend:
                        toAppend = "--template=" + s["template"]
                    cmd.append(toAppend)

            if s["variables"] != {}:
                for (k, v) in s["variables"].iteritems():
                    if isinstance(v, list):
                        for items in v:
                            cmd.append("--variable=" + str(k) + ":" + str(items))
                    else:
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
            if includes_paths_len == 0:
                if isinstance(s["include_in_header"], list):
                    for theInclude in s["include_in_header"]:
                        cmd.append("--include-in-header=" + str(theInclude))
                if isinstance(s["include_before_body"], list):
                    for theInclude in s["include_before_body"]:
                        cmd.append("--include-before-body=" + str(theInclude))
                if isinstance(s["include_after_body"], list):
                    for theInclude in s["include_after_body"]:
                        cmd.append("--include-after-body=" + str(theInclude))
            elif includes_paths_len > 0 and isinstance(includes_paths, list):
                if isinstance(s["include_in_header"], list) and len(s["include_in_header"]) > 0:
                    for theInclude in s["include_in_header"]:
                        toAppend = ""
                        if os.path.exists(os.path.join(self.workingDIR, theInclude)):
                            toAppend = "--include-in-header=" + os.path.join(self.workingDIR, theInclude)
                        else:
                            for includeToCheck in includes_paths:
                                includeToCheck = os.path.abspath(includeToCheck)
                                checkInclude = os.path.join(includeToCheck, theInclude)
                                if os.path.exists(checkInclude):
                                    toAppend = "--include-in-header=" + checkInclude
                                    break
                        if not toAppend:
                            toAppend = "--include-in-header=" + theInclude
                        cmd.append(toAppend)
                if isinstance(s["include_before_body"], list) and len(s["include_before_body"]) > 0:
                    for theInclude in s["include_before_body"]:
                        toAppend = ""
                        if os.path.exists(os.path.join(self.workingDIR, theInclude)):
                            toAppend = "--include-before-body" + os.path.join(self.workingDIR, theInclude)
                        else:
                            for includeToCheck in includes_paths:
                                includeToCheck = os.path.abspath(includeToCheck)
                                checkInclude = os.path.join(includeToCheck, theInclude)
                                if os.path.exists(checkInclude):
                                    toAppend = "--include-before-body" + checkInclude
                                    break
                        if not toAppend:
                            toAppend = "--include-before-body" + theInclude
                        cmd.append(toAppend)
                if isinstance(s["include_after_body"], list) and len(s["include_after_body"]) > 0:
                    for theInclude in s["include_after_body"]:
                        toAppend = ""
                        if os.path.exists(os.path.join(self.workingDIR, theInclude)):
                            toAppend = "--include-after-body=" + os.path.join(self.workingDIR, theInclude)
                        else:
                            for includeToCheck in includes_paths:
                                includeToCheck = os.path.abspath(includeToCheck)
                                checkInclude = os.path.join(includeToCheck, theInclude)
                                if os.path.exists(checkInclude):
                                    toAppend = "--include-after-body=" + checkInclude
                                    break
                        if not toAppend:
                            toAppend = "--include-after-body=" + theInclude
                        cmd.append(toAppend)
            else:
                print "[Pandown Error: includes_paths not set as list?]"

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
                if includes_paths_len == 0:
                    cmd.append("--reference-odt=" + s["reference_odt"])
                elif includes_paths_len > 0 and isinstance(includes_paths, list):
                    toAppend = ""
                    if os.path.exists(os.path.join(self.workingDIR, s["reference_odt"])):
                        toAppend = "--reference-odt=" + os.path.join(self.workingDIR, s["reference_odt"])
                    else:
                        for theIncludesPath in includes_paths:
                            theIncludesPath = os.path.abspath(theIncludesPath)
                            checkFile = os.path.join(theIncludesPath, s["reference_odt"])
                            if os.path.exists(checkFile):
                                toAppend = "--reference-odt=" + checkFile
                                break
                    if not toAppend:
                        toAppend = "--reference-odt=" + s["reference_odt"]
                    cmd.append(toAppend)
            if s["reference_docx"] != "":
                if includes_paths_len == 0:
                    cmd.append("--reference-docx=" + s["reference_docx"])
                elif includes_paths_len > 0 and isinstance(includes_paths, list):
                    toAppend = ""
                    if os.path.exists(os.path.join(self.workingDIR, s["reference_docx"])):
                        toAppend = "--reference-docx=" + os.path.join(self.workingDIR, s["reference_docx"])
                    else:
                        for theIncludesPath in includes_paths:
                            theIncludesPath = os.path.abspath(theIncludesPath)
                            checkFile = os.path.join(theIncludesPath, s["reference_docx"])
                            if os.path.exists(checkFile):
                                toAppend = "--reference-docx=" + checkFile
                                break
                    if not toAppend:
                        toAppend = "--reference-docx=" + s["reference_docx"]
                    cmd.append(toAppend)
            if s["epub_stylesheet"] != "":
                if includes_paths_len == 0:
                    cmd.append("--epub-stylesheet=" + s["epub_stylesheet"])
                elif includes_paths_len > 0 and isinstance(includes_paths, list):
                    toAppend = ""
                    if os.path.exists(os.path.join(self.workingDIR, s["epub_stylesheet"])):
                        toAppend = "--epub-stylesheet=" + os.path.join(self.workingDIR, s["epub_stylesheet"])
                    else:
                        for theIncludesPath in includes_paths:
                            theIncludesPath = os.path.abspath(theIncludesPath)
                            checkFile = os.path.join(theIncludesPath, s["epub_stylesheet"])
                            if os.path.exists(checkFile):
                                toAppend = "--epub-stylesheet=" + checkFile
                                break
                    if not toAppend:
                        toAppend = "--epub-stylesheet=" + s["epub_stylesheet"]
                    cmd.append(toAppend)
            if s["epub_coverimage"] != "":
                if includes_paths_len == 0:
                    cmd.append("--epub-cover-image=" + s["epub_coverimage"])
                elif includes_paths_len > 0 and isinstance(includes_paths, list):
                    toAppend = ""
                    if os.path.exists(os.path.join(self.workingDIR, s["epub_coverimage"])):
                        toAppend = "--epub-cover-image=" + os.path.join(self.workingDIR, s["epub_coverimage"])
                    else:
                        for theIncludesPath in includes_paths:
                            theIncludesPath = os.path.abspath(theIncludesPath)
                            checkFile = os.path.join(theIncludesPath, s["epub_coverimage"])
                            if os.path.exists(checkFile):
                                toAppend = "--epub-cover-image=" + checkFile
                                break
                    if not toAppend:
                        toAppend = "--epub-cover-image=" + s["epub_coverimage"]
                    cmd.append(toAppend)
            if s["epub_metadata"] != "":
                if includes_paths_len == 0:
                    cmd.append("--epub-metadata=" + s["epub_metadata"])
                elif includes_paths_len > 0 and isinstance(includes_paths, list):
                    toAppend = ""
                    if os.path.exists(os.path.join(self.workingDIR, s["epub_metadata"])):
                        toAppend = "--epub-metadata=" + os.path.join(self.workingDIR, s["epub_metadata"])
                    else:
                        for theIncludesPath in includes_paths:
                            theIncludesPath = os.path.abspath(theIncludesPath)
                            checkFile = os.path.join(theIncludesPath, s["epub_metadata"])
                            if os.path.exists(checkFile):
                                toAppend = "--epub-metadata=" + checkFile
                                break
                    if not toAppend:
                        toAppend = "--epub-metadata=" + s["epub_metadata"]
                    cmd.append(toAppend)
            if s["epub_embed_font"] != "":
                if includes_paths_len == 0:
                    cmd.append("--epub-embed-font=" + s["epub_embed_font"])
                elif includes_paths_len > 0 and isinstance(includes_paths, list):
                    toAppend = ""
                    if os.path.exists(os.path.join(self.workingDIR, s["epub_embed_font"])):
                        toAppend = "--epub-embed-font=" + os.path.join(self.workingDIR, s["epub_embed_font"])
                    else:
                        for theIncludesPath in includes_paths:
                            theIncludesPath = os.path.abspath(theIncludesPath)
                            checkFile = os.path.join(theIncludesPath, s["epub_embed_font"])
                            if os.path.exists(checkFile):
                                toAppend = "--epub-embed-font=" + checkFile
                                break
                    if not toAppend:
                        toAppend = "--epub-embed-font=" + s["epub_embed_font"]
                    cmd.append(toAppend)
            if s["latex_engine"] != "":
                cmd.append("--latex-engine=" + s["latex_engine"])
            if s["bibliography"] != "":
                if includes_paths_len == 0:
                    cmd.append("--bibliography=" + s["bibliography"])
                elif includes_paths_len > 0 and isinstance(includes_paths, list):
                    toAppend = ""
                    if os.path.exists(os.path.join(self.workingDIR, s["bibliography"])):
                        toAppend = "--bibliography=" + os.path.join(self.workingDIR, s["bibliography"])
                    else:
                        for theIncludesPath in includes_paths:
                            theIncludesPath = os.path.abspath(theIncludesPath)
                            checkFile = os.path.join(theIncludesPath, s["bibliography"])
                            if os.path.exists(checkFile):
                                toAppend = "--bibliography=" + checkFile
                                break
                    if not toAppend:
                        toAppend = "--bibliography=" + s["bibliography"]
                    cmd.append(toAppend)
            if s["csl"] != "":
                if includes_paths_len == 0:
                    cmd.append("--csl=" + s["csl"])
                elif includes_paths_len > 0 and isinstance(includes_paths, list):
                    toAppend = ""
                    if os.path.exists(os.path.join(self.workingDIR, s["csl"])):
                        toAppend = "--csl=" + os.path.join(self.workingDIR, s["csl"])
                    else:
                        for theIncludesPath in includes_paths:
                            theIncludesPath = os.path.abspath(theIncludesPath)
                            checkFile = os.path.join(theIncludesPath, s["csl"])
                            if os.path.exists(checkFile):
                                toAppend = "--csl=" + checkFile
                                break
                    if not toAppend:
                        toAppend = "--csl=" + s["csl"]
                    cmd.append(toAppend)
            if s["citation_abbreviations"] != "":
                if includes_paths_len == 0:
                    cmd.append("--citation-abbreviations=" + s["citation_abbreviations"])
                elif includes_paths_len > 0 and isinstance(includes_paths, list):
                    toAppend = ""
                    if os.path.exists(os.path.join(self.workingDIR, s["citation_abbreviations"])):
                        toAppend = "--citation-abbreviations=" + os.path.join(self.workingDIR, s["citation_abbreviations"])
                    else:
                        for theIncludesPath in includes_paths:
                            theIncludesPath = os.path.abspath(theIncludesPath)
                            checkFile = os.path.join(theIncludesPath, s["citation_abbreviations"])
                            if os.path.exists(checkFile):
                                toAppend = "--citation-abbreviations=" + checkFile
                                break
                    if not toAppend:
                        toAppend = "--citation-abbreviations=" + s["citation_abbreviations"]
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
