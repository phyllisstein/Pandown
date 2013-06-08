import os
import sublime
import sublime_plugin


class PandownDisplayDefaultsCommand(sublime_plugin.WindowCommand):
    def run(self, fn=None):
        if not fn:
            return

        if int(sublime.version()) < 3000 or not "sublime-package" in __file__:
            default_path = os.path.join(sublime.packages_path(), "Pandown", fn)
            self.window.open_file(default_path)
        else:
            default_path = os.path.join("Packages", "Pandown", fn)
            default_data = sublime.load_resource(default_path)
            new_view = self.window.new_file()
            new_view.set_scratch(True)
            new_view.run_command("pandown_display_data", {"data": default_data})


class PandownDisplayDataCommand(sublime_plugin.TextCommand):
    def run(self, edit, data):
        self.view.insert(edit, 0, data)
