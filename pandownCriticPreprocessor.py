# Modified from the Marked preprocessor
# available at http://criticmarkup.com:
# Original Author: Gabriel Weatherhead
# Project: CriticMarkup
# License: Apache 2

import re
import tempfile
import codecs
import sublime

class PandownCriticPreprocessor:
    def deletionProcess(self, group_object):
        replaceString = ''
        if group_object.group('value') == '\n\n':
            replaceString = "<del>&nbsp;</del>"
        else:
            replaceString = '<del>' + group_object.group('value').replace("\n\n", "&nbsp;") + '</del>'
        return replaceString

    def subsProcess(self, group_object):
        delString = '<del>' + group_object.group('original') + '</del>'
        insString  = '<ins>' + group_object.group('new') + '</ins>'
        return delString + insString

    # Converts Addition markup to HTML
    def additionProcess(self, group_object):
        replaceString = ''

        # Is there a new paragraph followed by new text
        if group_object.group('value').startswith('\n\n') and group_object.group('value') != "\n\n":
            replaceString = "\n\n<ins class='critic' break>&nbsp;</ins>\n\n"
            replaceString = replaceString + '<ins>' + group_object.group('value').replace("\n", " ")
            replaceString = replaceString +  '</ins>'

        # Is the addition just a single new paragraph
        elif group_object.group('value') == "\n\n":
            replaceString = "\n\n<ins class='critic break'>&nbsp;" + '</ins>\n\n'

        # Is it added text followed by a new paragraph?
        elif group_object.group('value').endswith('\n\n') and group_object.group('value') != "\n\n":
            replaceString = '<ins>' + group_object.group('value').replace("\n", " ") + '</ins>'
            replaceString = replaceString + "\n\n<ins class='critic break'>&nbsp;</ins>\n\n"

        else:
            replaceString = '<ins>' + group_object.group('value').replace("\n", " ") + '</ins>'

        return replaceString

    def highlightProcess(self, group_object):
        replaceString = '<span class="critic comment">' + group_object.group('value').replace("\n", " ") + '</span>'
        return replaceString

    def markProcess(self, group_object):
        replaceString = '<mark>' + group_object.group('value') + '</mark>'
        return replaceString

    def preprocessCritic(self, inFile):
        add_pattern = r'''(?s)\{\+\+(?P<value>.*?)\+\+[ \t]*(\[(?P<meta>.*?)\])?[ \t]*\}'''

        del_pattern = r'''(?s)\{\-\-(?P<value>.*?)\-\-[ \t]*(\[(?P<meta>.*?)\])?[ \t]*\}'''

        comm_pattern = r'''(?s)\{\>\>(?P<value>.*?)\<\<\}'''

        gen_comm_pattern = r'''(?s)\{[ \t]*\[(?P<meta>.*?)\][ \t]*\}'''

        subs_pattern = r'''(?s)\{\~\~(?P<original>(?:[^\~\>]|(?:\~(?!\>)))+)\~\>(?P<new>(?:[^\~\~]|(?:\~(?!\~\})))+)\~\~\}'''

        mark_pattern = r'''(?s)\{\{(?P<value>.*?)\}\}'''

        with codecs.open(inFile, "r", "utf-8") as f:
            h = f.read()

        if int(sublime.version()) < 3000:
            h = re.sub(del_pattern, self.deletionProcess, h)
            h = re.sub(add_pattern, self.additionProcess, h)
            h = re.sub(comm_pattern, self.highlightProcess, h)
            h = re.sub(mark_pattern, self.markProcess, h)
            h = re.sub(subs_pattern, self.subsProcess, h)
        else:
            h = re.sub(del_pattern, self.deletionProcess, h, flags=re.DOTALL)
            h = re.sub(add_pattern, self.additionProcess, h, flags=re.DOTALL)
            h = re.sub(comm_pattern, self.highlightProcess, h, flags=re.DOTALL)
            h = re.sub(mark_pattern, self.markProcess, h, flags=re.DOTALL)
            h = re.sub(subs_pattern, self.subsProcess, h, flags=re.DOTALL)

        workingTemp = tempfile.NamedTemporaryFile("w", delete=False)
        workingTemp.close()
        with codecs.open(workingTemp.name, "w", "utf-8") as f:
            f.write(h)

        return workingTemp.name
