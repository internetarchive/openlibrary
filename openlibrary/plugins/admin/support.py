import datetime
import textwrap

import web
from infogami.utils.view import render_template
from infogami import config
from infogami.utils.markdown import markdown

from openlibrary.core import support

support_db = None

class cases(object):
    def GET(self, typ = "all"):
        if not support_db:
            return render_template("admin/cases", None, None, True, False)
        i = web.input(sort="status", desc = "false")
        sortby = i['sort']
        desc = i['desc']
        cases = support_db.get_all_cases(typ, summarise = False, sortby = sortby, desc = desc)
        summary = support_db.get_all_cases(typ, summarise = True)
        desc = desc == "false" and "true" or "false"
        return render_template("admin/cases", summary, cases, desc)

class case(object):
    def GET(self, caseid):
        if not support_db:
            return render_template("admin/cases", None, None, True, False)
        case = support_db.get_case(caseid)
        date_pretty_printer = lambda x: x.strftime("%B %d, %Y")
        md = markdown.Markdown()
        if len(case.history) == 1:
            last_email = case.description
        else:
            last_email = case.history[-1]['text']
        admins = ((x.get_email(), x.get_username(), x.get_email() == case.assignee) for x in web.ctx.site.get("/usergroup/admin").members)
        return render_template("admin/case", case, last_email, admins, date_pretty_printer, md.convert)

    def POST(self, caseid):
        if not support_db:
            return render_template("admin/cases", None, None, True, False)
        case = support_db.get_case(caseid)
        form = web.input()
        action = form.get("button","")
        {"SEND REPLY" : self.POST_sendreply,
         "UPDATE"     : self.POST_update,
         "CLOSE CASE" : self.POST_closecase}[action](form,case)
        date_pretty_printer = lambda x: x.strftime("%B %d, %Y")
        md = markdown.Markdown()
        last_email = case.history[-1]['text']
        last_email = "\n".join("> %s"%x for x in textwrap.wrap(last_email))
        admins = ((x.get_email(), x.get_username(), x.get_email() == case.assignee) for x in web.ctx.site.get("/usergroup/admin").members)
        return render_template("admin/case", case, last_email, admins, date_pretty_printer, md.convert, True)
    
    def POST_sendreply(self, form, case):
        user = web.ctx.site.get_user()
        casenote = form.get("casenote1", "")
        casenote = "%s replied:\n\n%s"%(user.get_username(), casenote)
        case.add_worklog_entry(by = user.get_email(),
                               text = casenote)
        case.change_status("replied", user.get_email())
        email_to = form.get("email", False)
        subject = "Case #%s: %s"%(case.caseno, case.subject)
        if email_to:
            web.sendmail(config.report_spam_address, email_to, subject, casenote, cc = "mary@openlibrary.org")

    def POST_update(self, form, case):
        casenote = form.get("casenote2", False)
        assignee = form.get("assignee", False)
        user = web.ctx.site.get_user()
        by = user.get_email()
        text = casenote or "No note entered"
        if assignee != case.assignee:
            text += "\n\nassigned to %s"%assignee
            case.reassign(assignee, by)
        case.add_worklog_entry(by = by,
                               text = text)


    def POST_closecase(self, form, case):
        user = web.ctx.site.get_user()
        by = user.get_email()
        text = "Case closed"
        case.add_worklog_entry(by = by,
                               text = text)
        case.change_status("closed", by)

def setup():
    global support_db
    try:
        support_db = support.Support()
    except support.DatabaseConnectionError:
        support_db = None


