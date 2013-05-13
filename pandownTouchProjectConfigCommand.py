from __future__ import print_function
import sublime
import sublime_plugin
import os
import shutil


class PandownTouchProjectConfigCommand(sublime_plugin.WindowCommand):
    def run(self):
        if self.window.active_view().file_name():
            configFile = os.path.join(os.path.dirname(self.window.active_view().file_name()), 'pandoc-config.json')
        else:
            sublime.status_message("Cannot create project configuration for unsaved files.")
            return

        if os.path.exists(configFile):
            self.window.open_file(configFile)
            return

        defaultConfigFile = os.path.join(sublime.packages_path(), 'Pandown', 'default-pandoc-config.json')
        userConfigFile = os.path.join(sublime.packages_path(), 'User', 'pandoc-config.json')

        if not os.path.exists(defaultConfigFile) and not os.path.exists(userConfigFile):
            try:
                s = sublime.load_resource("Packages/Pandown/default-pandoc-config.json")
            except OSError as e:
                sublime.status_message("Could not load default Pandoc configuration.")
                print("[Pandown could not find a default configuration file in Packages/Pandown/default-pandoc-config.json]")
                print("[Loading from the binary package resource file also failed.]")
                return
            with open(configFile, "w") as f:
                f.write(s)
            self.window.open_file(configFile)

        else:
            try:
                toCopy = defaultConfigFile if not os.path.exists(userConfigFile) else userConfigFile
                shutil.copy(toCopy, configFile)
            except Exception as e:
                sublime.status_message("Could not write {0}".format(configFile))
                print("[Pandown encountered an exception:]")
                print("[e: {0}]".format(e))
            else:
                self.window.open_file(configFile)
