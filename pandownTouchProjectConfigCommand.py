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
            sublime.status_message("Could not find default Pandoc configuration.")
            print("[Pandown stores default configuration information in Projects/Pandown/default-pandoc-config.json.]")
            print("[If this file has been moved or deleted, please reinstall Pandown.]")
            print("[See the README for support information.]")
            return
        try:
            toCopy = defaultConfigFile if (not os.path.exists(userConfigFile)) else userConfigFile
            shutil.copy(toCopy, configFile)
        except Exception as e:
            sublime.status_message("Could not write " + configFile)
            print("[Pandown encountered an exception:]")
            print("[e: " + str(e) + "]")
        else:
            self.window.open_file(configFile)
